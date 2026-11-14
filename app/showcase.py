"""Public showcase manifest and bundled landing sample generation."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

from . import topics
from .pack_ops import DEFAULT_VOICE, VOICES, voice_name
from .summarizer import strip_headline_and_filler

log = logging.getLogger(__name__)

SHOWCASE_KEY = "showcase/sample.json"
SHOWCASE_SECTIONS: tuple[str, ...] = ("top",)
SHOWCASE_PER_SECTION = 2
OUTRO_KEY = "outro"

SAMPLE_BUNDLE_DIR = "web/sample"
SAMPLE_BUNDLE_AUDIO = "sample.mp3"


def showcase_key(voice: str) -> str:
    """Storage object key for a narrator's public landing sample manifest."""
    return f"showcase/sample-{voice}.json"


def showcase_payload(
    rows: list[dict],
    notes: list[dict],
    url_for,
    *,
    day: str,
    voice: str | None = None,
    sections: tuple[str, ...] = SHOWCASE_SECTIONS,
    per_section: int = SHOWCASE_PER_SECTION,
) -> dict:
    """Build the public landing sample payload with running clip timeline and chapters."""
    note_by_key = {n["note_key"]: n for n in notes if not voice or n.get("voice") == voice}
    by_section: dict[str, list[dict]] = {}
    for row in rows:
        if voice and row.get("voice") != voice:
            continue
        by_section.setdefault(row["section"], []).append(row)

    clips: list[dict] = []
    chapters: list[dict] = []
    stories: list[dict] = []
    counts: dict[str, int] = {}
    cursor = 0.0

    def add(duration: float, cid: str, kind: str, title: str, path: str) -> tuple[float, float]:
        nonlocal cursor
        start, end = cursor, cursor + duration
        clips.append({"url": url_for(path), "duration": round(duration, 3),
                      "start": round(start, 3), "end": round(end, 3)})
        chapters.append({"id": cid, "kind": kind, "title": title,
                         "start": round(start, 3), "end": round(end, 3)})
        cursor = end
        return start, end

    greeting = note_by_key.get("greeting_morning")
    if greeting:
        add(float(greeting.get("duration") or 0), "greeting", "note",
            greeting.get("text") or "Good morning.", greeting["audio_path"])

    for key in sections:
        chosen = sorted(by_section.get(key, []), key=lambda r: r.get("rank", 0))[:per_section]
        if not chosen:
            continue
        intro = note_by_key.get(f"intro_{key}")
        if intro:
            add(float(intro.get("duration") or 0), f"intro-{key}", "note",
                intro.get("text") or "", intro["audio_path"])
        for row in chosen:
            cid = f"{key}-{row['rank']}"
            start, end = add(float(row.get("duration") or 0), cid, "story",
                             row.get("title") or "", row["audio_path"])
            stories.append({
                "id": cid, "section": key, "headline": row.get("title") or "",
                "summary": row.get("summary") or strip_headline_and_filler(row.get("title") or "", row.get("script") or ""),
                "source": row.get("source") or "",
                "url": row.get("url") or "", "image": row.get("image") or "",
                "start": round(start, 3), "end": round(end, 3),
            })
            counts[key] = counts.get(key, 0) + 1

    outro = note_by_key.get(OUTRO_KEY)
    if outro:
        add(float(outro.get("duration") or 0), OUTRO_KEY, "note",
            outro.get("text") or "", outro["audio_path"])

    return {
        "date": day,
        "rows": rows,
        "notes": notes,
        "briefing": {
            "date": day,
            "title": "Your briefing",
            "voice": {"id": voice or DEFAULT_VOICE, "name": voice_name(voice),
                      "gender": (VOICES.get(voice or "") or {}).get("gender", "")},
            "duration": round(cursor, 2),
            "audio_url": "",
            "clips": clips,
            "chapters": chapters,
            "stories": stories,
            "sections": [{"key": k, "title": topics.ALL_SECTIONS[k]["title"], "count": n}
                         for k, n in counts.items()],
        },
    }


def _load_showcase_data(cfg, store, day: str | None, voice: str | None,
                        sections: tuple[str, ...], per_section: int) -> tuple[str, str, dict]:
    resolved_day = day or cfg.local_today()
    resolved_voice = voice or cfg.story_voice
    rows = store.select("story_audio", {"date": f"eq.{resolved_day}", "voice": f"eq.{resolved_voice}"})
    notes = store.select("voice_notes", {"date": f"eq.{resolved_day}", "voice": f"eq.{resolved_voice}"})
    payload = showcase_payload(rows, notes, store.public_url, day=resolved_day, voice=resolved_voice,
                               sections=sections, per_section=per_section)
    return resolved_day, resolved_voice, payload


