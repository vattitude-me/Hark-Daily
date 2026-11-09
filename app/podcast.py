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
from .tts.text import voice_normalize
from .writer import GEMINI_URL, GROQ_URL, _retry_after

log = logging.getLogger(__name__)

OPEN_VARIANTS = 3
CLOSE_VARIANTS = 2
READY_KEY = "podcast_ready"

# Word caps per piece keep the whole chat to roughly 60-90 seconds: news is the priority.
# open accommodates Part 1 (Brand Intro) + Part 2 (Conversational Open) across 4-6 short lines.
MAX_WORDS = {"open": 55, "tease": 38, "bridge": 20, "close": 42}
MAX_TURNS = {"open": 6, "tease": 3, "bridge": 2, "close": 4}

# How each section should sound, for the AI prompt and the template pools.
TONE = {
    "top": "serious but warm",
    "markets": "sharp and analytical",
    "ai": "curious and excited",
    "tech": "upbeat and practical",
    "politics": "measured and serious",
    "entertainment": "light and playful",
    "science": "curious and wondering",
    "sports": "energetic",
}

# Sections where Matthew (the serious, grounded anchor) naturally leads vs. Kelly (lively, curious).
HEAVY_SECTIONS = frozenset({"top", "politics", "markets"})

# Chatterbox performs these itself when they appear in the text, which sounds far more human than
# punctuation can (voice_service/turbo_voice/text.py lists the same set). Anything else in square
# brackets is rejected so a typo never gets read aloud.
TAGS = ("laugh", "chuckle", "sigh", "cough", "gasp", "groan", "sniffle", "yawn")
MAX_TAGS = 2
# Sections where a laugh or a sigh would be in poor taste: tags are stripped from their banter.
SOBER_SECTIONS = frozenset({"top", "politics"})
SOBER_KEYWORDS = frozenset({
    "kill", "death", "die", "dead", "fatal", "crash", "shoot", "attack",
    "casualty", "casualties", "tragedy", "victim", "victims", "murder",
    "injury", "injured", "grief", "mourn", "funeral", "fraud", "scam",
    "lawsuit", "sue", "sued", "suing", "layoff", "layoffs", "fired",
    "bankrupt", "bankruptcy", "probe", "investigation", "crime", "convict",
})
_TAG = re.compile(r"\[(" + "|".join(TAGS) + r")\]", re.I)
_TAG_START = re.compile(r"^\s*\[(" + "|".join(TAGS) + r")\]\s*", re.I)

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
# {a} and {b} are the hosts' first names (Matthew, Kelly), {h} the headline, {s} the section's title.
# Every OPEN_TEMPLATES entry follows Part 1 (Brand Intro with "Hark Daily" + tagline) + Part 2 (Conversational Open).
OPEN_TEMPLATES: list[list[Turn]] = [
    [(0, "This is Hark Daily. The news, minus the noise."),
     (1, "Look at you with the serious anchor voice, {a}."),
     (0, "Somebody has to keep us on track, {b}."),
     (1, "Fair enough. And we actually have a wild lineup of stories today.")],
    [(1, "You're listening to Hark Daily, your day caught up in minutes."),
     (0, "Short, steady, and straight to what matters."),
     (1, "I was just reading that first headline, {a}, and I have questions."),
     (0, "I figured you might.")],
    [(0, "Hark Daily. All the signal, none of the scrolling."),
     (1, "Okay, I like that tagline, {a}. We're keeping it."),
     (0, "Don't get used to it. There's some heavy news on the docket today."),
     (1, "Yeah, a couple of these stories really caught me off guard.")],
]
CLOSE_TEMPLATES: list[list[Turn]] = [
    [(1, "Still thinking about how much ground we covered today, {a}."),
     (0, "Never a quiet news cycle. That's Hark Daily for today."),
     (1, "Thanks for listening, everyone. Catch you next time.")],
    [(0, "That wraps it up for Hark Daily today."),
     (1, "Take care of yourselves [chuckle], and we'll talk to you on the next edition.")],
]
TEASE_TEMPLATES: dict[str, list[list[Turn]]] = {
    "serious": [[(0, "This one in {s} carries real weight today: {h}."), (1, "Yeah. Worth paying close attention to.")]],
    "warm": [[(0, "Leading our coverage today: {h}."), (1, "Here's what's actually happening behind that headline.")]],
    "excited": [[(1, "Wait until you hear this one in {s}: {h}."), (0, "It is a bigger shift than it looks at first glance.")]],
    "light": [[(1, "Okay, lighter note in {s}: {h}."), (0, "I have a feeling you're going to enjoy this one, {b}.") ]],
    "energetic": [[(1, "Over in {s}, look at this: {h}."), (0, "Quite a storyline building there.")]],
    "curious": [[(1, "I had to read this {s} headline twice: {h}."), (0, "The details are even more interesting.")]],
}
BRIDGE_TEMPLATES: dict[str, list[Turn]] = {
    "serious": [(0, "On a more serious note, {s}.")],
    "warm": [(0, "Starting with the lead stories.")],
    "excited": [(1, "Shifting over to {s}.")],
    "light": [(1, "Okay, lighter note with {s}.")],
    "energetic": [(1, "Over in {s}.")],
    "curious": [(1, "Speaking of big questions, here's {s}.")],
}


