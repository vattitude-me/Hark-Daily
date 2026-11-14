"""Build the day's shared story pack: stories → cloned voice → Supabase."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from . import topics
from .errors import DeadlineReached, PackBusy, PackIncomplete, VoiceServiceDown
from .pack_ops import (
    DEFAULT_VOICE,
    PACK_READY,
    STATIC_DATE,
    VOICES,
    clear_ready,
    holder_name,
    mark_ready,
    notify_admins,
    notify_listeners,
    pack_lease,
    prune_older,
    ready,
    record,
    voice_name,
    voice_slug,
)
from .showcase import (
    OUTRO_KEY,
    SAMPLE_BUNDLE_AUDIO,
    SAMPLE_BUNDLE_DIR,
    SHOWCASE_KEY,
    SHOWCASE_PER_SECTION,
    SHOWCASE_SECTIONS,
    _join_clips,
    _probe_seconds,
    publish_showcase,
    showcase_key,
    showcase_payload,
    write_sample_bundle,
)
from .store import StoreError
from .tts.text import clean_punctuation, voice_phonetic_normalize

log = logging.getLogger(__name__)

MAX_PER_SECTION = 5

GREETINGS = {
    "greeting_morning": "Good morning.",
    "greeting_afternoon": "Good afternoon.",
    "greeting_evening": "Good evening.",
}
INTROS = {
    "intro_top": "Here are the top stories.",
    "intro_markets": "Checking the markets.",
    "intro_ai": "Here's the latest in AI.",
    "intro_tech": "Now, the latest in tech.",
    "intro_politics": "Turning to politics.",
    "intro_entertainment": "In entertainment.",
    "intro_science": "In science.",
    "intro_sports": "In sports.",
}
OUTRO = "That's today's briefing. Have a great day, and stay informed."
NOTES: dict[str, str] = {**GREETINGS, **INTROS, OUTRO_KEY: OUTRO}


def static_note_path(key: str, voice: str) -> str:
    """The canonical permanent storage path for a static voice note."""
    return f"notes/static/{key}-{voice_slug(voice)}.mp3"


def greeting_key(hour: int) -> str:
    """Which greeting a listener hears, by their local hour (mirrors the client)."""
    if hour < 12:
        return "greeting_morning"
    if hour < 17:
        return "greeting_afternoon"
    return "greeting_evening"


def default_lineup() -> dict[str, int]:
    """Top stories defaults to 5, other categories default to 3."""
    return {key: (5 if key == "top" else 3) for key in topics.SECTIONS}


def lineup(settings: dict | None, default: dict[str, int] | None = None) -> dict[str, int]:
    """Per-section story counts from ``profiles.settings.stories``, clamped to 0..``MAX_PER_SECTION``."""
    chosen = (settings or {}).get("stories") or {}
    base = default or default_lineup()
    out: dict[str, int] = {}
    for key in topics.SECTIONS:
        try:
            count = int(chosen.get(key, base.get(key, 3 if key != "top" else 5)))
        except (TypeError, ValueError):
            count = 0
        out[key] = max(0, min(count, MAX_PER_SECTION))
    return out


def clips_for(rows: list[dict], wanted: dict[str, int], voice: str | None = None) -> list[dict]:
    """Order the shared clips into one listener's briefing following the section reading order."""
    by_section: dict[str, list[dict]] = {}
    for row in rows:
        if voice and row.get("voice") != voice:
            continue
        by_section.setdefault(row["section"], []).append(row)

    ordered: list[dict] = []
    for key in topics.SECTIONS:
        count = wanted.get(key, 0)
        if count > 0:
            ordered.extend(sorted(by_section.get(key, []), key=lambda r: r.get("rank", 0))[:count])
    return ordered


def total_seconds(clips: list[dict]) -> float:
    return round(sum(float(c.get("duration") or 0) for c in clips), 2)


