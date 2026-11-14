"""Podcast mode: two hosts chat around the day's news.

This module plans, writes, and voices shared banter pieces (``pod_open_*``,
``pod_tease_*``, ``pod_bridge_*``, ``pod_close_*``) and re-exports the text,
prompt, and story-dialogue APIs for callers and tests.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import date as _date

import httpx

from . import llm, topics
from .llm import GEMINI_URL, GROQ_URL, retry_after as _retry_after
from .podcast_dialogue import (
    PURPOSE_PAUSES,
    STORY_DIALOGUE_VERSION,
    VALID_PURPOSES,
    DialogueTurn,
    StoryDialogue,
    _dialogue_cache_path,
    _shared_topic_terms,
    _speaker_index,
    build_story_brief,
    fallback_story_dialogue,
    format_dialogue_transcript,
    generate_story_dialogue,
    is_solo_format,
    parse_story_dialogue_payload,
    select_story_format,
    select_story_lead,
    solo_host_index,
    stitch_turn_audio,
    synthesise_story_dialogue,
    validate_story_dialogue,
)
from .podcast_prompts import (
    _ANGLE_LENS,
    BRIDGE_TEMPLATES,
    CLOSE_TEMPLATES,
    CLOSE_VARIANTS,
    HOST_PERSONAS_BLOCK,
    OPEN_TEMPLATES,
    OPEN_TEMPLATES_CA,
    OPEN_TEMPLATES_IN,
    OPEN_TEMPLATES_US,
    OPEN_VARIANTS,
    SOBER_STORY_FORMAT_KEYS,
    STORY_DIALOGUE_PROMPT,
    STORY_FORMAT_KEYS,
    STORY_FORMATS,
    SYSTEM_PROMPT,
    TEASE_TEMPLATES,
    _fill,
    _prompt,
    _tone_family,
)
from .podcast_text import (
    _BAD,
    _PROFANITY_PATTERN,
    _TAG,
    _TAG_START,
    ALIEN_BRIDGE_TERMS,
    DANGLING_OPENER_RE,
    HEAVY_SECTIONS,
    MAX_TAGS,
    MAX_TURNS,
    MAX_WORDS,
    SLOP_PATTERNS,
    SOBER_KEYWORDS,
    SOBER_SECTIONS,
    TAGS,
    TONE,
    UNBOUND_CATEGORY_NOUNS,
    Turn,
    _clean,
    _enforce_host_identity,
    _is_redundant_with_headline,
    _split_sentences,
    clean_headline,
    clean_slop,
    extract_headline_lead_entity,
    is_unbound_story_lead,
    sanitize_profanity,
    strip_repetition_stutter,
    strip_speaker_prefix,
    strip_tags,
    transcript,
    validate_turns,
)

log = logging.getLogger(__name__)

READY_KEY = "podcast_ready"
_agy_bin = llm.agy_bin  # Test monkeypatch target


def _ai_provider_chain(cfg) -> list[tuple[str, str, str, str]]:
    """Build ordered AI provider chain, honoring test monkeypatches on ``podcast._agy_bin``."""
    return llm.ai_provider_chain(cfg, bin_lookup=_agy_bin)


@dataclass
class Piece:
    key: str
    kind: str                      # open | open_ca | open_us | open_in | tease | bridge | close
    section: str | None = None
    headline: str = ""
    summary: str = ""


@dataclass
class Written:
    turns: list[Turn]
    writer: str = "built-in"


class PodcastIncomplete(Exception):
    """Some pieces could not be published. The brief itself is unaffected."""


def piece_key(kind: str, n: int | str) -> str:
    return f"pod_{kind}_{n}"


def _clip_summary(raw: str, limit: int = 300) -> str:
    cleaned = _clean(raw)
    if len(cleaned) > limit:
        return cleaned[: limit - 3].rsplit(" ", 1)[0] + "..."
    return cleaned


def plan_pieces(scripts: list[dict]) -> list[Piece]:
    """The pieces the day needs: variants of open/close plus a tease and bridge per section."""
    pieces = [Piece(piece_key("open", i + 1), "open") for i in range(OPEN_VARIANTS)]
    top: dict[str, dict] = {}
    for s in scripts:
        sec = s.get("section")
        if sec in topics.ALL_SECTIONS and (sec not in top or s.get("rank", 99) < top[sec].get("rank", 99)):
            top[sec] = s

    for sec, kind in (("top", "open_ca"), ("top_us", "open_us"), ("top_in", "open_in")):
        if sec in top:
            pieces.append(Piece(
                f"pod_{kind}_1", kind, sec,
                _clean(top[sec].get("title", "")), _clean(top[sec].get("summary", ""))[:300],
            ))

    for sec, story in top.items():
        headline = _clean(story.get("title", ""))
        pieces.append(Piece(piece_key("tease", sec), "tease", sec, headline, _clip_summary(story.get("summary", ""))))
        pieces.append(Piece(piece_key("bridge", sec), "bridge", sec, headline))
    pieces += [Piece(piece_key("close", i + 1), "close") for i in range(CLOSE_VARIANTS)]
    return pieces


def template_piece(piece: Piece, hosts: tuple[str, str]) -> Written:
    """Guaranteed fallback. Variants rotate by position so open/close pieces differ."""
    regional = {"open_ca": OPEN_TEMPLATES_CA, "open_us": OPEN_TEMPLATES_US, "open_in": OPEN_TEMPLATES_IN}
    if piece.kind == "open":
        n = int(piece.key.rsplit("_", 1)[1]) - 1
        turns = OPEN_TEMPLATES[n % len(OPEN_TEMPLATES)]
    elif piece.kind in regional:
        turns = regional[piece.kind][0]
    elif piece.kind == "close":
        n = int(piece.key.rsplit("_", 1)[1]) - 1
        turns = CLOSE_TEMPLATES[n % len(CLOSE_TEMPLATES)]
    elif piece.kind == "tease":
        pool = TEASE_TEMPLATES[_tone_family(piece.section)]
        turns = pool[int(hashlib.sha1(piece.headline.encode()).hexdigest(), 16) % len(pool)]
    else:
        turns = BRIDGE_TEMPLATES[_tone_family(piece.section)]
    return Written(_fill(list(turns), hosts, piece))


def _collect(data: dict, pieces: list[Piece], model: str,
             hosts: tuple[str, str] = ("Matthew", "Kelly")) -> dict[str, Written]:
    out: dict[str, Written] = {}
    for p in pieces:
        if p.kind.startswith("open_"):
            raw = data.get(p.kind)
            if isinstance(raw, list) and raw and isinstance(raw[0], list):
                raw = raw[0]
        elif p.kind in ("open", "close"):
            variants = data.get(p.kind)
            n = int(p.key.rsplit("_", 1)[1]) - 1
            raw = variants[n] if isinstance(variants, list) and n < len(variants) else None
        else:
            group = data.get(p.kind)
            raw = group.get(p.section) if isinstance(group, dict) else None
        turns = validate_turns(raw, p.kind, p.section, hosts=hosts)
        if turns:
            out[p.key] = Written(turns, model)
    return out


def ask_ai(cfg, pieces: list[Piece], hosts: tuple[str, str], day: str, *,
           client: httpx.Client | None = None,
           yesterdays_opening: str | None = None) -> tuple[dict[str, Written], list[str]]:
    """One AI call for the whole day's banter pieces; falls back gracefully on any failure."""
    problems: list[str] = []
    models = llm.ai_provider_chain(cfg, bin_lookup=_agy_bin)
    if not models:
        return {}, ["no AI key configured"]

    sections = {
        p.section: {
            "title": topics.ALL_SECTIONS[p.section]["title"],
            "tone": TONE.get(topics.base_section(p.section), "neutral"),
            "headline": p.headline,
            "summary": p.summary,
        }
        for p in pieces if p.kind == "tease"
    }
    weekday = _date.fromisoformat(day).strftime("%A")
    payload: dict = {
        "date": day,
        "day_of_week": weekday,
        "sections": sections,
        "category_bridge_rules": (
            "CRITICAL CATEGORY ALIGNMENT: bridge[X] MUST strictly be the spoken transition ENTERING AND INTRODUCING section X. "
            "For example, bridge['science'] MUST introduce Science and NEVER mention sports. "
            "bridge['sports'] MUST introduce Sports and NEVER mention science or top headlines."
        ),
    }
    if yesterdays_opening:
        payload["yesterdays_opening"] = yesterdays_opening

    own = client is None
    client = client or httpx.Client(timeout=60)
    try:
        for model, url, token, provider in models:
            messages = [
                {"role": "system", "content": _prompt(hosts, weekday)},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
            try:
                raw_text = llm.generate_chat_text(
                    client, model=model, url=url, token=token, provider=provider,
                    messages=messages, temperature=0.75, max_tokens=3000,
                    cli_timeout=60.0, bin_lookup=_agy_bin,
                )
                data = json.loads(raw_text)
                if not isinstance(data, dict):
                    raise ValueError("not a JSON object")
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
                problems.append(f"{provider} {model}: {exc.__class__.__name__}: {str(exc)[:120]}")
                log.warning("Podcast banter %s (%s) failed, trying next provider: %s",
                            provider, model, exc.__class__.__name__)
                continue
            return _collect(data, pieces, model, hosts), problems
    finally:
        if own:
            client.close()
    log.warning("All %d podcast banter provider(s) failed (%d recorded problem(s))", len(models), len(problems))
    return {}, problems


def write_pieces(cfg, pieces: list[Piece], hosts: tuple[str, str], day: str, *,
                 client: httpx.Client | None = None,
                 yesterdays_opening: str | None = None) -> tuple[dict[str, Written], list[str]]:
    """Every piece gets lines: the AI's when valid, the template's otherwise."""
    try:
        written, problems = ask_ai(cfg, pieces, hosts, day, client=client, yesterdays_opening=yesterdays_opening)
    except Exception as exc:  # noqa: BLE001 - banter must never take the pack down
        written, problems = {}, [f"AI stage crashed: {exc.__class__.__name__}: {exc}"[:200]]
    for p in pieces:
        if p.key not in written:
            written[p.key] = template_piece(p, hosts)
    return written, problems


def scripts_from_pack(store, day: str) -> list[dict]:
    """Build script stubs from already-published ``story_audio`` rows so banter can be rebuilt alone."""
    seen: dict[tuple[str, int], dict] = {}
    for r in sorted(store.select("story_audio", {"date": f"eq.{day}"}), key=lambda r: (r["section"], r["rank"])):
        seen.setdefault((r["section"], r["rank"]), {
            "section": r["section"], "rank": r["rank"], "title": r.get("title", ""),
            "summary": _clip_summary(r.get("script", "")),
        })
    return list(seen.values())


def host_pair(cfg) -> tuple[str, str] | None:
    return tuple(cfg.podcast_hosts) if len(cfg.podcast_hosts) == 2 else None  # type: ignore[return-value]


def fetch_yesterdays_opening(store, day: str, hosts_id: str) -> str | None:
    """Fetch the most recent prior day's pod_open_1 transcript so today's opening never repeats it."""
    try:
        rows = store.select("podcast_clips", {"date": f"lt.{day}", "hosts": f"eq.{hosts_id}", "clip_key": "eq.pod_open_1"})
        if not rows:
            return None
        latest = max(rows, key=lambda r: str(r.get("date") or ""))
        return str(latest.get("text") or "").strip() or None
    except Exception:
        return None


async def build_podcast(cfg, store, scripts: list[dict], *, day: str, base: str,
                        force: bool = False, client: httpx.Client | None = None) -> list[dict]:
    """Voice and publish the day's banter. Returns the published rows ([] when the mode is off)."""
    from . import storypack

    if not cfg.podcast_enabled:
        return []
    pair = host_pair(cfg)
    if not pair:
        raise PodcastIncomplete(f"PODCAST_HOSTS needs exactly two voice ids, got {list(cfg.podcast_hosts)}")
    hosts_id = "+".join(pair)
    names = (storypack.voice_name(pair[0]).split()[0], storypack.voice_name(pair[1]).split()[0])

    yesterdays_opening = fetch_yesterdays_opening(store, day, hosts_id)
    pieces = plan_pieces(scripts)
    written, problems = await asyncio.to_thread(
        write_pieces, cfg, pieces, names, day, client=client, yesterdays_opening=yesterdays_opening
    )
    for problem in problems:
        log.warning("podcast writer: %s", problem)

    existing = {r["clip_key"]: r for r in store.select("podcast_clips", {"date": f"eq.{day}", "hosts": f"eq.{hosts_id}"})}
    rows: list[dict] = []
    failed: list[str] = []
    async with httpx.AsyncClient(timeout=180) as http:
        for p in pieces:
            w = written[p.key]
            text = transcript(w.turns, names)
            have = existing.get(p.key)
            if not force and have and have.get("text") == text and have.get("audio_path"):
                rows.append(have)
                continue
            try:
                raw_turns: list[tuple[bytes, float, float]] = []
                for who, line in w.turns:
                    clean_line = strip_speaker_prefix(line, names) or line
                    raw_audio, seconds = await storypack.synthesise(http, base, clean_line, pair[who])
                    raw_turns.append((raw_audio, seconds, 0.35))
                data, total, _ = await asyncio.to_thread(stitch_turn_audio, raw_turns)
                path = f"podcast/{day}/{p.key}-{hosts_id.replace('+', '__')}-{hashlib.sha256(data).hexdigest()[:8]}.mp3"
                await asyncio.to_thread(storypack._publish_audio_file, store, path, data)
                row = {"date": day, "hosts": hosts_id, "clip_key": p.key, "text": text,
                       "duration": round(total, 3), "audio_path": path, "writer": w.writer}
                store.insert("podcast_clips", row, on_conflict="date,hosts,clip_key")
                rows.append(row)
                log.info("[podcast] %-22s %5.1fs (%s)", p.key, total, w.writer)
            except Exception as exc:  # noqa: BLE001 - one piece's failure skips that piece only
                if isinstance(exc, storypack.VoiceServiceDown):
                    failed.append(f"{p.key}: voice service down")
                    break
                failed.append(f"{p.key}: {exc.__class__.__name__}: {exc}"[:200])

    keys = {r["clip_key"] for r in rows}
    if any(k.startswith("pod_open_") for k in keys) and any(k.startswith("pod_close_") for k in keys):
        store.insert("podcast_clips", {
            "date": day, "hosts": hosts_id, "clip_key": READY_KEY, "text": f"{len(rows)} pieces",
            "duration": 0, "audio_path": f"podcast/{day}/{READY_KEY}-{hosts_id.replace('+', '__')}.mp3",
            "writer": "marker"}, on_conflict="date,hosts,clip_key")
    else:
        store.delete("podcast_clips", {"date": f"eq.{day}", "hosts": f"eq.{hosts_id}", "clip_key": f"eq.{READY_KEY}"})
        failed.append("no complete opening and closing: podcast not marked ready")
    if failed:
        raise PodcastIncomplete("; ".join(failed)[:600])
    return rows