def _tone_family(section: str | None) -> str:
    base = (section or "").replace("_us", "").replace("_in", "").replace("_ca", "")
    return {"top": "warm", "markets": "serious", "politics": "serious", "ai": "excited", "tech": "excited",
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

# Strict broadcast-safety profanity filter: zero tolerance for vulgarity or explicit lyrics
_PROFANITY_PATTERN = re.compile(
    r"\b("
    r"fuck\w*|shit\w*|bitch\w*|asshole\w*|\bass\b|cunt\w*|dick\w*|pussy\w*|bastard\w*|"
    r"motherfuck\w*|bullshit\w*|dammit\w*"
    r")\b",
    re.IGNORECASE,
)


def sanitize_profanity(text: str) -> str:
    """Scrub any vulgarity, swear words or explicit lyrics into clean broadcast language."""
    if not text:
        return ""
    return _PROFANITY_PATTERN.sub("[bleep]", text)

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
    (re.compile(r"\bstrap\s+in\b", re.I), "so"),
    (re.compile(r"\bwithout\s+further\s+ado\b", re.I), "first off"),
    (re.compile(r"\bthat's\s+a\s+great\s+point\b", re.I), "right"),
    (re.compile(r"\bwelcome\s+back\s+everyone\b", re.I), "this is Hark Daily"),
    (re.compile(r"\bready\s+when\s+you\s+are\b", re.I), "right with you"),
    (re.compile(r"\bfascinating\b", re.I), "wild"),
    (re.compile(r"^\s*absolutely[.,!]\s*", re.I), "Right, "),
    (re.compile(r"\bthis\s+(?:morning|afternoon|evening)\b", re.I), "today"),
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
    """Strip or normalize robotic AI slop phrases and textual shorthand into simple, natural spoken English."""
    cleaned = text
    for pattern, repl in SLOP_PATTERNS:
        cleaned = pattern.sub(lambda m, r=repl: _preserve_case(m, r), cleaned)
    cleaned = voice_normalize(cleaned, preserve_tags=True)
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
        if who not in ("a", "b") or not words_only or _BAD.search(words_only) or _PROFANITY_PATTERN.search(words_only):
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
HOST_PERSONAS_BLOCK = """HOST PERSONALITIES
- {a} ("a", speaker 0): deep, steady, grounded. The serious anchor. Speaks in measured, weighty sentences and gives stories their gravity. Dry, understated humor that lands because it's rare. When something is absurd, he gets quieter and flatter, not louder. Prefers short, deliberate lines for big moments.
- {b} ("b", speaker 1): lively, quick, expressive. Brings energy and curiosity. Reacts out loud with surprise, amusement, or skepticism. Speaks in faster, more varied rhythms, with short bursts and the occasional run-on when she's excited. She's the one who teases {a} for being so serious.

THE DYNAMIC
- {b} sparks, {a} grounds. She makes things interesting, he makes them matter.
- {a} leads on heavy stories (politics, markets/economy, conflict, tragedy). {b} supports with brief, quieter reactions and drops the playfulness.
- {b} leads on light, quirky, or surprising stories. {a} plays it deadpan against her energy.
- Occasional role reversals keep it human: {a} gets caught off guard and laughs, or {b} gets serious and says this one actually matters.
- Light teasing is welcome, usually {b} poking at {a}'s gravity."""


SYSTEM_PROMPT = """You are the scriptwriter for "Hark Daily," a daily news podcast hosted by {a} ("a") and {b} ("b"). Write the script as a real conversation between two people who know each other well, not as two news readers handing off to each other.

""" + HOST_PERSONAS_BLOCK + """

STRICT LANGUAGE & ANTI-SLOP RULES (THIS WILL BE READ ALOUD BY TTS):
- Use contractions and spoken rhythm ("we've", "it's", "that's", "don't", "can't"). Short sentences. Occasional fragments.
- Light fillers ("honestly," "I mean," "right?") at most once or twice per piece.
- No lists, no parentheses, no stage directions, no emojis, no markdown, no URLs.
- Don't read headlines word for word. Retell them like you're telling a friend.
- BANNED PHRASES (NEVER USE ANY OF THESE):
  "Let's dive in", "dive into", "deep dive", "Buckle up", "Strap in", "Without further ado", "That's a great point", "Absolutely", "Fascinating", "Welcome back everyone", "Ready when you are", "let's roll", "whirlwind", "unpack", "delve", "fast-moving", "ground to cover", "buzzing", "wild ride", "game-changer", "moving across the board".
- Do NOT use time-of-day locked words like "morning", "afternoon", "evening", or "tomorrow morning".
- VOICE-BASED SPOKEN TEXT: Everything is read aloud by neural voices. Never use textual shorthand like "$5B", "$10M", or "20%". Always spell out numbers, symbols, and abbreviations the way they're spoken: "5 billion dollars", "10 million dollars", "20 percent", "versus", "and".
- Paralinguistic voice tags: [chuckle], [laugh], [sigh], [gasp]. Use very sparingly (most pieces should have ZERO tags, at most {max_tags} tags per piece). Never place tags on tragedy, politics, or serious hardship.

Return ONLY JSON of this shape:
{{"open": [turns, ...{open_n} variants], "close": [turns, ...{close_n} variants],
 "tease": {{"<section>": turns}}, "bridge": {{"<section>": turns}}}}
where turns is a list of {{"speaker": "a" or "b", "text": "..."}}.

SEGMENT RULES:
- open (<= {w_open} words, 4 to 6 short turns per variant): Combine PART 1 (BRAND INTRO) + PART 2 (CONVERSATIONAL OPEN):
  * PART 1 - BRAND INTRO (first 2 turns): A quick, fun, memorable show intro that sets the personality before the news begins. Must include the show name "Hark Daily" (or "hark Daily") once, plus a fresh daily tagline idea in the spirit of "the news, minus the noise" or "your day, caught up." Invent a fresh tagline for each variant—never reuse example lines! Can be a deadpan {a} line answered by an excited {b}, or {b} teasing {a} for his serious announcer voice.
  * PART 2 - CONVERSATIONAL OPEN (next 2-3 turns): Move straight into a natural mid-thought opening. No "welcome back everyone," no "let's get into what's happening," no "Hey [name]" followed by "Ready when you are." Open with a reaction to one of today's top headlines, a small observation about {weekday}, or a teaser. Each host's line must respond directly to the other's.
- tease (<= {w_tease} words, 2 to 3 turns): A natural reaction to that section's top headline. Have {a} lead heavy sections (top, politics, markets) and {b} lead lighter or fast-moving sections (ai, tech, science, entertainment, sports).
- bridge (<= {w_bridge} words, 1 to 2 turns): A natural transition into that section using a thematic link ("Speaking of money..."), a reaction, or a clean pivot ("Okay, lighter note."). Use "Next up" or "Moving on" at most once across the entire JSON output.
- close (<= {w_close} words, 2 to 4 turns): End casually with a last reaction or a light callback to one of today's stories, then a brief sign-off that includes "Hark Daily". No formal summary. Vary each variant.
- ANTI-REPETITION: Any example lines in this prompt are for tone only. Never reuse their wording, structure, or jokes. If yesterday's opening is provided in the user payload, make today's clearly different."""


def _prompt(hosts: tuple[str, str], weekday: str) -> str:
    return SYSTEM_PROMPT.format(
        a=hosts[0], b=hosts[1], weekday=weekday, open_n=OPEN_VARIANTS, close_n=CLOSE_VARIANTS,
        w_open=MAX_WORDS["open"], w_tease=MAX_WORDS["tease"], w_bridge=MAX_WORDS["bridge"], w_close=MAX_WORDS["close"], max_tags=MAX_TAGS)


_LAST_LLM_CALL_TIME: float = 0.0
_MIN_LLM_INTERVAL: float = 1.6  # Minimum seconds between LLM calls to keep safely within Groq 30 RPM limit


def _rate_limit_llm() -> None:
    """Ensure at least _MIN_LLM_INTERVAL seconds elapse between external LLM requests to prevent free-tier 429s."""
    global _LAST_LLM_CALL_TIME
    now = time.monotonic()
    elapsed = now - _LAST_LLM_CALL_TIME
    if elapsed < _MIN_LLM_INTERVAL:
        time.sleep(_MIN_LLM_INTERVAL - elapsed)
    _LAST_LLM_CALL_TIME = time.monotonic()


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
           client: httpx.Client | None = None,
           yesterdays_opening: str | None = None) -> tuple[dict[str, Written], list[str]]:
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
    payload: dict = {"date": day, "day_of_week": weekday, "sections": sections}
    if yesterdays_opening:
        payload["yesterdays_opening"] = yesterdays_opening
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
                _rate_limit_llm()
                resp = client.post(url, json=body, headers={"Authorization": f"Bearer {token}"})
                if resp.status_code == 429:
                    problems.append(f"{provider} {model}: HTTPStatusError: 429 Too Many Requests")
                    continue
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