async def synthesise(
    client: httpx.AsyncClient,
    base: str,
    text: str,
    voice: str,
    attempts: int = 3,
    *,
    pace: float | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    repetition_penalty: float | None = None,
    exaggeration: float | None = None,
    beat: float | None = None,
    fmt: str = "mp3",
) -> tuple[bytes, float]:
    """Request one synthesized clip (MP3 or WAV) from the voice service with retry backoff."""
    clean_text = clean_punctuation(voice_phonetic_normalize(text))
    payload: dict[str, Any] = {"text": clean_text, "voice": voice}
    for param, value in (
        ("pace", pace), ("temperature", temperature), ("top_p", top_p),
        ("repetition_penalty", repetition_penalty), ("exaggeration", exaggeration), ("beat", beat),
    ):
        if value is not None:
            payload[param] = value

    delay = 5
    last: Exception | None = None
    down = False
    for attempt in range(1, attempts + 1):
        try:
            resp = await client.post(f"{base}/synthesize", params={"format": fmt}, json=payload)
        except httpx.HTTPError as exc:
            last, down = exc, True
        else:
            if resp.status_code < 400:
                return resp.content, float(resp.headers.get("X-Duration") or 0.0)
            last, down = RuntimeError(f"voice service {resp.status_code}: {resp.text[:200]}"), False
            if resp.status_code not in (502, 503, 504):
                raise last
        if attempt < attempts:
            log.warning("voice service not answering (%s); retrying in %ds", last.__class__.__name__, delay)
            await asyncio.sleep(delay)
            delay *= 3
    if down:
        raise VoiceServiceDown(f"voice service unavailable after {attempts} attempts: {last}")
    raise last  # type: ignore[misc]


async def ensure_static_notes(
    cfg,
    store,
    *,
    voices: list[str],
    voice_url: str | None = None,
    force: bool = False,
    on_note: Callable[[str, str], None] | None = None,
) -> dict[str, list[dict]]:
    """Ensure static transition notes (greetings, intros, outro) are voiced once and stored permanently."""
    base = (voice_url or cfg.voice_url or "").rstrip("/")
    if not base:
        raise VoiceServiceDown("VOICE_SERVICE_URL is not set. A running voice service is required to synthesize audio.")

    results: dict[str, list[dict]] = {}
    async with httpx.AsyncClient(timeout=900) as client:
        for voice in voices:
            static_rows = {
                r["note_key"]: r
                for r in store.select("voice_notes", {"date": f"eq.{STATIC_DATE}", "voice": f"eq.{voice}"})
            }
            missing = [k for k in NOTES if force or k not in static_rows or static_rows[k].get("text") != NOTES[k]]

            if missing and not force:
                try:
                    for r in store.select("voice_notes", {"voice": f"eq.{voice}"}):
                        k = r.get("note_key")
                        if k in missing and r.get("text") == NOTES[k] and r.get("audio_path"):
                            target_path = static_note_path(k, voice)
                            if r["audio_path"] != target_path:
                                try:
                                    store.copy(r["audio_path"], target_path)
                                except Exception:
                                    pass
                            adopted = {
                                "date": STATIC_DATE, "voice": voice, "note_key": k,
                                "text": NOTES[k], "duration": r.get("duration") or 0,
                                "audio_path": target_path,
                            }
                            store.insert("voice_notes", adopted, on_conflict="date,voice,note_key")
                            static_rows[k] = adopted
                            missing.remove(k)
                            log.info("[static-note] %-20s adopted from %s for %s", k, r.get("date"), voice_name(voice))
                except Exception as exc:  # noqa: BLE001
                    log.debug("Could not adopt existing notes for %s: %s", voice, exc)

            if missing:
                synth_voice = voice.split("+", 1)[0] if "+" in voice else voice
                log.info("→ Synthesizing %d missing static notes for %s before VM shutdown...",
                         len(missing), voice_name(voice))
                for key in missing:
                    text = NOTES[key]
                    if on_note:
                        on_note(key, voice)
                    path = static_note_path(key, voice)
                    audio, duration = await synthesise(client, base, text, synth_voice)
                    store.upload(path, audio, content_type="audio/mpeg", cache="max-age=31536000")
                    row = {
                        "date": STATIC_DATE, "voice": voice, "note_key": key,
                        "text": text, "duration": round(duration, 3), "audio_path": path,
                    }
                    store.insert("voice_notes", row, on_conflict="date,voice,note_key")
                    static_rows[key] = row
                    log.info("[static-note] %-20s %-34s voiced & saved (%.1fs)", key, text, duration)
            else:
                log.info("[static-note] All %d static notes verified for %s (0 synthesized)",
                         len(NOTES), voice_name(voice))

            results[voice] = [static_rows[k] for k in NOTES if k in static_rows]
    return results


