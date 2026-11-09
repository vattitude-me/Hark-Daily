"""Turn a news script into speech spans and pauses.

Chatterbox's own ``punc_norm()`` rewrites "…" to ", " and "—" to "-", so
punctuation alone can never produce a real beat of silence. The script is
therefore split into speech spans and explicit pauses, each span is synthesised
on its own, and the pieces are joined with silence — the same "voice each beat,
then stitch" approach the v1 briefing uses.

Two things reach the model untouched:

* paralinguistic tags such as ``[sigh]``, ``[chuckle]``, ``[cough]``, ``[laugh]``
* ordinary punctuation, which the model reads and paces well

Pause syntax::

    [[pause:0.8]]   a pause of that many seconds
    ...  or  …      a beat, using the caller's default

``[sigh]`` and friends are left in the text on purpose: the model was trained on
them and performs the sound itself, which sounds far more human than the same
breath synthesised as noise.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
from dataclasses import dataclass

# The paralinguistic tags Chatterbox is trained on. Anything else in square
# brackets is passed through as literal text rather than silently swallowed, so a
# typo shows up in the audio instead of disappearing.
TAGS = frozenset({"sigh", "chuckle", "laugh", "cough", "gasp", "groan", "sniffle", "yawn"})

def _load_lexicon() -> dict[str, str]:
    candidates = [
        Path(os.getenv("LEXICON_PATH", "")),
        Path(__file__).resolve().parent.parent / "data" / "lexicon.json",
        Path(__file__).resolve().parent.parent.parent / "data" / "lexicon.json",
    ]
    for c in candidates:
        if c.is_file():
            try:
                data = json.loads(c.read_text(encoding="utf-8"))
                return {entry["pattern"]: entry["replacement"] for entry in data.get("entries", [])}
            except Exception:
                pass
    return {
        r"\bCarney's\b": "Car-nee's",
        r"\bCarney\b": "Car-nee",
        r"\bPoilievre's\b": "Pwal-ee-ev's",
        r"\bPoilievre\b": "Pwal-ee-ev",
        r"\bTrudeau's\b": "Troo-doh's",
        r"\bTrudeau\b": "Troo-doh",
        r"\bChrystia\b": "Kris-tya",
        r"\bJagmeet\b": "Jug-meet",
        r"\bLegault's\b": "Leh-goh's",
        r"\bLegault\b": "Leh-goh",
        r"\bBlanchet\b": "Blahn-shay",
        r"\bSaskatchewan\b": "Suh-skatch-uh-wun",
        r"\bCalgary\b": "Cal-gree",
        r"\bEdmonton\b": "Ed-mun-tun",
        r"\bByteDance\b": "Bite-dance",
        r"\bHuawei\b": "Hwah-way",
        r"\bNvidia's\b": "En-vid-ee-uh's",
        r"\bNvidia\b": "En-vid-ee-uh",
        r"\bNasdaq\b": "Naz-dak",
        r"\bSensex\b": "Sen-seks",
        r"\bNifty\b": "Nif-tee",
        r"\bTSMC\b": "T-S-M-C",
        r"\bNYSE\b": "N-Y-S-E",
        r"\bS&P\b": "S and P",
        r"\bDOGE\b": "Doj",
    }


# Phonetic respelling dictionary for proper nouns, Canadian/world political figures,
# and tricky names so neural TTS models (Chatterbox) pronounce them with 100% precision.
PRONUNCIATION_OVERRIDES = _load_lexicon()


# Strict broadcast-safety profanity filter: zero tolerance for vulgarity or explicit lyrics
_PROFANITY_PATTERN = re.compile(
    r"\b("
    r"fuck\w*|shit\w*|bitch\w*|asshole\w*|\bass\b|cunt\w*|dick\w*|pussy\w*|bastard\w*|"
    r"motherfuck\w*|bullshit\w*|dammit\w*"
    r")\b",
    re.IGNORECASE,
)


def sanitize_profanity(text: str) -> str:
    """Zero-tolerance broadcast profanity filter as an ultimate fail-safe before synthesis."""
    if not text:
        return ""
    return _PROFANITY_PATTERN.sub("[bleep]", text)


def voice_phonetic_normalize(text: str) -> str:
    """Normalize tricky proper nouns into phonetic spellings specifically for audio speech synthesis."""
    if not text:
        return ""
    for pattern, repl in PRONUNCIATION_OVERRIDES.items():
        text = re.sub(pattern, repl, text)
    return text

_PAUSE = re.compile(r"\[\[\s*pause\s*:\s*(\d+(?:\.\d+)?)\s*\]\]", re.I)
_ELLIPSIS = re.compile(r"\s*(?:\.\.\.+|…)\s*")
_PARAGRAPH = re.compile(r"\n\s*\n+")
_BRACKET = re.compile(r"\[([^\[\]]{1,24})\]")
_SPACE = re.compile(r"\s+")
_MARK = "\x00"

DEFAULT_BEAT = 0.55
MAX_PAUSE = 5.0
INTER_SENTENCE_PAUSE = 0.08  # Micro-breath pause between split sentences of the same speaker

# Common abbreviations, titles and honorifics that must not trigger a sentence split
ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "gen", "rep", "sen", "gov", "pres", "sec",
    "u.s", "u.k", "e.u", "d.c", "n.y", "l.a", "calif", "wash", "ont", "que", "b.c",
    "inc", "corp", "co", "ltd", "llc", "vs", "dept", "est",
    "etc", "approx", "no", "vol", "e.g", "i.e", "a.m", "p.m"
})

_SENTENCE_END = re.compile(
    r"([.!?]+)([\"'\u201d\u2019]?)\s+(?=[\"'\u201c\u2018]?[A-Z0-9])"
)

_CLAUSE_SPLIT = re.compile(
    r"(?<=[;—–])\s+|(?<=,)\s+(?=(?:and|but|while|although|where|which|as|because|since)\b)|(?<=,)\s+"
)


def _split_long_clause(clause: str, max_words: int = 20) -> list[str]:
    """Break a single long sentence (> 20 words) on natural clause and conjunction boundaries."""
    words = clause.split()
    if len(words) <= max_words:
        return [clause]

    subparts = [p.strip() for p in _CLAUSE_SPLIT.split(clause) if p.strip()]
    if len(subparts) <= 1:
        return [clause]

    grouped: list[str] = []
    current: list[str] = []
    current_len = 0
    for sp in subparts:
        sp_len = len(sp.split())
        if current and (current_len + sp_len > max_words):
            grouped.append(" ".join(current))
            current = [sp]
            current_len = sp_len
        else:
            current.append(sp)
            current_len += sp_len
    if current:
        grouped.append(" ".join(current))

    return grouped if grouped else [clause]


def split_sentences_safely(text: str, max_words: int = 20) -> list[str]:
    """Split long turns into natural sentence-sized units, avoiding mid-abbreviation breaks.

    If the text has <= max_words, it is returned untouched as a single chunk.
    Any single sentence exceeding max_words is further divided on natural clause boundaries.
    """
    words = text.split()
    if len(words) <= max_words:
        return [text]

    parts: list[str] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        end = match.end()
        candidate = text[start:match.start() + len(match.group(1)) + len(match.group(2))].strip()
        last_word = candidate.split()[-1].rstrip(".!?\"'\u201d\u2019").lower()
        if last_word in ABBREVIATIONS:
            continue
        if len(last_word) == 1 and last_word.isalpha():
            continue

        parts.append(candidate)
        start = end

    remainder = text[start:].strip()
    if remainder:
        parts.append(remainder)

    if not parts:
        return [text]

    # Further break any individual part that still exceeds max_words
    refined_parts: list[str] = []
    for p in parts:
        if len(p.split()) > max_words:
            refined_parts.extend(_split_long_clause(p, max_words=max_words))
        else:
            refined_parts.append(p)

    grouped: list[str] = []
    current: list[str] = []
    current_len = 0
    for p in refined_parts:
        p_len = len(p.split())
        if current and (current_len + p_len > max_words):
            grouped.append(" ".join(current))
            current = [p]
            current_len = p_len
        else:
            current.append(p)
            current_len += p_len
    if current:
        grouped.append(" ".join(current))

    return grouped


@dataclass(frozen=True)
class Say:
    """A span of text to voice."""

    text: str


@dataclass(frozen=True)
class Pause:
    """Silence to leave before the next span."""

    seconds: float


def _tidy(text: str) -> str:
    return _SPACE.sub(" ", text).strip()


def parse(text: str, *, beat: float = DEFAULT_BEAT) -> list[Say | Pause]:
    """Split ``text`` into alternating speech spans and pauses.

    Adjacent pauses are summed and leading or trailing pauses dropped, so the
    result always begins and ends with something to say.

    Long speech spans (> 22 words) are safely split into complete sentences separated
    by natural 0.08s breath pauses, ensuring neural TTS inference stays in its
    optimal low-latency, low-memory operating envelope.
    """
    text = (text or "").strip()
    if not text:
        return []

    # Ultimate fail-safe broadcast profanity sanitizer
    text = sanitize_profanity(text)

    # Phonetic pronunciation overrides for tricky proper nouns
    text = voice_phonetic_normalize(text)

    # Em-dashes and en-dashes cause Chatterbox's punc_norm to convert them to
    # hyphens, making the voice rush through without breathing. Replace them
    # with a comma so the voice pauses naturally.
    text = re.sub(r"\s*[—–]\s*", ", ", text)
    text = re.sub(r"\s+-\s+", ", ", text)
    text = re.sub(r",\s*,+", ",", text)
    text = re.sub(r",\s*([.!?])", r"\1", text)

    # Unify every "pause here" spelling behind one sentinel, prefixed so a span
    # that happens to be all digits ("2026") is never mistaken for a duration.
    # A blank line is a paragraph break, which reads as a beat of its own.
    text = _PARAGRAPH.sub(f"{_MARK}p:{beat}{_MARK}", text)
    text = _PAUSE.sub(lambda m: f"{_MARK}p:{m.group(1)}{_MARK}", text)
    text = _ELLIPSIS.sub(f"{_MARK}p:{beat}{_MARK}", text)

    out: list[Say | Pause] = []
    for part in text.split(_MARK):
        part = _tidy(part)
        if not part:
            continue
        if part.startswith("p:"):
            seconds = min(float(part[2:]), MAX_PAUSE)
            if seconds <= 0:
                continue
            if out and isinstance(out[-1], Pause):
                out[-1] = Pause(round(out[-1].seconds + seconds, 3))
            else:
                out.append(Pause(seconds))
        else:
            sentences = split_sentences_safely(part, max_words=20)
            if len(sentences) > 1:
                for s_idx, sentence in enumerate(sentences):
                    out.append(Say(sentence))
                    if s_idx < len(sentences) - 1:
                        out.append(Pause(INTER_SENTENCE_PAUSE))
            else:
                out.append(Say(part))

    while out and isinstance(out[0], Pause):
        out.pop(0)
    while out and isinstance(out[-1], Pause):
        out.pop()
    return out


def spans(text: str, *, beat: float = DEFAULT_BEAT) -> list[str]:
    """Just the text that will be voiced, for previews and card copy."""
    return [item.text for item in parse(text, beat=beat) if isinstance(item, Say)]


def tags(text: str) -> list[str]:
    """Bracketed tokens that are not tags we know, so callers can warn."""
    text = _PAUSE.sub(" ", text or "")
    return [t for t in _BRACKET.findall(text) if t.strip().lower() not in TAGS]


def plain(text: str) -> str:
    """The script without pause markers or tags: what a card should display."""
    text = _PAUSE.sub(" ", text or "")
    return _tidy(_BRACKET.sub(" ", text))