def fetch_yesterdays_opening(store, day: str, hosts_id: str) -> str | None:
    """Fetch the most recent prior day's pod_open_1 transcript so today's opening never repeats it."""
    try:
        rows = store.select("podcast_clips", {"date": f"lt.{day}", "hosts": f"eq.{hosts_id}", "clip_key": "eq.pod_open_1"})
        if not rows:
            return None
        latest = max(rows, key=lambda r: str(r.get("date") or ""))
        text = str(latest.get("text") or "").strip()
        return text or None
    except Exception:
        return None


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

    yesterdays_opening = fetch_yesterdays_opening(store, day, hosts_id)
    pieces = plan_pieces(scripts)
    written, problems = await asyncio.to_thread(
        write_pieces, cfg, pieces, names, day, client=client, yesterdays_opening=yesterdays_opening
    )
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
STORY_DIALOGUE_VERSION = "v3"
PURPOSE_PAUSES: dict[str, float] = {
    "lead": 0.44,
    "question": 0.56,
    "reaction": 0.28,
    "context": 0.42,
    "implication": 0.46,
    "takeaway": 0.50,
}
VALID_PURPOSES = frozenset(PURPOSE_PAUSES)

STORY_FORMATS: dict[str, str] = {
    "explainer_reactions": (
        "FORMAT 1 (Explainer + Short Reactions): The lead host explains the story across 2 to 3 substantial turns "
        "(up to 3-4 sentences in a turn) while the other host drops a short, natural 1 to 4 word human reaction "
        "(like 'Huh.', 'Wait, really?', 'Right.', 'That is steep.') before a grounded final takeaway. "
        "Do NOT force equal-length turns."
    ),
    "question_led": (
        "FORMAT 2 (Question-Led): One host introduces the surprising headline hook, the other asks a direct, "
        "curious question ('Wait, why did they do that?', 'How does that actually work in practice?'), "
        "and the first host explains the answer using the facts."
    ),
    "mild_disagreement": (
        "FORMAT 3 (Mild Disagreement / Two Angles): The hosts take slightly different angles on why the story matters "
        "(for example, one sees the practical upside or ambition while the other points out the cost, risk, or catch "
        "reported in the facts)."
    ),
    "conversational_dialogue": (
        "FORMAT 4 (Dynamic Banter / Deep-Dive): True conversational back-and-forth across 3 to 5 turns. "
        "Hosts can speak consecutive turns when natural ('A -> A -> B -> A'), share insights, and discuss "
        "the implications with lively pacing."
    ),
    "quick_hit": (
        "FORMAT 5 (Quick Hit): Keep this one tight and punchy—just 2 or 3 crisp turns total (around 35 to 60 words total) "
        "that land the essential news and why it matters, then move on."
    ),
    "reversal": (
        "FORMAT 6 (The Twist / Reversal): Start with the obvious surface take on the headline in Turn 1, "
        "then have the other host counter with 'Actually, here is the catch...' or the unexpected detail from the facts."
    ),
    "solo_matthew": (
        "FORMAT 7 (Solo Anchor - Matthew): Matthew anchors this story ALONE in 1 or 2 clear, punchy broadcast turns "
        "(25 to 65 words total). Kelly does NOT speak in this story at all. Matthew delivers the news and context with direct authority."
    ),
    "solo_kelly": (
        "FORMAT 8 (Solo Anchor - Kelly): Kelly anchors this story ALONE in 1 or 2 energetic, engaging broadcast turns "
        "(25 to 65 words total). Matthew does NOT speak in this story at all. Kelly delivers the story with lively clarity."
    ),
    "lead_takeaway": (
        "FORMAT 9 (Lead & Takeaway): Exactly 2 turns total. One host delivers the main news lead and context (20-40 words); "
        "the other host wraps with the single critical takeaway or bottom line (15-25 words). Tight, punchy 2-turn story."
    ),
}
STORY_FORMAT_KEYS: tuple[str, ...] = tuple(STORY_FORMATS.keys())
SOBER_STORY_FORMAT_KEYS: tuple[str, ...] = (
    "explainer_reactions", "solo_matthew", "lead_takeaway", "solo_kelly", "quick_hit", "question_led"
)