async def build_notes(
    cfg,
    store,
    *,
    day: str | None = None,
    voice: str | None = None,
    voice_url: str | None = None,
    keys: list[str] | None = None,
    force: bool = False,
    on_note: Callable[[str], None] | None = None,
) -> list[dict]:
    """Ensure static transition notes exist and link them to ``day`` in ``voice_notes``."""
    day = day or cfg.local_today()
    voice = voice or cfg.story_voice
    base = (voice_url or cfg.voice_url or "").rstrip("/")
    if not base:
        raise VoiceServiceDown("VOICE_SERVICE_URL is not set. A running voice service is required to synthesize audio.")

    static_map = await ensure_static_notes(
        cfg, store, voices=[voice], voice_url=base, force=force,
        on_note=lambda k, _: on_note(k) if on_note else None,
    )
    static_by_key = {r["note_key"]: r for r in static_map.get(voice, [])}

    items = [(k, NOTES[k]) for k in NOTES if not keys or k in keys]
    done = {r["note_key"]: r for r in store.select("voice_notes", {"date": f"eq.{day}", "voice": f"eq.{voice}"})}

    rows: list[dict] = []
    for key, text in items:
        if on_note:
            on_note(key)
        have = done.get(key)
        if not force and have and have.get("text") == text and have.get("audio_path"):
            rows.append(have)
            continue
        static_ref = static_by_key.get(key)
        if static_ref:
            row = {
                "date": day, "voice": voice, "note_key": key, "text": text,
                "duration": static_ref.get("duration") or 0,
                "audio_path": static_ref.get("audio_path") or static_note_path(key, voice),
            }
            store.insert("voice_notes", row, on_conflict="date,voice,note_key")
            rows.append(row)
            log.info("[note] %-20s %-34s linked to static (%.1fs)", key, text, row["duration"])

    log.info("Published %d voice notes for %s on %s", len(rows), voice_name(voice), day)
    return rows


def backfill_from_existing(
    scripts: list[dict],
    store,
    day: str,
    per_section: int,
    sections: list[str] | None = None,
) -> list[dict]:
    """Backfill starved sections using unexpired stories from earlier today's run."""
    target_sections = sections or list(topics.ALL_SECTIONS)
    current_by_sec: dict[str, list[dict]] = {sec: [] for sec in target_sections}
    for s in scripts:
        if s.get("section") in current_by_sec:
            current_by_sec[s["section"]].append(s)

    starved = [sec for sec, items in current_by_sec.items() if len(items) < per_section]
    if not starved:
        return scripts

    try:
        rows = store.select("story_audio", {"date": f"eq.{day}"})
    except Exception as exc:
        log.warning("Could not check existing story_audio for backfill: %s", exc)
        return scripts

    existing_by_sec: dict[str, list[dict]] = {}
    seen_urls = {topics.bare_url(s.get("url")) for s in scripts if s.get("url")}
    seen_titles = {topics.plain_title(s.get("title")) for s in scripts if s.get("title")}

    for r in sorted(rows, key=lambda x: x.get("rank", 99)):
        sec = r.get("section")
        url = topics.bare_url(r.get("url"))
        title = topics.plain_title(r.get("title"))
        if sec in starved and url and url not in seen_urls and (not title or title not in seen_titles):
            seen_urls.add(url)
            if title:
                seen_titles.add(title)
            existing_by_sec.setdefault(sec, []).append(r)

    out: list[dict] = []
    for sec in target_sections:
        items = current_by_sec.get(sec, [])
        needed = per_section - len(items)
        if needed > 0 and sec in existing_by_sec:
            backfill = existing_by_sec[sec][:needed]
            log.info("Backfilling %d earlier stories for section '%s'", len(backfill), sec)
            for extra in backfill:
                items.append({
                    "id": extra.get("id") or extra.get("url"),
                    "section": sec,
                    "rank": len(items) + 1,
                    "title": extra.get("title", ""),
                    "source": extra.get("source", ""),
                    "url": extra.get("url", ""),
                    "published": extra.get("published"),
                    "image": extra.get("image"),
                    "summary": extra.get("summary", ""),
                    "script": extra.get("script", ""),
                    "duration": extra.get("duration"),
                    "audio_path": extra.get("audio_path"),
                })
        for rank, item in enumerate(items, 1):
            item["rank"] = rank
            out.append(item)
    return out


