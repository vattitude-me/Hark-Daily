"""Podcast text cleaning, anti-slop normalization, and turn validation helpers."""
from __future__ import annotations

import logging
import re

from . import topics
from .summarizer import drop_boilerplate
from .tts.text import clean_punctuation, voice_normalize

log = logging.getLogger(__name__)

# Word caps per piece keep the whole banter to roughly 60-90 seconds: news is the priority.
MAX_WORDS = {"open": 55, "open_ca": 55, "open_us": 55, "open_in": 55, "tease": 38, "bridge": 20, "close": 42}
MAX_TURNS = {"open": 6, "open_ca": 6, "open_us": 6, "open_in": 6, "tease": 3, "bridge": 2, "close": 4}

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

HEAVY_SECTIONS = frozenset({"top", "politics", "markets"})

# Chatterbox performs these tags itself (matches voice_service/turbo_voice/text.py).
TAGS = ("laugh", "chuckle", "sigh", "cough", "gasp", "groan", "sniffle", "yawn")
MAX_TAGS = 2
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

Turn = tuple[int, str]  # (0 or 1 for host A or B, text which may carry [tags])

_SOURCE_SUFFIX_RE = re.compile(
    r"\s*(?:[|—–-]\s*(?:CBC News|The Verge|Variety|CBS Sports|The Hindu|Economic Times|ET Tech|"
    r"Indian Express|ESPNcricinfo|New York Times|NYT|MarketWatch|NPR|TechCrunch|BetaKit|"
    r"ScienceDaily|Reuters|AP News|Bloomberg|BBC News|CNN|The Globe and Mail).*)$",
    re.I,
)
_BAD = re.compile(r"https?://|www\.|[*_#`<>\[\]{}]|\bhttp", re.I)
_PROFANITY_PATTERN = re.compile(
    r"\b("
    r"fuck\w*|shit\w*|bitch\w*|asshole\w*|\bass\b|cunt\w*|dick\w*|pussy\w*|bastard\w*|"
    r"motherfuck\w*|bullshit\w*|dammit\w*"
    r")\b",
    re.IGNORECASE,
)

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

ALIEN_BRIDGE_TERMS: dict[str, re.Pattern] = {
    "science": re.compile(
        r"\b(sports?|athletes?|game|scores?|nfl|nba|nhl|mlb|brier|cricket|tournament|league|gridiron|"
        r"politics?|parliament|congress|senate|election|campaign|markets?|wall street|stocks?|investors?|"
        r"nasdaq|dow|entertainment|hollywood|box office|movie|film|actor|actress|album)\b",
        re.I,
    ),
    "sports": re.compile(
        r"\b(science|scientific|laboratory|scientists?|biology|physics|astronomy|top headlines?|lead stories|"
        r"top stories|global headlines?|politics?|parliament|congress|senate|election|campaign|markets?|"
        r"wall street|stocks?|shares?|investors?|nasdaq|dow)\b",
        re.I,
    ),
    "entertainment": re.compile(
        r"\b(science lab|science|scientific|laboratory|biology|physics|sports?|nfl|nba|nhl|mlb|cricket|"
        r"gridiron|markets?|wall street|stocks?|nasdaq|dow)\b",
        re.I,
    ),
    "markets": re.compile(
        r"\b(artificial intelligence boom|ai boom|over in ai|sports?|entertainment|hollywood|movie|"
        r"politics?|parliament|congress|senate|election)\b",
        re.I,
    ),
    "ai": re.compile(r"\b(broader tech sector|tech space|national politics|politics?|sports?|entertainment|hollywood)\b", re.I),
    "tech": re.compile(r"\b(national politics|politics?|parliament|congress|senate|election|sports?|entertainment|hollywood)\b", re.I),
    "politics": re.compile(r"\b(lighter story|entertainment|hollywood|creative world|box office|sports?|nfl|nba|cricket|science|laboratory)\b", re.I),
    "top": re.compile(r"\b(financial markets?|markets?|wall street|stocks?|sports?|entertainment|hollywood)\b", re.I),
}

