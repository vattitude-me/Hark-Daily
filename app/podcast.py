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
from dataclasses import dataclass
from datetime import date as _date

import httpx

from . import topics
from .writer import GEMINI_URL, GROQ_URL

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
        if sec in topics.SECTIONS and (sec not in top or s.get("rank", 99) < top[sec].get("rank", 99)):
            top[sec] = s
    for sec, story in top.items():
        pieces.append(Piece(piece_key("tease", sec), "tease", sec,
                            _clean(story.get("title", "")), _clean(story.get("summary", ""))[:300]))
        pieces.append(Piece(piece_key("bridge", sec), "bridge", sec, _clean(story.get("title", ""))))
    pieces += [Piece(piece_key("close", i + 1), "close") for i in range(CLOSE_VARIANTS)]
    return pieces


def _clean(text: str) -> str:
    return " ".join(str(text or "").split())


# ------------------------------------------------------------------ templates
# {a} and {b} are the hosts' first names, {h} the headline, {s} the section's title.
OPEN_TEMPLATES: list[list[Turn]] = [
    [(0, "Good morning, {b}! How are you doing this morning?"),
     (1, "[chuckle] Doing great, {a}, coffee in hand. Ready to dig into the news?"),
     (0, "Always. Let's get into it.")],
    [(0, "Hey {b}, welcome back. Did you sleep okay?"),
     (1, "[sigh] Better than most mornings, {a}. And there's plenty to talk about today."),
     (0, "There is. Let's jump right in.")],
    [(0, "Morning, {b}! Hope you're ready, it's a busy one."),
     (1, "Ready as I'll ever be, {a}. Let's see what's been happening."),
     (0, "Here we go.")],
]
CLOSE_TEMPLATES: list[list[Turn]] = [
    [(1, "And that's the brief. Thanks for listening."),
     (0, "Have a great day, everyone. See you tomorrow!")],
    [(0, "That's all for this morning."),
     (1, "[chuckle] Take care out there, and we'll be back tomorrow.")],
]
TEASE_TEMPLATES: dict[str, list[list[Turn]]] = {
    "serious": [[(0, "There's a story today that caught my eye: {h}."), (1, "Yes, that one matters. We'll get into it.")]],
    "warm": [[(0, "First up, {h}."), (1, "A lot to unpack there, so let's start.")]],
    "excited": [[(0, "Some exciting news in {s} today: {h}."), (1, "I've been looking forward to this one.")]],
    "light": [[(0, "Okay, this one is fun: {h}."), (1, "[laugh] I love it. Let's talk about it.")]],
    "energetic": [[(0, "Big news in {s}: {h}."), (1, "Sports fans, this one's for you.")]],
    "curious": [[(0, "Here's one that made me wonder: {h}."), (1, "Same here. Let's see what it says.")]],
}
BRIDGE_TEMPLATES: dict[str, list[Turn]] = {
    "serious": [(0, "Let's start with the main story.")],
    "warm": [(0, "Let's start with the main story.")],
    "excited": [(1, "Here's the latest in {s}.")],
    "light": [(1, "Now for something lighter, in {s}.")],
    "energetic": [(1, "Over to {s}.")],
    "curious": [(1, "Now, in {s}.")],
}


def _tone_family(section: str | None) -> str:
    return {"top": "warm", "politics": "serious", "ai": "excited", "tech": "excited",
            "entertainment": "light", "science": "curious", "sports": "energetic"}.get(section or "", "warm")


def _fill(turns: list[Turn], hosts: tuple[str, str], piece: Piece) -> list[Turn]:
    title = topics.SECTIONS.get(piece.section or "", {}).get("title", "the news")
    headline = piece.headline.rstrip(".")
    if len(headline) > 110:
        headline = headline[:107].rsplit(" ", 1)[0] + "..."
    filled = [(who, text.format(a=hosts[0], b=hosts[1], h=headline, s=title)) for who, text in turns]
    return [(who, strip_tags(text)) for who, text in filled] if piece.section in SOBER_SECTIONS else filled


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


# ------------------------------------------------------------------ validation
_BAD = re.compile(r"https?://|www\.|[*_#`<>\[\]{}]|\bhttp", re.I)


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
        words_only = strip_tags(text)
        if who not in ("a", "b") or not words_only or _BAD.search(words_only):
            return None
        tags += len(_TAG.findall(text))
        if section in SOBER_SECTIONS:
            text = words_only
        words += len(words_only.split())
        turns.append((0 if who == "a" else 1, text))
    if words > MAX_WORDS[kind] or tags > MAX_TAGS:
        return None
    return turns