async def build(
    cfg,
    store,
    *,
    day: str | None = None,
    per_section: int | None = None,
    sections: list[str] | None = None,
    edition: str | list[str] | None = None,
    voice: str | None = None,
    voice_url: str | None = None,
    notes: bool = True,
    force: bool = False,
    deadline: float | None = None,
    on_step: Callable[[str, float], None] | None = None,
) -> list[dict]:
    """Fetch stories, voice them per configured narrator, publish showcase, and prune old days."""
    day = day or cfg.local_today()
    base = (voice_url or cfg.voice_url or "").rstrip("/")
    if not base:
        raise VoiceServiceDown("VOICE_SERVICE_URL is not set. A running voice service is required to synthesize audio.")
    per_section = per_section or cfg.stories_per_section
    voices = [voice] if voice else list(cfg.story_voices or (DEFAULT_VOICE,))

    if not sections and edition:
        sections = topics.sections_for_editions(edition)
    scripts = (
        await topics.build_pack(per_section=per_section, sections=sections, edition=edition)
        if edition is not None
        else await topics.build_pack(per_section=per_section, sections=sections)
    )
    scripts = backfill_from_existing(scripts, store, day=day, per_section=per_section, sections=sections)
    log.info("Voicing %d stories for %s as %s", len(scripts), day, ", ".join(voices))

    units = len(scripts) * len(voices) + (len(NOTES) * len(voices) if notes else 0) + 1
    seen = {"n": 0}

    def tick(text: str) -> None:
        seen["n"] += 1
        if on_step:
            on_step(text, min(0.99, seen["n"] / units))

    rows: list[dict] = []
    failed: dict[str, str] = {}
    finished: list[str] = []
    for name in voices:
        if deadline is not None and time.monotonic() >= deadline:
            failed[voice_name(name)] = "ran out of time before it started"
            continue
        try:
            if force:
                clear_ready(store, day=day, voice=name)
            mine = await voice_scripts(
                store, scripts, day=day, voice=name, base=base, force=force, deadline=deadline, cfg=cfg,
                on_clip=lambda story, who=name: tick(f"{voice_name(who)}: {story['section']} #{story['rank']}"),
            )
            if notes:
                await build_notes(cfg, store, day=day, voice=name, voice_url=base, force=force,
                                  on_note=lambda key, who=name: tick(f"{voice_name(who)}: {key}"))
            if notes and mine:
                mark_ready(store, day=day, voice=name, clips=len(mine), notes=len(NOTES))
        except VoiceServiceDown:
            raise
        except Exception as exc:  # noqa: BLE001 — one narrator's failure must not discard the others
            log.error("[%s] did not finish: %s", voice_name(name), exc)
            failed[voice_name(name)] = (str(exc) if isinstance(exc, DeadlineReached)
                                        else f"{exc.__class__.__name__}: {exc}")[:300]
            continue
        finished.append(name)
        rows += mine

    log.info("Published %d clips (%.1fs of audio)", len(rows), total_seconds(rows))

    if cfg.podcast_enabled and finished:
        from . import podcast
        try:
            clips = await podcast.build_podcast(cfg, store, scripts, day=day, base=base, force=force)
            log.info("Published %d podcast pieces", len(clips))
        except Exception as exc:  # noqa: BLE001
            log.warning("Podcast not (fully) published: %s: %s", exc.__class__.__name__, exc)
        tick("podcast")

    try:
        for name in finished:
            await publish_showcase(cfg, store, day=day, voice=name)
        tick("landing sample")
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not publish the landing sample: %s", exc)

    everything = list(cfg.story_voices or (DEFAULT_VOICE,))
    if everything and all(ready(store, day=day, voice=n) for n in everything):
        ed_list = [e.strip().lower() for e in edition.split(",")] if isinstance(edition, str) else list(edition or [])
        preserve = [s for s in topics.EDITION_SECTIONS.get("in", []) if s.endswith("_in")] if ("in" not in ed_list and ed_list) else None
        gone = prune_older(store, keep=day, keep_days=cfg.keep_days, preserve_sections=preserve)
        if gone:
            log.info("Pruned %d older day(s): %s", len(gone), ", ".join(gone))
    if failed:
        raise PackIncomplete(failed, rows)
    return rows