def is_solo_format(fmt_key: str | None) -> bool:
    """Return True if the story format is anchored by a single host."""
    return fmt_key in ("solo_matthew", "solo_kelly")


def solo_host_index(fmt_key: str | None, hosts: tuple[str, str] = ("Matthew", "Kelly")) -> int:
    """Return speaker index for a solo format: 0 for Matthew (host A), 1 for Kelly (host B)."""
    return 1 if fmt_key == "solo_kelly" else 0


def select_story_format(
    section: str,
    rank: int,
    *,
    sober: bool = False,
    previous_format: str | None = None,
) -> tuple[str, str]:
    """Deterministically pick one of the story formats so back-to-back stories never repeat the same format."""
    pool = SOBER_STORY_FORMAT_KEYS if sober else STORY_FORMAT_KEYS
    sec_offset = int(hashlib.sha1((section or "top").encode("utf-8")).hexdigest()[:6], 16)
    idx = (sec_offset + max(1, int(rank)) - 1) % len(pool)
    chosen = pool[idx]
    if previous_format and chosen == previous_format and len(pool) > 1:
        chosen = pool[(idx + 1) % len(pool)]
    return chosen, STORY_FORMATS[chosen]


def select_story_lead(brief: dict, hosts: tuple[str, str] = ("Matthew", "Kelly")) -> str:
    """Assign who leads the story based on topic weight, with occasional role-reversal moments."""
    a, b = hosts
    base_sec = str(brief.get("section") or "top").replace("_us", "").replace("_in", "").replace("_ca", "")
    sober = bool(brief.get("sober"))
    story_hash = int(hashlib.sha1(str(brief.get("story_id") or "").encode("utf-8")).hexdigest()[:6], 16)
    role_reversal = (not sober) and (story_hash % 5 == 0)

    if sober or base_sec in HEAVY_SECTIONS:
        if role_reversal:
            return (
                f"Lead Host: {b} ('b') opens this one in a rare serious role reversal—she drops the playfulness "
                f"and says this story actually matters, while {a} ('a') grounds the numbers and implications."
            )
        return (
            f"Lead Host: {a} ('a', speaker 0) leads this story with steady, measured gravity. "
            f"{b} ('b', speaker 1) supports with quieter, grounded reactions and drops the playfulness."
        )

    if role_reversal:
        return (
            f"Lead Host: {a} ('a') leads, but gets slightly caught off guard by how unusual or surprising this story is, "
            f"while {b} ('b') plays off his reaction."
        )
    return (
        f"Lead Host: {b} ('b', speaker 1) leads this story with lively curiosity and energy. "
        f"{a} ('a', speaker 0) plays it deadpan and grounded against her energy."
    )


