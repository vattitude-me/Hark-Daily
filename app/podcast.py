"""Podcast mode: two hosts chat around the day's news.

The stories themselves are voiced by the normal narrator clips. This module writes and voices the
*banter between them*, as small pieces that every listener shares:

    pod_open_<n>        greeting chat, no news in it (a few variants so mornings differ)
    pod_tease_<section> reaction to that section's top headline ("big day for AI...")
    pod_bridge_<sec>    one or two lines leading into that section's stories
    pod_close_<n>       short sign-off chat

The browser strings together the pieces that match a listener's lineup, so a listener with three
categories gets a shorter, matching chat than one with seven. Banter is optional: the stories never
depend on it, so every failure here degrades to "fewer pieces" or "no podcast", never to "no brief".

Lines come from the same AI chain as the story copy (Gemini, then Groq) in a single call for the
whole day, each piece is validated on its own, and any piece the AI got wrong, or the whole set if the
AI is down, is replaced from the template pools below. The templates always ship.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date as _date
from pathlib import Path
import time

import httpx

from . import audio, topics
from .summarizer import drop_boilerplate
from .tts import SAMPLE_RATE
from .writer import GEMINI_URL, GROQ_URL, _retry_after

log = logging.getLogger(__name__)

OPEN_VARIANTS = 3
CLOSE_VARIANTS = 2
READY_KEY = "podcast_ready"

# Word caps per piece keep the whole chat to roughly 60-90 seconds: news is the priority.
MAX_WORDS = {"open": 40, "tease": 35, "bridge": 18, "close": 28}
MAX_TURNS = {"open": 4, "tease": 3, "bridge": 2, "close": 3}

# How each section should sound, for the AI prompt and the template pools.
TONE = {
    "top": "serious but warm",
    "ai": "curious and excited",
    "tech": "upbeat and practical",
    "politics": "measured and serious",
    "entertainment": "light and playful",
    "science": "curious and wondering",
    "sports": "energetic",
}

# Chatterbox performs these itself when they appear in the text, which sounds far more human than
# punctuation can (voice_service/turbo_voice/text.py lists the same set). Anything else in square
# brackets is rejected so a typo never gets read aloud.
TAGS = ("laugh", "chuckle", "sigh", "cough", "gasp", "groan", "sniffle", "yawn")
MAX_TAGS = 2
# Sections where a laugh or a sigh would be in poor taste: tags are stripped from their banter.
SOBER_SECTIONS = frozenset({"top", "politics"})
_TAG = re.compile(r"\[(" + "|".join(TAGS) + r")\]", re.I)

Turn = tuple[int, str]  # (0 or 1 for host A or B, text, which may carry [tags])


@dataclass
class Piece:
    key: str
    kind: str                      # open | tease | bridge | close
    section: str | None = None
    headline: str = ""
    summary: str = ""


@dataclass
class Written:
    turns: list[Turn]
    writer: str = "built-in"


def piece_key(kind: str, n: int | str) -> str:
    return f"pod_{kind}_{n}"


# ------------------------------------------------------------------ catalogue
def plan_pieces(scripts: list[dict]) -> list[Piece]:
    """The pieces the day needs: variants of open/close plus a tease and bridge per section.

    A section's tease is about its rank-1 story, which every lineup that includes the section plays."""
    pieces = [Piece(piece_key("open", i + 1), "open") for i in range(OPEN_VARIANTS)]
    top: dict[str, dict] = {}
    for s in scripts:
        sec = s.get("section")
        if sec in topics.ALL_SECTIONS and (sec not in top or s.get("rank", 99) < top[sec].get("rank", 99)):
            top[sec] = s
    for sec, story in top.items():
        pieces.append(Piece(piece_key("tease", sec), "tease", sec,
                            _clean(story.get("title", "")), _clean(story.get("summary", ""))[:300]))
        pieces.append(Piece(piece_key("bridge", sec), "bridge", sec, _clean(story.get("title", ""))))
    pieces += [Piece(piece_key("close", i + 1), "close") for i in range(CLOSE_VARIANTS)]
    return pieces


def _clean(text: str) -> str:
    s = str(text or "")
    s = re.sub(r"\s*[—–]\s*", ", ", s)
    s = re.sub(r"\s+-\s+", ", ", s)
    s = re.sub(r",\s*,+", ",", s)
    s = re.sub(r",\s*([.!?])", r"\1", s)
    return " ".join(s.split())