async def publish_showcase(
    cfg,
    store,
    *,
    day: str | None = None,
    voice: str | None = None,
    sections: tuple[str, ...] = SHOWCASE_SECTIONS,
    per_section: int = SHOWCASE_PER_SECTION,
) -> dict:
    """Publish the public sample of the day's pack for the landing page and guest apps."""
    day, voice, payload = _load_showcase_data(cfg, store, day, voice, sections, per_section)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    store.upload(showcase_key(voice), body, content_type="application/json", cache="max-age=300")
    if voice == (cfg.story_voices or (DEFAULT_VOICE,))[0]:
        store.upload(SHOWCASE_KEY, body, content_type="application/json", cache="max-age=300")
    try:
        all_rows = store.select("story_audio", {"date": f"eq.{day}"})
        all_notes = store.select("voice_notes", {"date": f"eq.{day}"})
        all_podcast = store.select("podcast_clips", {"date": f"eq.{day}"})
        if all_rows:
            pack_body = json.dumps(
                {"date": day, "story_audio": all_rows, "voice_notes": all_notes, "podcast_clips": all_podcast},
                ensure_ascii=False, separators=(",", ":"),
            ).encode()
            store.upload("showcase/pack.json", pack_body, content_type="application/json", cache="max-age=300")
            store.upload(f"showcase/pack-{day}.json", pack_body, content_type="application/json", cache="max-age=300")
    except Exception as exc:  # noqa: BLE001
        log.debug("Could not publish full guest pack manifest: %s", exc)
    log.info("Published the landing sample: %d clips, %.1fs",
             len(payload["briefing"]["clips"]), payload["briefing"]["duration"])
    return payload


def _probe_seconds(path: Path) -> float | None:
    """Return real duration in seconds via ffprobe, or None if unavailable."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            check=True, capture_output=True, text=True).stdout.strip()
        return float(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


async def _join_clips(urls: list[str], dest: Path, workdir: Path) -> bool:
    """Download and concatenate MP3 clips losslessly via ffmpeg; return False if unavailable."""
    if not urls or not shutil.which("ffmpeg"):
        return False
    parts = workdir / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    async with httpx.AsyncClient(timeout=300) as client:
        for i, url in enumerate(urls):
            resp = await client.get(url)
            resp.raise_for_status()
            name = f"{i:02d}.mp3"
            (parts / name).write_bytes(resp.content)
            names.append(name)
    listing = workdir / "parts.txt"
    listing.write_text("".join(f"file '{parts / n}'\n" for n in names))
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                        "-i", str(listing), "-c", "copy", str(dest)],
                       check=True, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Could not join the sample audio: %s", exc)
        return False
    return dest.exists() and dest.stat().st_size > 0


async def write_sample_bundle(
    cfg,
    store,
    directory: str = SAMPLE_BUNDLE_DIR,
    *,
    day: str | None = None,
    voice: str | None = None,
    sections: tuple[str, ...] = SHOWCASE_SECTIONS,
    per_section: int = SHOWCASE_PER_SECTION,
) -> dict:
    """Write the checked-in static landing sample MP3 and ``sample.json`` manifest."""
    _, _, payload = _load_showcase_data(cfg, store, day, voice, sections, per_section)
    brief = payload["briefing"]
    clips = brief.pop("clips", [])

    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    audio = out / SAMPLE_BUNDLE_AUDIO
    with tempfile.TemporaryDirectory() as tmp:
        joined = await _join_clips([c["url"] for c in clips], audio, Path(tmp))
    if joined:
        brief["audio_url"] = f"/sample/{SAMPLE_BUNDLE_AUDIO}"
        seconds = _probe_seconds(audio)
        if seconds:
            brief["duration"] = round(seconds, 2)
    else:
        brief["clips"] = clips
        brief["audio_url"] = ""
        audio.unlink(missing_ok=True)

    (out / "sample.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    log.info("Wrote the fixed landing sample to %s (%s, %.1fs)", out,
             brief["audio_url"] or f"{len(clips)} clips", brief["duration"])
    return payload