@dataclass
class DialogueTurn:
    speaker: int                  # 0 for Host A (Matthew), 1 for Host B (Kelly)
    text: str                     # spoken text (may include valid Chatterbox tags in non-sober sections)
    purpose: str = "context"      # lead | question | reaction | context | implication | takeaway
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
    story_format: str = "question_led"


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
    headline = voice_normalize(_clean(story.get("title") or story.get("headline") or "").rstrip("."), preserve_tags=False)
    source = _clean(story.get("source") or "News wire")
    summary = voice_normalize(_clean(story.get("summary") or ""), preserve_tags=False)
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
        facts.append({"id": fid, "fact": voice_normalize(sent, preserve_tags=False)})
        if len(facts) >= 6:
            break

    if len(facts) == 1 and summary and summary.lower().rstrip(".") != head_norm:
        facts.append({"id": "F2", "fact": summary if summary.endswith((".", "!", "?")) else f"{summary}."})

    has_sensitive_keyword = any(kw in headline.lower() or kw in summary.lower() for kw in SOBER_KEYWORDS)
    sober = (base_sec in SOBER_SECTIONS) or has_sensitive_keyword

    return {
        "story_id": str(story.get("id") or story.get("url") or f"{sec}-{story.get('rank', 1)}"),
        "section": sec,
        "section_title": topics.ALL_SECTIONS.get(sec, {}).get("title", sec.title()),
        "rank": int(story.get("rank") or 1),
        "headline": headline,
        "source": source,
        "summary": summary or headline,
        "tone": TONE.get(base_sec, "warm and informative"),
        "sober": sober,
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


_SCRIPT_LINE_RE = re.compile(r"^\s*\[?([A-Za-z]+)\]?\s*:\s*(.+)$")


def parse_story_dialogue_payload(
    raw: str | dict | list | None,
    hosts: tuple[str, str] = ("Matthew", "Kelly"),
) -> dict | list | None:
    """Parse either JSON dialogue output or plain 'MATTHEW: ... / KELLY: ...' script lines."""
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, (dict, list)):
            return parsed
    except Exception:
        pass

    turns: list[dict] = []
    for line in text.splitlines():
        m = _SCRIPT_LINE_RE.match(line.strip())
        if not m:
            continue
        speaker_tok, spoken = m.group(1), m.group(2).strip()
        if _speaker_index(speaker_tok, hosts) is not None and spoken:
            turns.append({"speaker": speaker_tok, "text": spoken})
    return {"turns": turns} if turns else None


def validate_story_dialogue(
    raw: dict | list | str | None,
    story_brief: dict,
    hosts: tuple[str, str] = ("Matthew", "Kelly"),
    *,
    min_turns: int | None = None,
    max_turns: int | None = None,
) -> list[DialogueTurn] | None:
    """Validate LLM-generated story dialogue turns against podcast editorial & TTS rules.

    Supports solo reports (1-2 turns), 2-turn quick hits, up to 7-turn back-and-forths.
    Enforces a strict <= 24 word limit per sentence to prevent TTS generation slowdowns.
    """
    fmt_key = str(story_brief.get("story_format") or "")
    is_solo = is_solo_format(fmt_key)
    solo_spk = solo_host_index(fmt_key, hosts) if is_solo else None

    if min_turns is None:
        min_turns = 1 if is_solo else 2
    if max_turns is None:
        max_turns = 3 if is_solo else 7

    if isinstance(raw, str):
        raw = parse_story_dialogue_payload(raw, hosts)
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
        if is_solo and who != solo_spk:
            return None
        if not is_solo:
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

        # Canned reflex reaction tag removal: if Turn 2 (the immediate response to the headline)
        # starts with a reaction sound ([laugh], [sigh], [chuckle], etc.), strip it so the second
        # speaker responds naturally with words rather than an automatic repetitive sound effect.
        if len(parsed) == 1 and not is_solo:
            text = _clean(_TAG_START.sub("", text))

        words_only = strip_tags(text)
        word_count = len(words_only.split())
        if not words_only or word_count < 1 or word_count > 68 or _BAD.search(words_only) or _PROFANITY_PATTERN.search(words_only):
            return None

        # Sentence length ceiling: individual sentences over 24 words drastically slow down TTS
        # synthesis and cause pacing drift. Reject run-on sentences to maintain crisp pacing.
        sentences = re.split(r"(?<=[.!?])\s+", words_only)
        for s in sentences:
            s_words = [w for w in s.strip().split() if w]
            if len(s_words) > 24:
                return None

        tags_in_turn = len(_TAG.findall(text))
        total_tags += tags_in_turn
        if sober:
            text = words_only
        elif total_tags > 1 and tags_in_turn > 0:
            text = strip_tags(text)
            total_tags = 1

        purpose = str(item.get("purpose") or ("reaction" if word_count <= 3 else "context")).strip().lower()
        if purpose not in VALID_PURPOSES:
            purpose = "reaction" if word_count <= 3 else "context"

        raw_refs = item.get("fact_refs")
        fact_refs = [str(r).strip().upper() for r in raw_refs if str(r).strip()] if isinstance(raw_refs, list) else []
        if valid_fact_ids:
            fact_refs = [r for r in fact_refs if r in valid_fact_ids] or ["F1"]

        pause_after = 0.28 if (word_count <= 3 and purpose != "question") else PURPOSE_PAUSES.get(purpose, 0.36)
        total_words += word_count
        parsed.append(DialogueTurn(
            speaker=who,
            text=text,
            purpose=purpose,
            fact_refs=fact_refs,
            pause_after=pause_after,
        ))

    if is_solo:
        if total_words < 18 or total_words > 120:
            return None
    else:
        speakers_used = {t.speaker for t in parsed}
        if len(speakers_used) < 2 or total_words < 20 or total_words > 190:
            return None
    if not sober and total_tags > MAX_TAGS:
        return None
    return parsed