# ------------------------------------------------------------------ templates
# {a} and {b} are the hosts' first names, {h} the headline, {s} the section's title.
OPEN_TEMPLATES: list[list[Turn]] = [
    [(0, "Hey {b}."),
     (1, "Hey {a}. What's on your radar today?"),
     (0, "A few big stories just broke. Let's take a look.")],
    [(0, "Hey {b}, good to see you."),
     (1, "Good to see you too, {a}. What are we tracking today?"),
     (0, "Quite a bit. Let's start with the top story.")],
    [(0, "Welcome back everyone, and hey {b}."),
     (1, "Hey {a}. Ready when you are."),
     (0, "Great. Let's get into what's happening.")],
]
CLOSE_TEMPLATES: list[list[Turn]] = [
    [(1, "And that is our look at the news for today."),
     (0, "Thanks for listening. We'll talk to you on the next update.")],
    [(0, "That covers the main stories today."),
     (1, "[chuckle] Take care, stay informed, and we'll catch you next time.")],
]
TEASE_TEMPLATES: dict[str, list[list[Turn]]] = {
    "serious": [[(0, "Here's an important story we're following: {h}."), (1, "Yeah, this one matters... here are the details.")]],
    "warm": [[(0, "In the headlines today: {h}."), (1, "Here's the background on what happened.")]],
    "excited": [[(0, "Take a look at this in {s}: {h}."), (1, "[chuckle] Yeah, this caught a lot of attention today.")]],
    "light": [[(0, "Here's an interesting one in {s}: {h}."), (1, "[laugh] Let's see what happened here.")]],
    "energetic": [[(0, "In {s} today: {h}."), (1, "Here's what you need to know.")]],
    "curious": [[(0, "This is an interesting one: {h}."), (1, "Yeah, let's look at the details.")]],
}
BRIDGE_TEMPLATES: dict[str, list[Turn]] = {
    "serious": [(0, "Here is the lead story.")],
    "warm": [(0, "Here are the top stories.")],
    "excited": [(1, "Now to {s}.")],
    "light": [(1, "Moving on to {s}.")],
    "energetic": [(1, "Here's the latest in {s}.")],
    "curious": [(1, "Next up, {s}.")],
}


def _tone_family(section: str | None) -> str:
    base = (section or "").replace("_us", "").replace("_in", "").replace("_ca", "")
    return {"top": "warm", "politics": "serious", "ai": "excited", "tech": "excited",
            "entertainment": "light", "science": "curious", "sports": "energetic"}.get(base, "warm")


def _fill(turns: list[Turn], hosts: tuple[str, str], piece: Piece) -> list[Turn]:
    title = topics.ALL_SECTIONS.get(piece.section or "", {}).get("title", "the news")
    headline = piece.headline.rstrip(".")
    if len(headline) > 110:
        headline = headline[:107].rsplit(" ", 1)[0] + "..."
    filled = [(who, text.format(a=hosts[0], b=hosts[1], h=headline, s=title)) for who, text in turns]
    base_sec = (piece.section or "").replace("_us", "").replace("_in", "").replace("_ca", "")
    return [(who, strip_tags(text)) for who, text in filled] if base_sec in SOBER_SECTIONS else filled


def template_piece(piece: Piece, hosts: tuple[str, str]) -> Written:
    """The guaranteed fallback. Variants rotate by position so open/close pieces differ."""
    if piece.kind == "open":
        n = int(piece.key.rsplit("_", 1)[1]) - 1
        turns = OPEN_TEMPLATES[n % len(OPEN_TEMPLATES)]
    elif piece.kind == "close":
        n = int(piece.key.rsplit("_", 1)[1]) - 1
        turns = CLOSE_TEMPLATES[n % len(CLOSE_TEMPLATES)]
    elif piece.kind == "tease":
        pool = TEASE_TEMPLATES[_tone_family(piece.section)]
        turns = pool[int(hashlib.sha1(piece.headline.encode()).hexdigest(), 16) % len(pool)]
    else:
        turns = BRIDGE_TEMPLATES[_tone_family(piece.section)]
    return Written(_fill(list(turns), hosts, piece))


# ------------------------------------------------------------------ validation & anti-slop
_BAD = re.compile(r"https?://|www\.|[*_#`<>\[\]{}]|\bhttp", re.I)

SLOP_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:let's|lets)\s+roll\b", re.I), "let's get started"),
    (re.compile(r"\ba\s+whirlwind\s+of\s+a\s+(?:day|week|news cycle)\b", re.I), "a busy day"),
    (re.compile(r"\ba\s+whirlwind\b", re.I), "a lot happening"),
    (re.compile(r"\b(?:let's|lets)\s+dive\s+(?:right\s+)?in(?:to)?\b", re.I), "let's look at"),
    (re.compile(r"\bdive\s+into\b", re.I), "look at"),
    (re.compile(r"\bdeep\s+dive\b", re.I), "closer look"),
    (re.compile(r"\bunpack\s+this\b", re.I), "break this down"),
    (re.compile(r"\bquite\s+a\s+lot\s+to\s+unpack\b", re.I), "a lot of details here"),
    (re.compile(r"\bunpack\b", re.I), "explain"),
    (re.compile(r"\bdelve\s+into\b", re.I), "look into"),
    (re.compile(r"\bdelve\b", re.I), "look"),
    (re.compile(r"\bbuckle\s+up\b", re.I), "so"),
    (re.compile(r"\bwithout\s+further\s+ado\b", re.I), "first off"),
    (re.compile(r"\ba\s+lot\s+of\s+ground\s+to\s+cover\b", re.I), "a lot to cover"),
    (re.compile(r"\bfast[- ]moving\b", re.I), "busy"),
    (re.compile(r"\bmoving\s+across\s+the\s+board\b", re.I), "developing today"),
    (re.compile(r"\bwhat's\s+buzzing\s+in\b", re.I), "the latest in"),
    (re.compile(r"\bgame[- ]changer\b", re.I), "big deal"),
    (re.compile(r"\bneedless\s+to\s+say\b", re.I), "of course"),
]