_SPEAKER_TAG = re.compile(r"\[(Matthew|Kelly|Host|Speaker\s*\d+)\]\s*", re.I)

_ABBR_SPLIT_PROTECT = re.compile(
    r"\b("
    r"mr|mrs|ms|dr|prof|sr|jr|gen|rep|sen|gov|pres|sec|st|capt|lt|col|maj|rev|"
    r"u\.s|u\.k|e\.u|d\.c|n\.y|l\.a|calif|wash|ont|que|b\.c|inc|corp|co|ltd|llc|vs|dept|est|"
    r"etc|approx|no|vol|e\.g|i\.e|a\.m|p\.m|[A-Za-z]"
    r")\.",
    re.IGNORECASE,
)

UNBOUND_CATEGORY_NOUNS = frozenset({
    "series", "show", "drama", "comedy", "movie", "film", "franchise", "documentary", "podcast", "album", "song", "track",
    "company", "firm", "startup", "corporation", "carmaker", "automaker", "retailer", "carrier", "airline", "bank",
    "platform", "app", "website", "service", "tool", "network", "system", "device", "model",
    "team", "club", "squad", "player", "athlete", "coach", "manager", "driver",
    "artist", "singer", "musician", "band", "actor", "actress", "creator", "director", "author", "writer",
    "minister", "premier", "prime minister", "president", "governor", "mayor", "politician", "lawmaker", "senator",
    "government", "agency", "department", "ministry", "board", "committee", "regulator",
    "deal", "merger", "acquisition", "settlement", "agreement", "pact", "contract",
    "case", "lawsuit", "suit", "trial", "probe", "investigation", "inquiry",
    "study", "report", "survey", "project", "initiative", "program", "plan", "bill", "law",
})

DANGLING_OPENER_RE = re.compile(
    r"^(?:(?:sources|insiders|reports)\s+say(?:,\s*|\s+that\s+|\s+)|according to (?:sources|reports),\s*)?"
    r"(?:the\s+(?:[a-z\-]+\s+)?(?:" + "|".join(UNBOUND_CATEGORY_NOUNS) + r")|he|she|they|it)\b",
    re.I,
)

_HEADLINE_LEAD_STOP = frozenset({
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "sources", "reports", "say", "says", "said", "new", "get", "gets", "getting", "two", "three",
})

_VERB_BOUNDARY_RE = re.compile(
    r"\b(?:is|are|was|were|has|have|had|could|can|may|might|will|would|should|to\s+[a-z]+|"
    r"announces?|unveils?|launches?|reports?|recalls?|faces?|beats?|hits?|drops?|falls?|rises?|jumps?|"
    r"names?|appoints?|wins?|loses?|buys?|acquires?|sells?|warns?|eyes?|seeks?|plans?|considers?|"
    r"could\s+be\s+getting|could\s+get|set\s+to|poised\s+to|slated\s+to)\b",
    re.I,
)


def _clean(text: str) -> str:
    return clean_punctuation(str(text or ""), collapse_whitespace=True)


def clean_headline(title: str) -> str:
    """Strip wire and publisher branding suffixes (e.g. ' | CBC News', ' - The Verge') from titles."""
    return _SOURCE_SUFFIX_RE.sub("", _clean(title or "")).strip()


def sanitize_profanity(text: str) -> str:
    """Scrub any vulgarity, swear words or explicit lyrics into clean broadcast language."""
    return _PROFANITY_PATTERN.sub("[bleep]", text) if text else ""