STORY_DIALOGUE_PROMPT = """You are the scriptwriter for "Hark Daily," a daily news podcast hosted by {a} ("a") and {b} ("b"). Write the script for ONE news story as a real conversation between two people who know each other well, not as two news readers handing off to each other.

""" + HOST_PERSONAS_BLOCK + """

ASSIGNED STORY FORMAT & LEAD FOR THIS STORY:
- {lead_instruction}
- {format_instruction}
- {transition_instruction}

STRICT EDITORIAL, LANGUAGE & ANTI-SLOP RULES:
1. Do NOT read the headline word for word. Retell the story like you're telling a smart friend across the table.
2. Vary turn lengths naturally: a turn can be a 1-to-3 word reaction ("Huh.", "Wait, really?", "Right.") or a 3-to-4 sentence explanation. A host may speak twice in a row when it fits the rhythm, as long as both hosts participate in the story. Let pacing follow the story's weight: slower and sparser for serious news, quicker and looser for light news.
3. Grounding: Stay 100% faithful to the supplied `facts` (`F1`, `F2`, ...). Add personality, NEVER invented details, numbers, quotes, causes, or outcomes.
4. Use contractions ("don't", "can't", "it's", "they're", "we've") and spoken rhythm. Short sentences. Occasional fragments. Light fillers ("honestly," "I mean," "right?") at most once or twice per story.
5. BANNED PHRASES (NEVER USE ANY OF THESE):
   "Let's dive in", "dive into", "deep dive", "Buckle up", "Strap in", "Without further ado", "That's a great point", "Absolutely", "Fascinating", "Welcome back everyone", "let's roll", "whirlwind", "unpack", "delve", "game-changer", "tapestry", "beacon", "foster", "testament", "pivotal", "in today's world", "at the end of the day", "needless to say", "fast-moving", "wild ride", "mind-blowing", "ground to cover", "moving across the board".
6. No lists, no parentheses, no stage directions, no emojis, no semicolons, no dashes, no markdown, no URLs. Do NOT use time-of-day words ("this morning", "tonight").
7. Paralinguistic emotion tags: {tag_instruction}
8. VOICE-BASED TEXT (CRITICAL - SCRIPT IS SPOKEN BY NEURAL TEXT-TO-SPEECH VOICES):
   Write exclusively for the ear as spoken aloud, NEVER visual print or textual shorthand.
   - Money and Currency: NEVER write symbols or abbreviated shorthand like "$5B", "$10M", "$500K", "$20", "€50M", or "£10B". Always spell them out in full spoken words: "5 billion dollars", "10 million dollars", "500 thousand dollars", "20 dollars", "50 million euros", "10 billion pounds".
   - Percentages: NEVER use the "%" symbol (e.g. "15%"). Always write "15 percent" or "fifteen percent".
   - Numbers & Multipliers: Round numbers naturally. Say "5 times" instead of "5x", "number one" instead of "#1" or "No. 1".
   - Acronyms & Abbreviations: Write out acronyms so text-to-speech speaks them cleanly. Say "I-P-O", "C-E-O", "first quarter" (never "Q1"), "third quarter" (never "Q3"), "versus" (never "vs" or "vs."), "and" (never "&"), "with" (never "w/"), "approximately" (never "approx.").
   - Do not use forward slashes (say "per" or "or").
9. BROADCAST SAFETY & FAMILY-FRIENDLINESS (ZERO TOLERANCE FOR PROFANITY):
   - Absolutely NO profanity, swear words, vulgarity, offensive slang, or expletives (e.g. fuck, shit, bitch, ass, asshole, dick, pussy, bastard, or any variations).
   - Even if the source material, news story, song title, or music album quotes explicit lyrics or swear words, NEVER repeat the expletives. Rephrase or describe them cleanly for a general public family audience (e.g., say 'an expletive-laden challenge' or describe the sentiment in clean words). Any script containing profanity will be automatically rejected.
10. KEEP SENTENCES SHORT (CRITICAL FOR AUDIO PACING):
    Keep every individual sentence under 20 words. Compound run-on sentences cause audio synthesis slowdowns and unnatural cadence. Break complex thoughts into punchy spoken sentences.

{shape_instruction}"""


def fallback_story_dialogue(
    story: dict,
    hosts: tuple[str, str] = ("Matthew", "Kelly"),
) -> StoryDialogue:
    """Deterministic, strictly factual exchange built from extracted article sentences."""
    brief = build_story_brief(story)
    facts = brief["facts"]
    base_sec = str(brief.get("section") or "top").replace("_us", "").replace("_in", "").replace("_ca", "")
    lead_speaker = 0 if (brief["sober"] or base_sec in HEAVY_SECTIONS or brief["rank"] % 2 == 1) else 1
    co_speaker = 1 - lead_speaker
    source = brief["source"]
    headline = brief["headline"].rstrip(".")
    fmt_key, _ = select_story_format(brief["section"], brief["rank"], sober=brief["sober"])

    f1 = facts[0]["fact"] if facts else f"{headline}."
    f2 = facts[1]["fact"] if len(facts) > 1 else ""
    f3 = facts[2]["fact"] if len(facts) > 2 else ""
    f4 = facts[3]["fact"] if len(facts) > 3 else ""

    if is_solo_format(fmt_key):
        solo_spk = solo_host_index(fmt_key, hosts)
        turns = [
            DialogueTurn(
                speaker=solo_spk,
                text=f1,
                purpose="lead",
                fact_refs=["F1"],
                pause_after=PURPOSE_PAUSES["lead"],
            ),
            DialogueTurn(
                speaker=solo_spk,
                text=f2 if f2 else (f3 if f3 else f"Reporting from {source}."),
                purpose="takeaway",
                fact_refs=["F2"] if f2 else ["F1"],
                pause_after=PURPOSE_PAUSES["takeaway"],
            ),
        ]
        return StoryDialogue(
            story_id=brief["story_id"],
            section=brief["section"],
            headline=brief["headline"],
            summary=brief["summary"],
            turns=turns,
            writer="built-in",
            story_format=fmt_key,
        )

    if fmt_key == "lead_takeaway":
        takeaway_text = f2 if f2 else (f3 if f3 else f"Reporting there from {source}.")
        turns = [
            DialogueTurn(
                speaker=lead_speaker,
                text=f1,
                purpose="lead",
                fact_refs=["F1"],
                pause_after=PURPOSE_PAUSES["lead"],
            ),
            DialogueTurn(
                speaker=co_speaker,
                text=takeaway_text,
                purpose="takeaway",
                fact_refs=["F2"] if f2 else ["F1"],
                pause_after=PURPOSE_PAUSES["takeaway"],
            ),
        ]
        return StoryDialogue(
            story_id=brief["story_id"],
            section=brief["section"],
            headline=brief["headline"],
            summary=brief["summary"],
            turns=turns,
            writer="built-in",
            story_format=fmt_key,
        )

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
        story_format=fmt_key,
    )