def _preserve_case(match: re.Match, replacement: str) -> str:
    text = match.group(0)
    if text and text[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def clean_slop(text: str) -> str:
    """Strip or normalize robotic AI slop phrases into simple, natural spoken English."""
    cleaned = text
    for pattern, repl in SLOP_PATTERNS:
        cleaned = pattern.sub(lambda m, r=repl: _preserve_case(m, r), cleaned)
    return " ".join(cleaned.split())


def strip_tags(text: str) -> str:
    """The words alone, for captions, word counts and sober sections."""
    return _clean(_TAG.sub(" ", text))


def validate_turns(raw, kind: str, section: str | None = None) -> list[Turn] | None:
    """Turn the AI's JSON for one piece into clean turns, or None if any rule is broken.

    Known Chatterbox tags are kept (at most MAX_TAGS a piece), except in sober sections where
    they are removed; any other bracketed text rejects the piece."""
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_TURNS[kind]:
        return None
    turns: list[Turn] = []
    words = tags = 0
    for item in raw:
        if not isinstance(item, dict):
            return None
        who = str(item.get("speaker", "")).strip().lower()
        text = _clean(item.get("text", ""))
        text = _clean(_TAG.sub(lambda m: f"[{m.group(1).lower()}]", text))
        text = clean_slop(text)
        words_only = strip_tags(text)
        if who not in ("a", "b") or not words_only or _BAD.search(words_only):
            return None
        tags += len(_TAG.findall(text))
        base_sec = (section or "").replace("_us", "").replace("_in", "").replace("_ca", "")
        if base_sec in SOBER_SECTIONS:
            text = words_only
        words += len(words_only.split())
        turns.append((0 if who == "a" else 1, text))
    if words > MAX_WORDS[kind] or tags > MAX_TAGS:
        return None
    return turns


# ------------------------------------------------------------------ AI writer
SYSTEM_PROMPT = """You write simple, natural, conversational banter for a two-host news podcast. The hosts introduce and react to the day's news; a separate narrator reads the stories in full, so you never read the news yourself.

Hosts: "a" is {a} and "b" is {b}.
Tone & Register: Two smart, grounded friends talking over coffee. Simple, honest, everyday spoken English.

STRICT ANTI-SLOP RULES (ZERO AI JARGON OR HYPE):
- Speak like real human beings, NOT morning radio DJs, TV hype-men, or AI bots.
- BANNED CLICHÉS (NEVER USE ANY OF THESE):
  "let's roll", "whirlwind", "buckle up", "dive into", "dive in", "deep dive", "unpack", "delve", "fast-moving", "ground to cover", "buzzing", "wild ride", "nuts and bolts", "without further ado", "what a day", "packed day", "game-changer", "moving across the board".
- Keep language plain, simple, and direct. Avoid breathless hype, exaggerated drama, and corporate buzzwords.
- Use natural contractions ("we've", "it's", "that's", "don't", "can't").
- Pacing: use short sentences and natural commas or ellipses `...` where a person would take a breath.
- Use paralinguistic voice tags sparingly and naturally: [chuckle], [laugh], [sigh], [gasp]. At most {max_tags} tags per piece. Do not use tags on tragedy, death, or severe hardship.

Return ONLY JSON of this shape:
{{"open": [turns, ...{open_n} variants], "close": [turns, ...{close_n} variants],
 "tease": {{"<section>": turns}}, "bridge": {{"<section>": turns}}}}
where turns is a list of {{"speaker": "a" or "b", "text": "..."}}.

Rules:
- open: an easy-going, time-neutral greeting between two friends ("Hey {b}. Good to see you.", "Welcome back, {b}. A lot of news to catch up on."). Today is {weekday}. No news yet. Make the {open_n} variants clearly distinct and relaxed. IMPORTANT: Do NOT use time-of-day locked words like "morning", "afternoon", "evening", or "morning coffee".
- close: an easy-going, friendly sign-off ("That covers the main headlines for today. Thanks for listening.", "Stay safe, stay curious, and we will talk to you next time."). Make variants distinct. Do NOT say "tomorrow morning" or "morning brief".
- tease: react simply and honestly to the top headline of that section ("Did you see this one in AI?", "This score in sports caught a lot of people off guard..."). Do NOT say "this morning".
- bridge: a clean, direct 1-line handoff into that section ("Here is the top story.", "Moving over to politics.").
- Limits per piece: open <= {w_open} words and 4 turns, tease <= {w_tease} words and 3 turns, bridge <= {w_bridge} words and 2 turns, close <= {w_close} words and 3 turns.
- No URLs, emoji, lists, markdown or stage directions. Paraphrase headlines naturally.
- The tone of each section is guidance for how you sound; never say the tone words themselves ("curious", "serious", "energetic").
- Stay respectful on sensitive stories: no jokes about tragedies."""


def _prompt(hosts: tuple[str, str], weekday: str) -> str:
    return SYSTEM_PROMPT.format(
        a=hosts[0], b=hosts[1], weekday=weekday, open_n=OPEN_VARIANTS, close_n=CLOSE_VARIANTS,
        w_open=MAX_WORDS["open"], w_tease=MAX_WORDS["tease"], w_bridge=MAX_WORDS["bridge"], w_close=MAX_WORDS["close"], max_tags=MAX_TAGS)


def _ai_provider_chain(cfg) -> list[tuple[str, str, str, str]]:
    """Ordered (model, url, token, provider_label) chain: Groq first, then local LLM, then Gemini."""
    models: list[tuple[str, str, str, str]] = []
    if getattr(cfg, "groq_api_key", None):
        models += [(m, GROQ_URL, cfg.groq_api_key, "Groq") for m in cfg.groq_models]
    if getattr(cfg, "local_llm_url", None):
        models.append((getattr(cfg, "local_llm_model", "llama3.1:8b"), cfg.local_llm_url, "local", "LocalLLM"))
    if getattr(cfg, "gemini_api_key", None):
        models += [(m, GEMINI_URL, cfg.gemini_api_key, "Gemini") for m in cfg.gemini_models]
    return models


def ask_ai(cfg, pieces: list[Piece], hosts: tuple[str, str], day: str, *,
           client: httpx.Client | None = None) -> tuple[dict[str, Written], list[str]]:
    """One AI call for the whole day. Returns the valid pieces by key and a list of problems.

    Tries each Groq, local, then Gemini model once; the first answer that parses wins. Never raises:
    a down or rate-limited service just yields nothing, and the caller fills in from templates."""
    problems: list[str] = []
    models = _ai_provider_chain(cfg)
    if not models:
        return {}, ["no AI key configured"]

    sections = {p.section: {"title": topics.ALL_SECTIONS[p.section]["title"],
                            "tone": TONE.get((p.section or "").replace("_us", "").replace("_in", "").replace("_ca", ""), "neutral"),
                            "headline": p.headline, "summary": p.summary}
                for p in pieces if p.kind == "tease"}
    weekday = _date.fromisoformat(day).strftime("%A")
    payload = {"sections": sections}
    own = client is None
    client = client or httpx.Client(timeout=60)
    try:
        for model, url, token, provider in models:
            body = {
                "model": model, "temperature": 0.75, "max_tokens": 3000,
                "response_format": {"type": "json_object"},
                **({"reasoning_effort": "low"} if model.startswith("openai/gpt-oss") else {}),
                "messages": [{"role": "system", "content": _prompt(hosts, weekday)},
                             {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            }
            try:
                resp = client.post(url, json=body, headers={"Authorization": f"Bearer {token}"})
                resp.raise_for_status()
                data = json.loads(resp.json()["choices"][0]["message"]["content"])
                if not isinstance(data, dict):
                    raise ValueError("not a JSON object")
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                problems.append(f"{provider} {model}: {exc.__class__.__name__}: {str(exc)[:120]}")
                continue
            return _collect(data, pieces, model), problems
    finally:
        if own:
            client.close()
    return {}, problems


def _collect(data: dict, pieces: list[Piece], model: str) -> dict[str, Written]:
    out: dict[str, Written] = {}
    for p in pieces:
        if p.kind in ("open", "close"):
            variants = data.get(p.kind)
            n = int(p.key.rsplit("_", 1)[1]) - 1
            raw = variants[n] if isinstance(variants, list) and n < len(variants) else None
        else:
            group = data.get(p.kind)
            raw = group.get(p.section) if isinstance(group, dict) else None
        turns = validate_turns(raw, p.kind, p.section)
        if turns:
            out[p.key] = Written(turns, model)
    return out


def write_pieces(cfg, pieces: list[Piece], hosts: tuple[str, str], day: str, *,
                 client: httpx.Client | None = None) -> tuple[dict[str, Written], list[str]]:
    """Every piece gets lines: the AI's when valid, the template's otherwise."""
    try:
        written, problems = ask_ai(cfg, pieces, hosts, day, client=client)
    except Exception as exc:  # noqa: BLE001 - banter must never take the pack down
        written, problems = {}, [f"AI stage crashed: {exc.__class__.__name__}: {exc}"[:200]]
    for p in pieces:
        if p.key not in written:
            written[p.key] = template_piece(p, hosts)
    return written, problems


def scripts_from_pack(store, day: str) -> list[dict]:
    """The day's already-published stories as pack scripts, so banter can be (re)built on its own.

    Every narrator voices the same stories, so one set of rows per (section, rank) is enough."""
    seen: dict[tuple[str, int], dict] = {}
    for r in sorted(store.select("story_audio", {"date": f"eq.{day}"}), key=lambda r: (r["section"], r["rank"])):
        seen.setdefault((r["section"], r["rank"]), {
            "section": r["section"], "rank": r["rank"], "title": r.get("title", ""),
            "summary": _clean(r.get("script", ""))[:300]})
    return list(seen.values())


# ------------------------------------------------------------------ audio
class PodcastIncomplete(Exception):
    """Some pieces could not be published. The brief itself is unaffected."""


def host_pair(cfg) -> tuple[str, str] | None:
    return tuple(cfg.podcast_hosts) if len(cfg.podcast_hosts) == 2 else None  # type: ignore[return-value]


def transcript(turns: list[Turn]) -> str:
    return "\n".join(strip_tags(text) for _, text in turns)


def stitch_turn_audio(
    raw_turns: list[tuple[bytes, float, float]],
    sr: int = SAMPLE_RATE,
) -> tuple[bytes, float, list[tuple[float, float]]]:
    """Decode each turn's audio bytes, stitch with PCM silence, and encode once to MP3.

    ``raw_turns`` is a list of ``(audio_bytes, reported_duration, pause_after_sec)``.
    Returns ``(mp3_bytes, total_duration_sec, [(start_sec, end_sec), ...])``.
    """
    decoded: list[tuple] = []
    for raw_bytes, dur, pause_after in raw_turns:
        pcm = audio.decode_audio(raw_bytes, sr=sr, fallback_duration=dur or 1.2)
        decoded.append((pcm, pause_after))
    combined, marks = audio.stitch_turns(decoded, sr=sr)
    mp3_bytes = audio.encode_mp3(combined, sr=sr)
    total_sec = round(combined.size / sr, 3)
    return mp3_bytes, total_sec, marks


async def build_podcast(cfg, store, scripts: list[dict], *, day: str, base: str,
                        force: bool = False, client: httpx.Client | None = None) -> list[dict]:
    """Voice and publish the day's banter. Returns the published rows ([] when the mode is off).

    Pieces already published with the same lines are reused. A piece whose speech fails is skipped.
    The day is marked ready only once there is at least one opening and one closing, so a listener
    never gets a chat with no beginning or end. Raises PodcastIncomplete after publishing what it
    could if anything was skipped; the caller treats that as a warning."""
    from .storypack import _publish_audio_file, synthesise, voice_name  # lazy: storypack imports us

    if not cfg.podcast_enabled:
        return []
    pair = host_pair(cfg)
    if not pair:
        raise PodcastIncomplete(f"PODCAST_HOSTS needs exactly two voice ids, got {list(cfg.podcast_hosts)}")
    hosts_id = "+".join(pair)
    names = (voice_name(pair[0]).split()[0], voice_name(pair[1]).split()[0])

    pieces = plan_pieces(scripts)
    written, problems = await asyncio.to_thread(write_pieces, cfg, pieces, names, day, client=client)
    for problem in problems:
        log.warning("podcast writer: %s", problem)

    existing = {r["clip_key"]: r for r in store.select(
        "podcast_clips", {"date": f"eq.{day}", "hosts": f"eq.{hosts_id}"})}
    rows: list[dict] = []
    failed: list[str] = []
    async with httpx.AsyncClient(timeout=180) as http:
        for p in pieces:
            w = written[p.key]
            text = transcript(w.turns)
            have = existing.get(p.key)
            if not force and have and have.get("text") == text and have.get("audio_path"):
                rows.append(have)
                continue
            try:
                raw_turns: list[tuple[bytes, float, float]] = []
                for who, line in w.turns:
                    raw_audio, seconds = await synthesise(http, base, line, pair[who])
                    raw_turns.append((raw_audio, seconds, 0.35))
                data, total, _ = await asyncio.to_thread(stitch_turn_audio, raw_turns)
                path = f"podcast/{day}/{p.key}-{hosts_id.replace('+', '__')}-{hashlib.sha256(data).hexdigest()[:8]}.mp3"
                await asyncio.to_thread(_publish_audio_file, store, path, data)
                row = {"date": day, "hosts": hosts_id, "clip_key": p.key, "text": text,
                       "duration": round(total, 3), "audio_path": path, "writer": w.writer}
                store.insert("podcast_clips", row, on_conflict="date,hosts,clip_key")
                rows.append(row)
                log.info("[podcast] %-22s %5.1fs (%s)", p.key, total, w.writer)
            except Exception as exc:  # noqa: BLE001 - one piece's failure skips that piece only
                from .storypack import VoiceServiceDown
                if isinstance(exc, VoiceServiceDown):
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


# ------------------------------------------------------------------ Two-Host Story Dialogue Engine
STORY_DIALOGUE_VERSION = "v2"
PURPOSE_PAUSES: dict[str, float] = {
    "lead": 0.44,
    "question": 0.56,
    "context": 0.42,
    "implication": 0.46,
    "takeaway": 0.50,
}
VALID_PURPOSES = frozenset(PURPOSE_PAUSES)


@dataclass
class DialogueTurn:
    speaker: int                  # 0 for Host A (Matthew), 1 for Host B (Kelly)
    text: str                     # spoken text (may include valid Chatterbox tags in non-sober sections)
    purpose: str = "context"      # lead | question | context | implication | takeaway
    fact_refs: list[str] = field(default_factory=list)
    pause_after: float = 0.36


@dataclass
class StoryDialogue:
    story_id: str
    section: str
    headline: str
    summary: str
    turns: list[DialogueTurn]
    writer: str = "built-in"


def _split_sentences(text: str) -> list[str]:
    cleaned = _clean(drop_boilerplate(text) or text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", cleaned)
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        s = _clean(p).strip()
        if len(s.split()) < 4:
            continue
        key = s.lower()
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def build_story_brief(story: dict) -> dict:
    """Extract a grounded factual brief (F1..Fn) from an enriched story dict."""
    sec = str(story.get("section") or "top")
    base_sec = sec.replace("_us", "").replace("_in", "").replace("_ca", "")
    headline = _clean(story.get("title") or story.get("headline") or "").rstrip(".")
    source = _clean(story.get("source") or "News wire")
    summary = _clean(story.get("summary") or "")
    raw_body = str(story.get("article_text") or story.get("summary") or story.get("script") or "")

    candidates = _split_sentences(raw_body)
    if summary:
        for s in _split_sentences(summary):
            if s.lower() not in {c.lower() for c in candidates}:
                candidates.insert(0, s)

    head_norm = headline.lower()
    facts: list[dict[str, str]] = []
    if headline:
        facts.append({"id": "F1", "fact": f"{headline}."})
    for sent in candidates:
        if sent.lower().rstrip(".") == head_norm:
            continue
        fid = f"F{len(facts) + 1}"
        facts.append({"id": fid, "fact": sent})
        if len(facts) >= 6:
            break

    if len(facts) == 1 and summary and summary.lower().rstrip(".") != head_norm:
        facts.append({"id": "F2", "fact": summary if summary.endswith((".", "!", "?")) else f"{summary}."})

    return {
        "story_id": str(story.get("id") or story.get("url") or f"{sec}-{story.get('rank', 1)}"),
        "section": sec,
        "section_title": topics.ALL_SECTIONS.get(sec, {}).get("title", sec.title()),
        "rank": int(story.get("rank") or 1),
        "headline": headline,
        "source": source,
        "summary": summary or headline,
        "tone": TONE.get(base_sec, "warm and informative"),
        "sober": base_sec in SOBER_SECTIONS,
        "facts": facts,
    }


def _speaker_index(raw_speaker: str, hosts: tuple[str, str] = ("Matthew", "Kelly")) -> int | None:
    s = str(raw_speaker or "").strip().lower()
    h0, h1 = hosts[0].lower(), hosts[1].lower()
    if s in ("a", "0", h0, f"{h0}_reference"):
        return 0
    if s in ("b", "1", h1, f"{h1}_reference"):
        return 1
    return None


def validate_story_dialogue(
    raw: dict | list | None,
    story_brief: dict,
    hosts: tuple[str, str] = ("Matthew", "Kelly"),
    *,
    min_turns: int = 3,
    max_turns: int = 6,
) -> list[DialogueTurn] | None:
    """Validate LLM-generated story dialogue turns against podcast editorial & TTS rules."""
    turns_raw = raw.get("turns") if isinstance(raw, dict) else raw
    if not isinstance(turns_raw, list) or not (min_turns <= len(turns_raw) <= max_turns):
        return None

    sober = bool(story_brief.get("sober"))
    valid_fact_ids = {f["id"] for f in story_brief.get("facts", []) if isinstance(f, dict) and "id" in f}
    parsed: list[DialogueTurn] = []
    total_words = 0
    total_tags = 0
    consecutive = 0
    last_speaker: int | None = None

    for item in turns_raw:
        if not isinstance(item, dict):
            return None
        who = _speaker_index(item.get("speaker", ""), hosts)
        if who is None:
            return None
        if who == last_speaker:
            consecutive += 1
            if consecutive > 2:
                return None
        else:
            consecutive = 1
            last_speaker = who

        text = _clean(item.get("text", ""))
        text = _clean(_TAG.sub(lambda m: f"[{m.group(1).lower()}]", text))
        text = clean_slop(text)
        words_only = strip_tags(text)
        word_count = len(words_only.split())
        if not words_only or word_count < 3 or word_count > 52 or _BAD.search(words_only):
            return None

        tags_in_turn = len(_TAG.findall(text))
        total_tags += tags_in_turn
        if sober:
            text = words_only

        purpose = str(item.get("purpose") or "context").strip().lower()
        if purpose not in VALID_PURPOSES:
            purpose = "context"

        raw_refs = item.get("fact_refs")
        fact_refs = [str(r).strip().upper() for r in raw_refs if str(r).strip()] if isinstance(raw_refs, list) else []
        if valid_fact_ids:
            fact_refs = [r for r in fact_refs if r in valid_fact_ids] or ["F1"]

        pause_after = PURPOSE_PAUSES.get(purpose, 0.36)
        total_words += word_count
        parsed.append(DialogueTurn(
            speaker=who,
            text=text,
            purpose=purpose,
            fact_refs=fact_refs,
            pause_after=pause_after,
        ))

    # Both hosts must participate, and total word budget must fit a crisp 20-45s segment
    speakers_used = {t.speaker for t in parsed}
    if len(speakers_used) < 2 or total_words < 20 or total_words > 190:
        return None
    if not sober and total_tags > MAX_TAGS:
        return None
    return parsed


STORY_DIALOGUE_PROMPT = """You write a simple, grounded, and natural conversation between two friends for ONE news story.

Hosts:
- "a" is {a} (introduces the news clearly and plainly, sharing the core facts without hype).
- "b" is {b} (the curious friend who asks the obvious question, reacts with genuine human emotion, or notes what it means).

STRICT ANTI-SLOP & PLAIN CONVERSATIONAL RULES:
1. Speak in plain, everyday conversational English. Talk like two friends chatting about an article they just read over lunch—NOT morning radio DJs, TV news anchors, or PR spokespeople.
2. BANNED AI CLICHÉS (NEVER USE ANY OF THESE):
   "let's roll", "whirlwind", "buckle up", "dive into", "dive in", "deep dive", "unpack", "delve", "game-changer", "tapestry", "beacon", "foster", "testament", "pivotal", "in today's world", "at the end of the day", "needless to say", "fast-moving", "without further ado", "wild ride", "mind-blowing", "ground to cover", "moving across the board".
3. Grounding: Stay 100% faithful to the supplied `facts` (`F1`, `F2`, ...). NEVER invent details, numbers, quotes, causes, or outcomes not present in `facts`.
4. Structure: 4 natural, punchy turns (60 to 120 words total across all turns):
   - Turn 1 ("purpose": "lead"): State what happened in one clear, simple sentence. No throat-clearing.
   - Turn 2 ("purpose": "question" or "context"): Ask a simple, direct question ("Wait, why did they do that?", "How much did they actually raise?") or react to fact F2.
   - Turn 3 ("purpose": "context" or "implication"): Explain the detail or number simply from fact F3 ("Well, according to the report...", "They're saying...").
   - Turn 4 ("purpose": "takeaway" or "implication"): Land what it means or what happens next in one grounded sentence ("Definitely something to keep an eye on.", "We will see how that plays out.").
5. Style & Pacing:
   - 8 to 22 words per turn. Keep sentences short and clear. Use everyday words instead of fancy vocabulary.
   - Use natural contractions ("don't", "can't", "it's", "they're", "we've").
   - Use natural commas and ellipses `...` where a speaker would take a breath.
   - No semicolons, colons, dashes, markdown, URLs, or quotation marks.
   - Avoid hollow filler ("That's so interesting", "Totally agree", "Great point"). Every turn must share a real fact or question.
   - Do NOT use time-of-day words ("this morning", "tonight").
   - Paralinguistic emotion tags: {tag_instruction}

Return ONLY valid JSON of this exact shape:
{{
  "summary": "1-2 sentence neutral card summary (30-50 words) built strictly from the facts",
  "turns": [
    {{"speaker": "a", "purpose": "lead", "fact_refs": ["F1"], "text": "..."}},
    {{"speaker": "b", "purpose": "context", "fact_refs": ["F2"], "text": "..."}},
    {{"speaker": "a", "purpose": "implication", "fact_refs": ["F3"], "text": "..."}},
    {{"speaker": "b", "purpose": "takeaway", "fact_refs": ["F2", "F3"], "text": "..."}}
  ]
}}"""


def fallback_story_dialogue(
    story: dict,
    hosts: tuple[str, str] = ("Matthew", "Kelly"),
) -> StoryDialogue:
    """Deterministic, strictly factual two-host exchange built from extracted article sentences."""
    brief = build_story_brief(story)
    facts = brief["facts"]
    lead_speaker = 0 if (brief["rank"] % 2 == 1) else 1
    co_speaker = 1 - lead_speaker
    source = brief["source"]
    headline = brief["headline"].rstrip(".")

    f1 = facts[0]["fact"] if facts else f"{headline}."
    f2 = facts[1]["fact"] if len(facts) > 1 else ""
    f3 = facts[2]["fact"] if len(facts) > 2 else ""
    f4 = facts[3]["fact"] if len(facts) > 3 else ""

    turns: list[DialogueTurn] = [
        DialogueTurn(
            speaker=lead_speaker,
            text=f1,
            purpose="lead",
            fact_refs=["F1"],
            pause_after=PURPOSE_PAUSES["lead"],
        ),
    ]
    if f2:
        turns.append(DialogueTurn(
            speaker=co_speaker,
            text=f2,
            purpose="context",
            fact_refs=["F2"],
            pause_after=PURPOSE_PAUSES["context"],
        ))
    else:
        turns.append(DialogueTurn(
            speaker=co_speaker,
            text=f"That comes from {source}, and it is one of the key developments we are tracking in {brief['section_title']}.",
            purpose="context",
            fact_refs=["F1"],
            pause_after=PURPOSE_PAUSES["context"],
        ))

    if f3:
        turns.append(DialogueTurn(
            speaker=lead_speaker,
            text=f3,
            purpose="implication",
            fact_refs=["F3"],
            pause_after=PURPOSE_PAUSES["implication"],
        ))
        takeaway_text = f4 if f4 else f"Reporting there from {source}."
        turns.append(DialogueTurn(
            speaker=co_speaker,
            text=takeaway_text,
            purpose="takeaway",
            fact_refs=["F4"] if f4 else ["F3"],
            pause_after=PURPOSE_PAUSES["takeaway"],
        ))
    else:
        turns.append(DialogueTurn(
            speaker=lead_speaker,
            text=f"Full details on that story are available from {source}.",
            purpose="takeaway",
            fact_refs=["F1"],
            pause_after=PURPOSE_PAUSES["takeaway"],
        ))

    return StoryDialogue(
        story_id=brief["story_id"],
        section=brief["section"],
        headline=brief["headline"],
        summary=brief["summary"],
        turns=turns,
        writer="built-in",
    )


def _dialogue_cache_path(cfg, brief: dict, hosts: tuple[str, str]) -> Path | None:
    cache_root = getattr(cfg, "cache_dir", None)
    if not cache_root:
        return None
    folder = Path(cache_root) / "story_dialogue"
    folder.mkdir(parents=True, exist_ok=True)
    fingerprint = json.dumps(
        {"v": STORY_DIALOGUE_VERSION, "hosts": hosts, "headline": brief["headline"], "facts": brief["facts"]},
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
    return folder / f"{digest}.{STORY_DIALOGUE_VERSION}.json"


def generate_story_dialogue(
    cfg,
    story: dict,
    hosts: tuple[str, str] = ("Matthew", "Kelly"),
    *,
    client: httpx.Client | None = None,
    force: bool = False,
    sleep=time.sleep,
) -> StoryDialogue:
    """Write a grounded two-host conversation for one story using Groq -> Local LLM -> Gemini -> fallback."""
    brief = build_story_brief(story)
    cache_path = _dialogue_cache_path(cfg, brief, hosts)
    if not force and cache_path and cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            turns = validate_story_dialogue(cached.get("turns"), brief, hosts)
            if turns:
                return StoryDialogue(
                    story_id=brief["story_id"],
                    section=brief["section"],
                    headline=brief["headline"],
                    summary=_clean(cached.get("summary") or brief["summary"]),
                    turns=turns,
                    writer=str(cached.get("writer") or "cached"),
                )
        except Exception:
            pass

    models = _ai_provider_chain(cfg)
    if not models:
        return fallback_story_dialogue(story, hosts)

    tag_instruction = (
        "Do NOT use any bracketed voice tags ([laugh], [chuckle], etc.) because this is a sober news section. Express gravity and warmth through thoughtful phrasing and `...` pauses."
        if brief["sober"]
        else "Include 1 to 2 natural Chatterbox emotion tags ([chuckle], [laugh], [sigh], or [gasp]) at the start of a reaction turn where it fits the story's mood."
    )
    sys_prompt = STORY_DIALOGUE_PROMPT.format(
        a=hosts[0],
        b=hosts[1],
        source=brief["source"],
        tag_instruction=tag_instruction,
    )
    user_payload = {
        "section": brief["section_title"],
        "tone": brief["tone"],
        "source": brief["source"],
        "headline": brief["headline"],
        "facts": brief["facts"],
    }

    own = client is None
    client = client or httpx.Client(timeout=60)
    try:
        for model, url, token, provider in models:
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ]
            for attempt in range(2):
                body = {
                    "model": model,
                    "temperature": 0.45 if attempt == 0 else 0.25,
                    "max_tokens": 1100,
                    "response_format": {"type": "json_object"},
                    **({"reasoning_effort": "low"} if model.startswith("openai/gpt-oss") else {}),
                    "messages": messages,
                }
                try:
                    resp = client.post(url, json=body, headers={"Authorization": f"Bearer {token}"})
                    if resp.status_code == 429:
                        wait = _retry_after(resp)
                        if wait <= 20 and attempt == 0:
                            sleep(wait + 0.5)
                            continue
                        break
                    resp.raise_for_status()
                    content = resp.json()["choices"][0]["message"]["content"]
                    data = json.loads(content)
                    if not isinstance(data, dict):
                        raise ValueError("response is not a JSON object")
                    turns = validate_story_dialogue(data, brief, hosts)
                    if not turns:
                        if attempt == 0:
                            messages.append({"role": "assistant", "content": content})
                            messages.append({
                                "role": "user",
                                "content": (
                                    "Repair the JSON: ensure 4 to 5 turns alternating between 'a' and 'b', "
                                    "8 to 26 words per turn, no dashes or special characters, and valid fact_refs."
                                ),
                            })
                            continue
                        break
                    summary = _clean(data.get("summary") or brief["summary"])
                    result = StoryDialogue(
                        story_id=brief["story_id"],
                        section=brief["section"],
                        headline=brief["headline"],
                        summary=summary,
                        turns=turns,
                        writer=model,
                    )
                    if cache_path:
                        try:
                            cache_path.write_text(
                                json.dumps(
                                    {
                                        "story_id": result.story_id,
                                        "section": result.section,
                                        "headline": result.headline,
                                        "summary": result.summary,
                                        "writer": result.writer,
                                        "turns": [
                                            {
                                                "speaker": "a" if t.speaker == 0 else "b",
                                                "purpose": t.purpose,
                                                "fact_refs": t.fact_refs,
                                                "text": t.text,
                                            }
                                            for t in result.turns
                                        ],
                                    },
                                    ensure_ascii=False,
                                    indent=2,
                                ),
                                encoding="utf-8",
                            )
                        except Exception:
                            pass
                    return result
                except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                    log.debug("story dialogue %s (%s) attempt %d failed: %s", provider, model, attempt + 1, exc)
                    continue
    finally:
        if own:
            client.close()

    return fallback_story_dialogue(story, hosts)


def format_dialogue_transcript(
    turns: list[DialogueTurn],
    hosts: tuple[str, str] = ("Matthew", "Kelly"),
) -> str:
    """Format two-host turns as speaker-labeled lines for ``story_audio.script`` and the UI teleprompter."""
    lines: list[str] = []
    for t in turns:
        speaker_name = hosts[t.speaker] if 0 <= t.speaker < len(hosts) else hosts[0]
        clean_line = strip_tags(t.text)
        if clean_line:
            lines.append(f"[{speaker_name}] {clean_line}")
    return "\n".join(lines)


async def synthesise_story_dialogue(
    http: httpx.AsyncClient,
    base: str,
    dialogue: StoryDialogue,
    host_voices: tuple[str, str],
    *,
    cache_dir: Path | None = None,
) -> tuple[bytes, float, list[tuple[float, float]]]:
    """Synthesize each turn of a StoryDialogue with Matthew & Kelly, cache per-turn audio, and stitch via PCM."""
    from .storypack import synthesise

    turn_cache: Path | None = None
    if cache_dir:
        turn_cache = Path(cache_dir) / "podcast_turns"
        turn_cache.mkdir(parents=True, exist_ok=True)

    raw_turns: list[tuple[bytes, float, float]] = []
    for turn in dialogue.turns:
        voice_id = host_voices[turn.speaker]
        key = hashlib.sha256(f"{voice_id}::{turn.text}".encode("utf-8")).hexdigest()[:16]
        cached_mp3 = turn_cache / f"{key}.mp3" if turn_cache else None
        cached_meta = turn_cache / f"{key}.json" if turn_cache else None

        if cached_mp3 and cached_mp3.is_file() and cached_meta and cached_meta.is_file():
            try:
                raw_audio = cached_mp3.read_bytes()
                seconds = float(json.loads(cached_meta.read_text(encoding="utf-8")).get("duration") or 1.2)
                raw_turns.append((raw_audio, seconds, turn.pause_after))
                continue
            except Exception:
                pass

        raw_audio, seconds = await synthesise(http, base, turn.text, voice_id)
        if cached_mp3 and cached_meta:
            try:
                cached_mp3.write_bytes(raw_audio)
                cached_meta.write_text(json.dumps({"duration": seconds, "voice": voice_id}), encoding="utf-8")
            except Exception:
                pass
        raw_turns.append((raw_audio, seconds, turn.pause_after))

    return await asyncio.to_thread(stitch_turn_audio, raw_turns)