# ------------------------------------------------------------------ AI writer
SYSTEM_PROMPT = """You write the banter for a two-host morning news podcast. The hosts introduce and react to the day's news; a separate narrator reads the stories in full, so you never read the news yourself.

Hosts: "a" is {a} and "b" is {b}. Warm, natural, like two colleagues chatting. Short spoken sentences, contractions, no jargon.

Return ONLY JSON of this shape:
{{"open": [turns, ...{open_n} variants], "close": [turns, ...{close_n} variants],
 "tease": {{"<section>": turns}}, "bridge": {{"<section>": turns}}}}
where turns is a list of {{"speaker": "a" or "b", "text": "..."}}.

Rules:
- open: a greeting chat only ("Good morning {b}, how are you doing?"). Today is {weekday}. No news. Make the {open_n} variants clearly different.
- close: a short goodbye. Make the variants different.
- tease: for each section, react to its headline in a way that fits its tone ("exciting news on AI today", "this one is a little scary"). Use only what the headline and summary say; never add facts.
- bridge: one short line leading into that section's stories, in the section's tone.
- Limits per piece: open <= {w_open} words and 4 turns, tease <= {w_tease} words and 3 turns, bridge <= {w_bridge} words and 2 turns, close <= {w_close} words and 3 turns.
- You may use these voice tags, which the hosts perform as real sounds: [laugh] [chuckle] [sigh] [cough] [gasp] [groan] [sniffle] [yawn]. Put one at the start of a turn, only where a person would genuinely react (a [chuckle] at a light moment, a [gasp] at a surprise), at most {max_tags} per piece, and many pieces should have none. Never use them for the "top" or "politics" sections or for any sad, violent or tragic story. Use no other square brackets.
- No URLs, emoji, lists, markdown or stage directions. Do not read the headline out word for word every time; paraphrase.
- The tone of each section is guidance for how you sound; never say the tone words themselves ("curious", "serious", "energetic").
- Stay respectful on sensitive stories: no jokes about tragedies."""


def _prompt(hosts: tuple[str, str], weekday: str) -> str:
    return SYSTEM_PROMPT.format(
        a=hosts[0], b=hosts[1], weekday=weekday, open_n=OPEN_VARIANTS, close_n=CLOSE_VARIANTS,
        w_open=MAX_WORDS["open"], w_tease=MAX_WORDS["tease"], w_bridge=MAX_WORDS["bridge"], w_close=MAX_WORDS["close"], max_tags=MAX_TAGS)


def ask_ai(cfg, pieces: list[Piece], hosts: tuple[str, str], day: str, *,
           client: httpx.Client | None = None) -> tuple[dict[str, Written], list[str]]:
    """One AI call for the whole day. Returns the valid pieces by key and a list of problems.

    Tries each Gemini then Groq model once; the first answer that parses wins. Never raises: a down or
    rate-limited service just yields nothing, and the caller fills in from templates."""
    problems: list[str] = []
    models = []
    if cfg.gemini_api_key:
        models += [(m, GEMINI_URL, cfg.gemini_api_key, "Gemini") for m in cfg.gemini_models]
    if cfg.groq_api_key:
        models += [(m, GROQ_URL, cfg.groq_api_key, "Groq") for m in cfg.groq_models]
    if not models:
        return {}, ["no AI key configured"]

    sections = {p.section: {"title": topics.SECTIONS[p.section]["title"], "tone": TONE.get(p.section, "neutral"),
                            "headline": p.headline, "summary": p.summary}
                for p in pieces if p.kind == "tease"}
    weekday = _date.fromisoformat(day).strftime("%A")
    payload = {"sections": sections}
    own = client is None
    client = client or httpx.Client(timeout=60)
    try:
        for model, url, token, provider in models:
            body = {
                "model": model, "temperature": 0.8, "max_tokens": 3000,
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
                parts, total = [], 0.0
                for who, line in w.turns:
                    audio, seconds = await synthesise(http, base, line, pair[who])
                    parts.append(audio)
                    total += seconds
                data = b"".join(parts)
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