def _publish_audio_file(store, path: str, audio: bytes) -> None:
    store.upload(path, audio, content_type="audio/mpeg", cache="max-age=86400")


def story_audio_path(day: str, section: str, rank: int | str, voice: str, audio: bytes) -> str:
    """Content-hashed storage path for a voiced story clip."""
    content_hash = hashlib.sha256(audio).hexdigest()[:8]
    return f"stories/{day}/{section}-{rank}-{voice_slug(voice)}-{content_hash}.mp3"


def upsert_story_audio(store, row: dict) -> None:
    """Upsert a ``story_audio`` row, gracefully omitting ``marks`` if the DB lacks that column."""
    try:
        store.insert("story_audio", row, on_conflict="date,section,rank,voice")
    except Exception as exc:
        if "marks" in str(exc).lower() and "marks" in row:
            store.insert("story_audio", {k: v for k, v in row.items() if k != "marks"},
                         on_conflict="date,section,rank,voice")
        else:
            raise


async def voice_scripts(
    store,
    scripts: list[dict],
    *,
    day: str,
    voice: str,
    base: str,
    force: bool = False,
    on_clip: Callable[[dict], None] | None = None,
    deadline: float | None = None,
    cfg=None,
) -> list[dict]:
    """Voice one narrator's (or duo pair's) stories with overlapped background uploads."""
    existing = {(r["section"], r["rank"]): r for r in store.select(
        "story_audio", {"date": f"eq.{day}", "voice": f"eq.{voice}"})}
    existing_by_url = {r["url"]: r for r in existing.values() if r.get("url")}
    is_duo = "+" in voice
    duo_voices: tuple[str, str] | None = None
    duo_names: tuple[str, str] = ("Matthew", "Kelly")
    if is_duo:
        parts = [p.strip() for p in voice.split("+") if p.strip()]
        if len(parts) >= 2:
            duo_voices = (parts[0], parts[1])
            duo_names = (voice_name(parts[0]).split()[0], voice_name(parts[1]).split()[0])

    rows: list[dict] = []
    publishing: list[asyncio.Future] = []
    prev_story_by_sec: dict[str, dict] = {}
    prev_format_by_sec: dict[str, str] = {}
    prev_dialogue_by_sec: dict[str, Any] = {}

    def raise_if_publishing_failed() -> None:
        for task in publishing:
            if task.done() and task.exception():
                raise task.exception()

    async with httpx.AsyncClient(timeout=900) as client:
        try:
            for story in scripts:
                raise_if_publishing_failed()
                if on_clip:
                    on_clip(story)
                sec_key = story["section"]
                prev_story = prev_story_by_sec.get(sec_key)
                prev_fmt = prev_format_by_sec.get(sec_key)
                prev_diag = prev_dialogue_by_sec.get(sec_key)
                prev_story_by_sec[sec_key] = story
                image = (story.get("image") or "")[:2000] or None
                done = existing.get((story["section"], story["rank"]))
                if not (done and done.get("audio_path") and done.get("url") == story["url"]):
                    done = existing_by_url.get(story["url"])
                if not force and done and done.get("audio_path") and done.get("url") == story["url"]:
                    rows.append({
                        **done, "section": story["section"], "rank": story["rank"], "image": image,
                        "title": story["title"][:500],
                        "source": (story.get("source") or done.get("source") or "")[:200],
                        "script": done.get("script") if is_duo and done.get("script") else story["script"],
                    })
                    log.info("[%s %s #%s] %s — reused (%.1fs)", voice_name(voice), story["section"],
                             story["rank"], story["title"][:60], done.get("duration") or 0)
                    continue

                if deadline is not None and time.monotonic() >= deadline:
                    raise DeadlineReached(f"ran out of time at {story['section']} #{story['rank']}")
                if duo_voices:
                    from . import podcast
                    dialogue = await asyncio.to_thread(
                        podcast.generate_story_dialogue, cfg, story, duo_names, force=force,
                        previous_story=prev_story, previous_format=prev_fmt, previous_dialogue=prev_diag,
                    )
                    prev_dialogue_by_sec[sec_key] = dialogue
                    prev_format_by_sec[sec_key] = dialogue.story_format
                    audio, duration, marks = await podcast.synthesise_story_dialogue(
                        client, base, dialogue, duo_voices, cache_dir=getattr(cfg, "cache_dir", None),
                    )
                    spoken_script = podcast.format_dialogue_transcript(dialogue.turns, duo_names)
                    marks_payload = [{"start": round(m[0], 3), "end": round(m[1], 3)} for m in marks]
                else:
                    audio, duration = await synthesise(client, base, story["script"], voice)
                    spoken_script = story["script"]
                    marks_payload = None

                path = story_audio_path(day, story["section"], story["rank"], voice, audio)
                row: dict[str, Any] = {
                    "date": day, "section": story["section"], "rank": story["rank"], "voice": voice,
                    "title": story["title"][:500], "url": story["url"],
                    "source": (story["source"] or "")[:200], "image": image,
                    "script": spoken_script, "duration": round(duration, 3), "audio_path": path,
                    **({"marks": marks_payload} if marks_payload else {}),
                }
                publishing.append(asyncio.ensure_future(asyncio.to_thread(_publish_audio_file, store, path, audio)))
                rows.append(row)
                log.info("[%s %s #%s] %s — %.1fs", voice_name(voice), story["section"], story["rank"],
                         story["title"][:60], duration)
        except Exception:
            await asyncio.gather(*publishing, return_exceptions=True)
            raise
        await asyncio.gather(*publishing)

    for row in rows:
        upsert_story_audio(store, row)
    current_keys = {(r["section"], r["rank"]) for r in rows}
    built_sections = {s["section"] for s in scripts}
    stale_ranks = {(sec, rk) for (sec, rk) in existing.keys() if sec in built_sections} - current_keys
    for sec, rk in stale_ranks:
        store.delete("story_audio", {"date": f"eq.{day}", "voice": f"eq.{voice}",
                                     "section": f"eq.{sec}", "rank": f"eq.{rk}"})
    return rows