def _dialogue_cache_path(cfg, brief: dict, hosts: tuple[str, str], fmt_key: str = "") -> Path | None:
    cache_root = getattr(cfg, "cache_dir", None)
    if not cache_root:
        return None
    folder = Path(cache_root) / "story_dialogue"
    folder.mkdir(parents=True, exist_ok=True)
    fingerprint = json.dumps(
        {
            "v": STORY_DIALOGUE_VERSION,
            "hosts": hosts,
            "format": fmt_key,
            "headline": brief["headline"],
            "facts": brief["facts"],
        },
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
    previous_story: dict | None = None,
    previous_format: str | None = None,
) -> StoryDialogue:
    """Write a grounded two-host conversation for one story using Groq -> Local LLM -> Gemini -> fallback."""
    brief = build_story_brief(story)
    fmt_key, fmt_desc = select_story_format(
        brief["section"], brief["rank"], sober=brief["sober"], previous_format=previous_format
    )
    cache_path = _dialogue_cache_path(cfg, brief, hosts, fmt_key)
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
                    story_format=str(cached.get("story_format") or fmt_key),
                )
        except Exception:
            pass

    models = _ai_provider_chain(cfg)
    if not models:
        return fallback_story_dialogue(story, hosts)

    tag_instruction = (
        "Do NOT use any bracketed voice tags ([laugh], [chuckle], etc.) because this is a sober or serious news section. Express gravity and warmth through thoughtful phrasing and `...` pauses."
        if brief["sober"]
        else (
            "Paralinguistic voice tags ([chuckle], [laugh], [sigh], [gasp]) are strictly OPTIONAL and must be used VERY SPARINGLY. "
            "Most stories (over 80%) should have ZERO tags. "
            "CRITICAL: Do NOT put an emotion tag at the beginning of the second speaker's response (Turn 2) to a headline—it sounds monotonous and fake. "
            "Only include a tag (at most 1 in the entire story) if the news is genuinely amusing, quirky, or ironic, and place it naturally where a human would express it (such as mid-sentence or in the closing takeaway turn), or omit it completely."
        )
    )
    lead_instruction = select_story_lead(brief, hosts)
    lead_speaker = "a" if lead_instruction.startswith(f"Lead Host: {hosts[0]}") else "b"
    co_speaker = "b" if lead_speaker == "a" else "a"
    prev_title = _clean((previous_story or {}).get("title") or (previous_story or {}).get("headline") or "")
    if brief["rank"] <= 1 and not prev_title:
        transition_instruction = (
            "Transition: This is the first story in the section. Open directly into the story hook with no greeting, "
            "no show intro, and no 'Next up'."
        )
    elif prev_title:
        transition_instruction = (
            f"Transition: The previous story in this section was '{prev_title[:90]}'. "
            "Begin Turn 1 with a subtle thematic link, a brief reaction pivot, or a natural conversational shift "
            "('Speaking of money...', 'On a very different note...', 'Meanwhile,'). Do NOT overuse 'Next up' or 'Moving on'."
        )
    else:
        transition_instruction = (
            "Transition: Begin Turn 1 with a natural conversational pivot into this story without repeating 'Next up' or 'Moving on'."
        )

    brief["story_format"] = fmt_key

    if is_solo_format(fmt_key):
        solo_spk_idx = solo_host_index(fmt_key, hosts)
        solo_spk_letter = "a" if solo_spk_idx == 0 else "b"
        solo_spk_name = hosts[solo_spk_idx]
        shape_instruction = f"""Return ONLY valid JSON of this exact shape (1 to 2 turns total by {solo_spk_name} ('{solo_spk_letter}'), 25 to 65 words total across all turns):
{{
  "summary": "1-2 sentence neutral card summary (30-50 words) built strictly from the facts",
  "turns": [
    {{"speaker": "{solo_spk_letter}", "purpose": "lead", "fact_refs": ["F1"], "text": "..."}},
    {{"speaker": "{solo_spk_letter}", "purpose": "takeaway", "fact_refs": ["F2"], "text": "..."}}
  ]
}}"""
    elif fmt_key == "lead_takeaway":
        shape_instruction = f"""Return ONLY valid JSON of this exact shape (EXACTLY 2 turns total: Turn 1 by '{lead_speaker}' (20-40 words), Turn 2 by '{co_speaker}' (15-25 words), 35 to 65 words total):
{{
  "summary": "1-2 sentence neutral card summary (30-50 words) built strictly from the facts",
  "turns": [
    {{"speaker": "{lead_speaker}", "purpose": "lead", "fact_refs": ["F1"], "text": "..."}},
    {{"speaker": "{co_speaker}", "purpose": "takeaway", "fact_refs": ["F2"], "text": "..."}}
  ]
}}"""
    else:
        shape_instruction = f"""Return ONLY valid JSON of this exact shape (2 to 5 turns total, 35 to 140 words across all turns):
{{
  "summary": "1-2 sentence neutral card summary (30-50 words) built strictly from the facts",
  "turns": [
    {{"speaker": "{lead_speaker}", "purpose": "lead", "fact_refs": ["F1"], "text": "..."}},
    {{"speaker": "{co_speaker}", "purpose": "reaction", "fact_refs": ["F2"], "text": "..."}},
    {{"speaker": "{lead_speaker}", "purpose": "context", "fact_refs": ["F2", "F3"], "text": "..."}},
    {{"speaker": "{co_speaker}", "purpose": "takeaway", "fact_refs": ["F3"], "text": "..."}}
  ]
}}"""

    sys_prompt = STORY_DIALOGUE_PROMPT.format(
        a=hosts[0],
        b=hosts[1],
        source=brief["source"],
        tag_instruction=tag_instruction,
        lead_instruction=lead_instruction,
        format_instruction=fmt_desc,
        transition_instruction=transition_instruction,
        lead_speaker=lead_speaker,
        co_speaker=co_speaker,
        shape_instruction=shape_instruction,
    )
    user_payload = {
        "section": brief["section_title"],
        "rank": brief["rank"],
        "story_format": fmt_key,
        "tone": brief["tone"],
        "source": brief["source"],
        "headline": brief["headline"],
        "facts": brief["facts"],
    }
    if prev_title:
        user_payload["previous_story_headline"] = prev_title[:120]

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
                    "temperature": 0.55 if attempt == 0 else 0.30,
                    "max_tokens": 1100,
                    "response_format": {"type": "json_object"},
                    **({"reasoning_effort": "low"} if model.startswith("openai/gpt-oss") else {}),
                    "messages": messages,
                }
                try:
                    _rate_limit_llm()
                    resp = client.post(url, json=body, headers={"Authorization": f"Bearer {token}"})
                    if resp.status_code == 429:
                        wait = max(_retry_after(resp), 3.0)
                        if wait <= 20 and attempt == 0:
                            log.warning("Groq rate limit hit (429) during story dialogue. Backing off for %.1fs...", wait)
                            sleep(wait)
                            continue
                        break
                    resp.raise_for_status()
                    content = resp.json()["choices"][0]["message"]["content"]
                    data = parse_story_dialogue_payload(content, hosts)
                    if not isinstance(data, dict):
                        raise ValueError("response is not a JSON object")
                    turns = validate_story_dialogue(data, brief, hosts)
                    if not turns:
                        if attempt == 0:
                            messages.append({"role": "assistant", "content": content})
                            messages.append({
                                "role": "user",
                                "content": (
                                    "Repair the JSON: ensure valid turns adhering to the format, "
                                    "keep each sentence under 20 words, no dashes or special characters, and valid fact_refs."
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
                        story_format=fmt_key,
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
                                        "story_format": result.story_format,
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
        clean_line = voice_normalize(strip_tags(t.text), preserve_tags=False)
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
    """Synthesize each turn of a StoryDialogue with Matthew & Kelly, cache per-turn audio, and stitch via PCM.

    Requests lossless WAV (?format=wav) from the voice service, caches with honest parameter keys,
    applies per-host pace and temperature variation, stitches in PCM, and encodes ONCE to MP3 at 96 kbps.
    """
    from .storypack import synthesise

    turn_cache: Path | None = None
    if cache_dir:
        turn_cache = Path(cache_dir) / "podcast_turns"
        turn_cache.mkdir(parents=True, exist_ok=True)

    raw_turns: list[tuple[bytes, float, float]] = []
    for turn in dialogue.turns:
        voice_id = host_voices[turn.speaker]
        word_count = len(strip_tags(turn.text).split())

        # Pacing & temperature variation per host and turn purpose
        if turn.speaker == 0:  # Matthew: grounded, measured
            turn_pace = 0.93
            turn_temp = 0.82
        else:                  # Kelly: lively, energetic
            turn_pace = 0.97
            turn_temp = 0.88

        # Short reaction turns: slightly brisker and more expressive
        if turn.purpose == "reaction" and word_count <= 4:
            turn_pace = 0.98
            turn_temp = 0.90

        # Honest cache key incorporating format, voice, pace, temperature, and text
        cache_key_str = f"wav|{voice_id}|{turn_pace:.2f}|{turn_temp:.2f}|{turn.text}"
        key = hashlib.sha256(cache_key_str.encode("utf-8")).hexdigest()[:16]
        cached_wav = turn_cache / f"{key}.wav" if turn_cache else None
        cached_meta = turn_cache / f"{key}.json" if turn_cache else None

        if cached_wav and cached_wav.is_file() and cached_meta and cached_meta.is_file():
            try:
                raw_audio = cached_wav.read_bytes()
                seconds = float(json.loads(cached_meta.read_text(encoding="utf-8")).get("duration") or 1.2)
                raw_turns.append((raw_audio, seconds, turn.pause_after))
                continue
            except Exception:
                pass

        # Request lossless WAV from voice service (format="wav")
        raw_audio, seconds = await synthesise(
            http, base, turn.text, voice_id,
            pace=turn_pace,
            temperature=turn_temp,
            fmt="wav",
        )
        if cached_wav and cached_meta:
            try:
                cached_wav.write_bytes(raw_audio)
                cached_meta.write_text(
                    json.dumps({"duration": seconds, "voice": voice_id, "pace": turn_pace, "temp": turn_temp}),
                    encoding="utf-8",
                )
            except Exception:
                pass
        raw_turns.append((raw_audio, seconds, turn.pause_after))

    return await asyncio.to_thread(stitch_turn_audio, raw_turns)