def _preserve_case(match: re.Match, replacement: str) -> str:
    matched = match.group(0)
    if matched and matched[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def strip_repetition_stutter(text: str) -> str:
    """Detect and remove repeated restart phrases (e.g. 'Intro cut off Intro full sentence')."""
    words = text.split()
    if len(words) < 10 or len(set(words)) < 6:
        return text
    for n in range(min(12, len(words) // 2), 4, -1):
        for i in range(len(words) - 2 * n):
            phrase = " ".join(words[i : i + n])
            rest = " ".join(words[i + n :])
            if phrase in rest:
                return rest[rest.index(phrase):]
    return text


def clean_slop(text: str) -> str:
    """Strip or normalize robotic AI slop phrases and textual shorthand into spoken English."""
    cleaned = strip_repetition_stutter(text)
    for pattern, repl in SLOP_PATTERNS:
        cleaned = pattern.sub(lambda m, r=repl: _preserve_case(m, r), cleaned)
    return " ".join(voice_normalize(cleaned, preserve_tags=True).split())


def strip_tags(text: str) -> str:
    """Return spoken words alone without Chatterbox paralinguistic tags."""
    return _clean(_TAG.sub(" ", text))


def strip_speaker_prefix(text: str, hosts: tuple[str, str] = ("Matthew", "Kelly")) -> str:
    """Strip accidental leading speaker labels (e.g. 'Kelly:', '[Matthew]', '**Kelly:**')."""
    cleaned = _clean(text)
    if not cleaned:
        return ""
    host_names: list[str] = []
    seen_lower: set[str] = set()
    for name in (*hosts, "Matthew", "Kelly"):
        n = str(name or "").strip()
        if n and n.lower() not in seen_lower:
            seen_lower.add(n.lower())
            host_names.append(re.escape(n))
    names_alt = "|".join(host_names) if host_names else "Matthew|Kelly"
    generic_roles = r"Host(?:\s*[AB12])?|Speaker\s*[AB12]?|Narrator"
    all_labels = rf"{names_alt}|{generic_roles}|a|b"
    named_labels = rf"{names_alt}|{generic_roles}"
    patterns = (
        re.compile(rf"^(?:\*\*|__)?\[(?:{all_labels})\](?:\*\*|__)?(?:\s*:\s*(?:\*\*|__)?|\s+[-–—]\s+)?\s*", re.I),
        re.compile(rf"^(?:\*\*|__)?(?:{all_labels})\s*(?:(?:\*\*|__)\s*:|:\s*(?:\*\*|__)?)\s*", re.I),
        re.compile(rf"^(?:\*\*|__)(?:{named_labels})(?:\*\*|__)\s*[-–—]\s*", re.I),
        re.compile(rf"^(?:{generic_roles})\s+[-–—]\s+", re.I),
    )
    stripped_any = False
    while cleaned:
        updated = cleaned
        for pat in patterns:
            candidate = pat.sub("", updated).strip()
            if candidate != updated:
                updated = candidate
                stripped_any = True
        if updated == cleaned:
            break
        cleaned = updated
    if stripped_any and cleaned and cleaned[0].isalpha() and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def sanitize_turn_text(raw_text: str, hosts: tuple[str, str] = ("Matthew", "Kelly")) -> str:
    """Normalize tags, strip speaker labels/AI slop/shorthand for one spoken turn."""
    text = strip_speaker_prefix(raw_text, hosts)
    text = _clean(_TAG.sub(lambda m: f"[{m.group(1).lower()}]", text))
    text = clean_slop(text)
    return strip_speaker_prefix(text, hosts)


def _enforce_host_identity(text: str, who: str, hosts: tuple[str, str]) -> str | None:
    """Repair inverted self-introductions and reject contradictory speaker identity claims."""
    if len(hosts) != 2:
        return text
    this_name, other_name = (hosts[0], hosts[1]) if who == "a" else (hosts[1], hosts[0])
    re_other_and = re.compile(rf"\b(and\s+)?(i\s+am|i'm)\s+{re.escape(other_name)}\b", re.I)
    if re_other_and.search(text):
        text = re_other_and.sub(lambda m: f"{m.group(1) or ''}I am {this_name}", text)
    if re.search(rf"\b(?:i\s+am|i'm|this\s+is)\s+{re.escape(other_name)}\b", text, re.I):
        return None
    return text


def validate_turns(raw, kind: str, section: str | None = None,
                   hosts: tuple[str, str] = ("Matthew", "Kelly")) -> list[Turn] | None:
    """Validate and normalize AI banter JSON for one piece, or return None on rule violation."""
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_TURNS[kind]:
        return None
    turns: list[Turn] = []
    words = tags = 0
    base_sec = topics.base_section(section)
    for item in raw:
        if not isinstance(item, dict):
            return None
        who = str(item.get("speaker", "")).strip().lower()
        text = sanitize_turn_text(item.get("text", ""), hosts)
        text = _enforce_host_identity(text, who, hosts)
        if text is None:
            return None
        words_only = strip_tags(text)
        if who not in ("a", "b") or not words_only or _BAD.search(words_only) or _PROFANITY_PATTERN.search(words_only):
            return None
        tags += len(_TAG.findall(text))
        if base_sec in SOBER_SECTIONS:
            text = words_only
        words += len(words_only.split())
        turns.append((0 if who == "a" else 1, text))
    if words > MAX_WORDS[kind] or tags > MAX_TAGS:
        return None
    if kind == "bridge" and section:
        alien = ALIEN_BRIDGE_TERMS.get(base_sec)
        full_text = " ".join(t[1] for t in turns)
        if alien and alien.search(full_text):
            log.warning("Rejecting mismatched bridge for %s: contains alien category reference %r", section, full_text[:80])
            return None
    return turns


def extract_headline_lead_entity(headline: str) -> list[str]:
    """Extract candidate lead entity tokens from a story headline."""
    clean_h = re.sub(r"^(?:report|exclusive|update|sources|breaking|analysis|watch)\s*[:—\-]\s*", "",
                     headline.strip().rstrip(".,!?"), flags=re.I)
    verb_boundary = _VERB_BOUNDARY_RE.search(clean_h)
    if verb_boundary and verb_boundary.start() > 3:
        entity_phrase = clean_h[:verb_boundary.start()].strip()
    else:
        words = clean_h.split()
        entity_phrase = " ".join(words[:min(4, len(words))])
    tokens = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", entity_phrase)
              if w.lower() not in _HEADLINE_LEAD_STOP and len(w) >= 3]
    if tokens:
        return tokens
    return [w.lower() for w in re.findall(r"[A-Za-z0-9]+", clean_h)
            if w.lower() not in _HEADLINE_LEAD_STOP and len(w) >= 3]


def is_unbound_story_lead(turn_text: str, headline: str) -> bool:
    """Return True if Turn 1 opens with an unbound determiner or omits the headline's subject entity."""
    clean_turn = turn_text.strip()
    if not clean_turn:
        return True
    if DANGLING_OPENER_RE.search(clean_turn):
        subj_tokens = extract_headline_lead_entity(headline)
        turn_lower = clean_turn.lower()
        return not (subj_tokens and any(token in turn_lower for token in subj_tokens))
    return False


def _is_redundant_with_headline(fact_text: str, headline: str) -> bool:
    """Return True if fact_text has high token overlap (>=50% of its tokens) with the headline."""
    h_tokens = {w for w in re.findall(r"[a-z0-9]+", headline.lower()) if len(w) >= 3 and w not in _HEADLINE_LEAD_STOP}
    f_tokens = {w for w in re.findall(r"[a-z0-9]+", fact_text.lower()) if len(w) >= 3 and w not in _HEADLINE_LEAD_STOP}
    if not f_tokens or not h_tokens:
        return False
    return (len(f_tokens & h_tokens) / len(f_tokens)) >= 0.50


def _split_sentences(text: str) -> list[str]:
    """Split text into clean, deduplicated sentences with >=4 words while protecting abbreviations."""
    raw_clean = _SPEAKER_TAG.sub("", str(text or ""))
    cleaned = _clean(drop_boilerplate(raw_clean) or raw_clean)
    if not cleaned:
        return []
    protected = _ABBR_SPLIT_PROTECT.sub(r"\1«DOT»", cleaned)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", protected)
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        restored = p.replace("«DOT»", ".")
        s = _clean(_SPEAKER_TAG.sub("", restored)).strip()
        if len(s.split()) < 4:
            continue
        key = s.lower()
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def transcript(turns: list[Turn], hosts: tuple[str, str] = ("Matthew", "Kelly")) -> str:
    """Render banter turns as plain caption lines stripped of speaker prefixes and tags."""
    return "\n".join(strip_tags(strip_speaker_prefix(text, hosts)) for _, text in turns)