def main() -> int:
    from .config import load
    from .store import Store

    ap = argparse.ArgumentParser(description="Voice the day's stories into the shared pack.")
    ap.add_argument("--day", help="Date to publish under (default: today)")
    ap.add_argument("--voice", help="Reference clip name (default: STORY_VOICE)")
    ap.add_argument("--per-section", type=int, help="Stories per section (default: STORIES_PER_SECTION)")
    ap.add_argument("--sections", help="Comma-separated subset (default: all)")
    ap.add_argument("--notes-only", action="store_true", dest="notes_only",
                    help="only re-voice the greeting and section intros")
    ap.add_argument("--no-notes", action="store_true", dest="no_notes",
                    help="skip the greeting and section intros")
    ap.add_argument("--showcase-only", action="store_true", dest="showcase_only",
                    help="only republish the landing page's sample of the day's pack")
    ap.add_argument("--sample-bundle", nargs="?", const=SAMPLE_BUNDLE_DIR, metavar="DIR",
                    help="write the fixed landing sample (audio + manifest) into DIR")
    ap.add_argument("--force", action="store_true",
                    help="re-voice every clip and note, even ones already published")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load()
    store = Store.from_config(cfg)
    sections = args.sections.split(",") if args.sections else None
    if args.sample_bundle:
        payload = asyncio.run(write_sample_bundle(cfg, store, args.sample_bundle, day=args.day, voice=args.voice))
        brief = payload["briefing"]
        print(f"wrote {args.sample_bundle}: {brief['audio_url'] or 'clip playlist'}, "
              f"{brief['duration']:.1f}s, {len(brief['stories'])} stories")
        return 0
    if args.showcase_only:
        payload = asyncio.run(publish_showcase(cfg, store, day=args.day, voice=args.voice))
        brief = payload["briefing"]
        print(f"published the landing sample: {len(brief['clips'])} clips, {brief['duration']:.1f}s")
        return 0
    if args.notes_only:
        notes = asyncio.run(build_notes(cfg, store, day=args.day, voice=args.voice))
        print(f"published {len(notes)} voice notes")
        return 0 if notes else 1
    rows = asyncio.run(build(cfg, store, day=args.day, per_section=args.per_section,
                             sections=sections, voice=args.voice, notes=not args.no_notes, force=args.force))
    print(f"published {len(rows)} clips, {total_seconds(rows):.1f}s of audio")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
