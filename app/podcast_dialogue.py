"""Two-host story dialogue generation, validation, fallback, and TTS synthesis."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from . import audio, llm, topics
from .podcast_prompts import (
    _ANGLE_LENS,
    SOBER_STORY_FORMAT_KEYS,
    STORY_DIALOGUE_PROMPT,
    STORY_FORMAT_KEYS,
    STORY_FORMATS,
)
from .podcast_text import (
    _BAD,
    _PROFANITY_PATTERN,
    _TAG,
    _TAG_START,
    HEAVY_SECTIONS,
    MAX_TAGS,
    SOBER_KEYWORDS,
    SOBER_SECTIONS,
    TONE,
    _clean,
    _is_redundant_with_headline,
    _split_sentences,
    clean_headline,
    is_unbound_story_lead,
    sanitize_turn_text,
    strip_repetition_stutter,
    strip_speaker_prefix,
    strip_tags,
)
from .summarizer import strip_metadata_noise
from .tts import SAMPLE_RATE
from .tts.text import voice_normalize

log = logging.getLogger(__name__)

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

_SCRIPT_LINE_RE = re.compile(r"^\s*\[?([A-Za-z]+)\]?\s*:\s*(.+)$")
_METADATA_LINE_RE = re.compile(
    r"\b(?:date|source|summary|journal reference)\s*[:;,]+\s*"
    r"(?:november|december|january|february|march|april|may|june|july|august|"
    r"september|october|\d{4}|reuters|associated press|nasa)\b",
    re.I,
)
_ROBO_FILLER_RE = re.compile(
    r"\b(?:reporting (?:there )?from|that comes from|key developments we are tracking|"
    r"here is what is developing|leading our coverage today|full details on that story)\b",
    re.I,
)
_EXTRA_TOPIC_STOP = frozenset({"full", "text", "report", "reports", "news", "story", "stories", "ceo"})


def _resolve_agy_bin() -> str | None:
    """Resolve _agy_bin via app.podcast when loaded so test monkeypatches on podcast._agy_bin apply."""
    mod = sys.modules.get("app.podcast")
    fn = getattr(mod, "_agy_bin", None) if mod is not None else None
    return fn() if callable(fn) else llm.agy_bin()


def is_solo_format(fmt_key: str | None) -> bool:
    """Return True if the story format is anchored by a single host."""
    return fmt_key in ("solo_matthew", "solo_kelly")


def solo_host_index(fmt_key: str | None, hosts: tuple[str, str] = ("Matthew", "Kelly")) -> int:
    """Return speaker index for a solo format: 0 for host A, 1 for host B."""
    return 1 if fmt_key == "solo_kelly" else 0


def select_story_format(
    section: str,
    rank: int,
    *,
    sober: bool = False,
    previous_format: str | None = None,
) -> tuple[str, str]:
    """Deterministically pick one story format so adjacent stories never repeat the same format."""
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
    base_sec = topics.base_section(brief.get("section") or "top")
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
    speaker: int
    text: str
    purpose: str = "context"
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


def _story_dialogue_obj(
    brief: dict,
    turns: list[DialogueTurn],
    *,
    summary: str | None = None,
    writer: str = "built-in",
    story_format: str = "question_led",
) -> StoryDialogue:
    return StoryDialogue(
        story_id=brief["story_id"],
        section=brief["section"],
        headline=brief["headline"],
        summary=summary if summary is not None else brief["summary"],
        turns=turns,
        writer=writer,
        story_format=story_format,
    )


def build_story_brief(story: dict) -> dict:
    """Extract a grounded factual brief (F1..Fn) from an enriched story dict."""
    sec = str(story.get("section") or "top")
    base_sec = topics.base_section(sec)
    raw_head = clean_headline(story.get("title") or story.get("headline") or "")
    headline = voice_normalize(_clean(raw_head).rstrip("."), preserve_tags=False)
    raw_source = _clean(story.get("source") or "News wire")
    source = raw_source.split("·")[0].strip() or raw_source
    raw_sum = strip_metadata_noise(story.get("summary") or "")
    summary = voice_normalize(_clean(raw_sum), preserve_tags=False)
    raw_body = strip_metadata_noise(str(story.get("article_text") or story.get("summary") or story.get("script") or ""))

    candidates: list[str] = []
    if summary:
        candidates.extend(_split_sentences(summary))
    if raw_body and raw_body != summary:
        candidates.extend(_split_sentences(raw_body))

    head_norm = headline.lower().rstrip(".")
    seen_facts: set[str] = {head_norm, *{p.lower().rstrip(".") for p in _split_sentences(headline)}}

    facts: list[dict[str, str]] = []
    if headline:
        facts.append({"id": "F1", "fact": headline if headline.endswith((".", "!", "?")) else f"{headline}."})

    for sent in candidates:
        s_clean = strip_repetition_stutter(_clean(sent))
        if not s_clean or len(s_clean.split()) < 3:
            continue
        if re.search(r"\b(?:date|source|summary|author|published|journal reference)\s*[:;,]", s_clean, re.I):
            continue
        v_fact = voice_normalize(s_clean, preserve_tags=False)
        v_norm = v_fact.lower().rstrip(".")
        if v_norm in seen_facts:
            continue
        seen_facts.add(v_norm)
        facts.append({"id": f"F{len(facts) + 1}", "fact": v_fact if v_fact.endswith((".", "!", "?")) else f"{v_fact}."})
        if len(facts) >= 6:
            break

    has_sensitive_keyword = any(kw in headline.lower() or kw in summary.lower() for kw in SOBER_KEYWORDS)
    return {
        "story_id": str(story.get("id") or story.get("url") or f"{sec}-{story.get('rank', 1)}"),
        "section": sec,
        "section_title": topics.ALL_SECTIONS.get(sec, {}).get("title", sec.title()),
        "rank": int(story.get("rank") or 1),
        "headline": headline,
        "source": source,
        "summary": summary or headline,
        "tone": TONE.get(base_sec, "warm and informative"),
        "sober": (base_sec in SOBER_SECTIONS) or has_sensitive_keyword,
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


def _clean_opening_turn(text: str, story_brief: dict) -> str | None:
    """Apply adjacent-story anti-repetition & headline guards on Turn 1; return None if rejected."""
    prev_lead = str(story_brief.get("prev_lead") or "").strip().lower()
    if prev_lead:
        if re.search(r"^\s*(?:and\s+)?staying\s+with\b", prev_lead):
            bad_stay = re.compile(r"^\s*(?:and\s+)?staying\s+with\s+[^,]+,\s*", re.I)
            if bad_stay.search(text):
                text = bad_stay.sub("", text).strip()
                if text and text[0].islower():
                    text = text[0].upper() + text[1:]
        prev_stem = " ".join(re.findall(r"[a-z0-9]+", prev_lead)[:4])
        curr_stem = " ".join(re.findall(r"[a-z0-9]+", text.lower())[:4])
        if prev_stem and curr_stem and prev_stem == curr_stem:
            return None

    for term in story_brief.get("shared_prev_terms") or ():
        bad_shift = re.compile(
            rf"^\s*(?:and\s+)?(?:turn(?:ing)?(?:\s+now)?|switch(?:ing)?(?:\s+now)?|"
            rf"shifting(?:\s+now)?|over(?:\s+now)?)\s+(?:to|at)\s+{re.escape(term)}\s*(?:,\s*where\s+|,\s*)",
            re.I,
        )
        if bad_shift.search(text):
            stripped = bad_shift.sub("", text).strip()
            if stripped:
                text = f"Also at {term.title()}, {stripped[0].lower()}{stripped[1:]}"
                break

    words_only = strip_tags(text)
    h_clean = re.sub(r"[^a-z0-9 ]+", "", story_brief.get("headline", "").lower()).strip()
    w_clean = re.sub(r"[^a-z0-9 ]+", "", words_only.lower()).strip()
    if h_clean and (w_clean == h_clean or w_clean.startswith(h_clean)):
        return None
    if is_unbound_story_lead(words_only, str(story_brief.get("headline") or "")):
        log.debug("Rejecting story dialogue: Turn 1 missing headline entity or unbound lead: %s", words_only[:80])
        return None
    return text


def validate_story_dialogue(
    raw: dict | list | str | None,
    story_brief: dict,
    hosts: tuple[str, str] = ("Matthew", "Kelly"),
    *,
    min_turns: int | None = None,
    max_turns: int | None = None,
) -> list[DialogueTurn] | None:
    """Validate LLM-generated story dialogue turns against podcast editorial & TTS rules."""
    fmt_key = str(story_brief.get("story_format") or "")
    is_solo = is_solo_format(fmt_key)
    solo_spk = solo_host_index(fmt_key, hosts) if is_solo else None
    min_turns = (1 if is_solo else 2) if min_turns is None else min_turns
    max_turns = (3 if is_solo else 7) if max_turns is None else max_turns

    if isinstance(raw, str):
        raw = parse_story_dialogue_payload(raw, hosts)
    turns_raw = raw.get("turns") if isinstance(raw, dict) else raw
    if not isinstance(turns_raw, list) or not (min_turns <= len(turns_raw) <= max_turns):
        return None

    sober = bool(story_brief.get("sober"))
    valid_fact_ids = {f["id"] for f in story_brief.get("facts", []) if isinstance(f, dict) and "id" in f}
    parsed: list[DialogueTurn] = []
    total_words = total_tags = consecutive = 0
    last_speaker: int | None = None

    for item in turns_raw:
        if not isinstance(item, dict):
            return None
        who = _speaker_index(item.get("speaker", ""), hosts)
        if who is None or (is_solo and who != solo_spk):
            return None
        if not is_solo:
            consecutive = consecutive + 1 if who == last_speaker else 1
            if consecutive > 2:
                return None
            last_speaker = who

        text = sanitize_turn_text(item.get("text", ""), hosts)
        if len(parsed) == 1 and not is_solo:
            text = _clean(_TAG_START.sub("", text))

        words_only = strip_tags(text)
        word_count = len(words_only.split())
        if (
            not words_only
            or not (1 <= word_count <= 68)
            or _BAD.search(words_only)
            or _PROFANITY_PATTERN.search(words_only)
            or _METADATA_LINE_RE.search(text)
            or _ROBO_FILLER_RE.search(text)
        ):
            return None

        if any(len([w for w in s.strip().split() if w]) > 24 for s in re.split(r"(?<=[.!?])\s+", words_only)):
            return None

        if not parsed:
            text_or_none = _clean_opening_turn(text, story_brief)
            if text_or_none is None:
                return None
            text = text_or_none
            words_only = strip_tags(text)
            word_count = len(words_only.split())

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
        parsed.append(DialogueTurn(who, text, purpose, fact_refs, pause_after))

    if is_solo:
        if not (18 <= total_words <= 120):
            return None
    elif len({t.speaker for t in parsed}) < 2 or not (20 <= total_words <= 190):
        return None
    if not sober and total_tags > MAX_TAGS:
        return None
    return parsed


def _make_turn(speaker: int, fact: tuple[str, str], purpose: str) -> DialogueTurn:
    return DialogueTurn(
        speaker=speaker,
        text=fact[1],
        purpose=purpose,
        fact_refs=[fact[0]],
        pause_after=PURPOSE_PAUSES[purpose],
    )


def fallback_story_dialogue(story: dict, hosts: tuple[str, str] = ("Matthew", "Kelly")) -> StoryDialogue:
    """Deterministic, strictly factual exchange built from extracted article sentences."""
    brief = build_story_brief(story)
    base_sec = topics.base_section(brief.get("section") or "top")
    lead_speaker = 0 if (brief["sober"] or base_sec in HEAVY_SECTIONS or brief["rank"] % 2 == 1) else 1
    co_speaker = 1 - lead_speaker
    headline_raw = brief["headline"].rstrip(".")
    headline_sent = headline_raw if headline_raw.endswith((".", "!", "?")) else f"{headline_raw}."
    fmt_key, _ = select_story_format(brief["section"], brief["rank"], sober=brief["sober"])

    body_facts: list[tuple[str, str]] = []
    seen_body = {headline_raw.lower().rstrip(".")}
    for f in brief["facts"]:
        fid = str(f.get("id") or "F1")
        if fid == "F1":
            continue
        txt = f.get("fact", "").strip()
        norm = txt.lower().rstrip(".")
        if norm and norm not in seen_body:
            seen_body.add(norm)
            body_facts.append((fid, txt))

    lead_is_unbound = bool(body_facts and is_unbound_story_lead(body_facts[0][1], brief["headline"]))
    if body_facts and not lead_is_unbound:
        if len(body_facts) == 1 and brief["rank"] > 1:
            lead_fact, remaining_facts = ("F1", headline_sent), body_facts
        else:
            lead_fact, remaining_facts = body_facts[0], body_facts[1:]
    else:
        lead_fact = ("F1", headline_sent)
        candidate_facts = body_facts[1:] if lead_is_unbound else body_facts
        remaining_facts = [bf for bf in candidate_facts if not _is_redundant_with_headline(bf[1], brief["headline"])]

    if is_solo_format(fmt_key):
        solo_spk = solo_host_index(fmt_key, hosts)
        turns = [_make_turn(solo_spk, lead_fact, "lead")]
        if remaining_facts:
            turns.append(_make_turn(solo_spk, remaining_facts[0], "takeaway"))
        if len(remaining_facts) > 1 and len(lead_fact[1].split()) + len(remaining_facts[0][1].split()) < 35:
            turns.append(DialogueTurn(solo_spk, remaining_facts[1][1], "context", [remaining_facts[1][0]], PURPOSE_PAUSES["takeaway"]))
        return _story_dialogue_obj(brief, turns, story_format=fmt_key)

    if not remaining_facts:
        return _story_dialogue_obj(
            brief, [_make_turn(lead_speaker, lead_fact, "lead")],
            story_format="solo_matthew" if lead_speaker == 0 else "solo_kelly",
        )

    if len(remaining_facts) == 1 or fmt_key == "lead_takeaway":
        return _story_dialogue_obj(
            brief,
            [_make_turn(lead_speaker, lead_fact, "lead"), _make_turn(co_speaker, remaining_facts[0], "takeaway")],
            story_format="lead_takeaway",
        )

    schedule = [(co_speaker, "context"), (lead_speaker, "implication"), (co_speaker, "takeaway")]
    turns = [_make_turn(lead_speaker, lead_fact, "lead")]
    for fact, (spk, purpose) in zip(remaining_facts, schedule):
        turns.append(_make_turn(spk, fact, purpose))
    return _story_dialogue_obj(brief, turns, story_format=fmt_key)


def _shared_topic_terms(prev_headline: str, curr_headline: str) -> list[str]:
    """Return shared substantive subject words between two consecutive headlines."""
    stop = topics._TOPIC_STOP | _EXTRA_TOPIC_STOP
    p_words = [w for w in re.findall(r"[a-z0-9]+", (prev_headline or "").lower()) if len(w) >= 4 and w not in stop]
    c_set = {w for w in re.findall(r"[a-z0-9]+", (curr_headline or "").lower()) if len(w) >= 4 and w not in stop}
    shared: list[str] = []
    for w in p_words:
        if w in c_set and w not in shared:
            shared.append(w)
    return shared


def _dialogue_cache_path(cfg, brief: dict, hosts: tuple[str, str], fmt_key: str = "",
                         prev_title: str = "", prev_lead: str = "") -> Path | None:
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
            "prev": prev_title[:120],
            "prev_lead": prev_lead[:80],
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return folder / f"{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:16]}.{STORY_DIALOGUE_VERSION}.json"


def _extract_prev_lead(previous_story: dict | None, previous_dialogue: StoryDialogue | None) -> str:
    if previous_dialogue and getattr(previous_dialogue, "turns", None):
        return _clean(previous_dialogue.turns[0].text)
    if not previous_story:
        return ""
    raw_prev = str(previous_story.get("script") or "")
    m = re.search(r"\[(?:Matthew|Kelly|[A-Za-z]+)\]\s*([^[\n]+)", raw_prev)
    if m:
        return _clean(m.group(1))
    sents = _split_sentences(raw_prev)
    return _clean(sents[0]) if sents else ""


def _build_transition_instruction(brief: dict, prev_title: str, prev_lead: str, shared_terms: list[str]) -> str:
    if brief["rank"] <= 1 and not prev_title:
        return ("Transition: This is the first story in the section. Open directly into the story hook with no greeting, "
                "no show intro, and no 'Next up'.")
    if prev_title and shared_terms:
        topic_str = ", ".join(t.title() for t in shared_terms[:3])
        anti_repeat = ""
        if prev_lead:
            anti_repeat = (
                f'\nCRITICAL ANTI-ITERATION RULE: The previous story opened with:\n  "{prev_lead[:120]}"\n'
                f"You MUST NOT use similar opening words, repetitive transition formulas, or repeat phrases like "
                f"'Staying with {shared_terms[0].title()} for a moment'. Use a completely different angle connector."
            )
        return (
            f"Transition: CONTINUING DEVELOPING STORY ({topic_str}) WITH A DISTINCT ANGLE.\n"
            f"The previous story was '{prev_title[:90]}', which already introduced the initial angle.\n"
            f"CRITICAL: Do NOT introduce {topic_str} as if it is a brand new subject (never say 'Turn now to {topic_str}' or 'Turning to {topic_str}').\n"
            f"At the same time, NEVER repeat formulaic pivot crutches like 'Staying with {shared_terms[0].title()} for a moment'.\n"
            f"Connect organically based on the specific new angle.{anti_repeat}"
        )
    if prev_title:
        return (
            f"Transition: The previous story in this section was '{prev_title[:90]}'. "
            "Begin Turn 1 with a subtle thematic link, a brief reaction pivot, or a natural conversational shift "
            "('Speaking of money...', 'On a very different note...', 'Meanwhile,'). Do NOT overuse 'Next up', 'Moving on', or 'Turn now to'."
        )
    return "Transition: Begin Turn 1 directly with the news hook without repeating 'Next up', 'Moving on', or 'Turn now to'."


def _dialogue_shape_instruction(fmt_key: str, hosts: tuple[str, str], lead_speaker: str, co_speaker: str) -> str:
    if is_solo_format(fmt_key):
        idx = solo_host_index(fmt_key, hosts)
        letter = "a" if idx == 0 else "b"
        return f"""Return ONLY valid JSON of this exact shape (1 to 2 turns total by {hosts[idx]} ('{letter}'), 25 to 65 words total across all turns):
{{
  "summary": "1-2 sentence neutral card summary (30-50 words) built strictly from the facts",
  "turns": [
    {{"speaker": "{letter}", "purpose": "lead", "fact_refs": ["F1"], "text": "..."}},
    {{"speaker": "{letter}", "purpose": "takeaway", "fact_refs": ["F2"], "text": "..."}}
  ]
}}"""
    if fmt_key == "lead_takeaway":
        return f"""Return ONLY valid JSON of this exact shape (EXACTLY 2 turns total: Turn 1 by '{lead_speaker}' (20-40 words), Turn 2 by '{co_speaker}' (15-25 words), 35 to 65 words total):
{{
  "summary": "1-2 sentence neutral card summary (30-50 words) built strictly from the facts",
  "turns": [
    {{"speaker": "{lead_speaker}", "purpose": "lead", "fact_refs": ["F1"], "text": "..."}},
    {{"speaker": "{co_speaker}", "purpose": "takeaway", "fact_refs": ["F2"], "text": "..."}}
  ]
}}"""
    return f"""Return ONLY valid JSON of this exact shape (2 to 5 turns total, 35 to 140 words across all turns):
{{
  "summary": "1-2 sentence neutral card summary (30-50 words) built strictly from the facts",
  "turns": [
    {{"speaker": "{lead_speaker}", "purpose": "lead", "fact_refs": ["F1"], "text": "..."}},
    {{"speaker": "{co_speaker}", "purpose": "reaction", "fact_refs": ["F2"], "text": "..."}},
    {{"speaker": "{lead_speaker}", "purpose": "context", "fact_refs": ["F2", "F3"], "text": "..."}},
    {{"speaker": "{co_speaker}", "purpose": "takeaway", "fact_refs": ["F3"], "text": "..."}}
  ]
}}"""


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
    previous_dialogue: StoryDialogue | None = None,
) -> StoryDialogue:
    """Write a grounded two-host conversation for one story using Antigravity -> Groq -> Local -> Gemini -> fallback."""
    brief = build_story_brief(story)
    prev_title = _clean((previous_story or {}).get("title") or (previous_story or {}).get("headline") or "")
    prev_lead = _extract_prev_lead(previous_story, previous_dialogue)
    fmt_key, fmt_desc = select_story_format(
        brief["section"], brief["rank"], sober=brief["sober"], previous_format=previous_format
    )
    cache_path = _dialogue_cache_path(cfg, brief, hosts, fmt_key, prev_title=prev_title, prev_lead=prev_lead)
    if not force and cache_path and cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            brief["prev_lead"] = prev_lead
            turns = validate_story_dialogue(cached.get("turns"), brief, hosts)
            if turns:
                return _story_dialogue_obj(
                    brief, turns, summary=_clean(cached.get("summary") or brief["summary"]),
                    writer=str(cached.get("writer") or "cached"),
                    story_format=str(cached.get("story_format") or fmt_key),
                )
        except Exception:
            pass

    models = llm.ai_provider_chain(cfg, bin_lookup=_resolve_agy_bin)
    if not models:
        return fallback_story_dialogue(story, hosts)

    tag_instruction = (
        "Do NOT use any bracketed voice tags ([laugh], [chuckle], etc.) because this is a sober or serious news section. Express gravity and warmth through thoughtful phrasing and `...` pauses."
        if brief["sober"]
        else (
            "Paralinguistic voice tags ([chuckle], [laugh], [sigh], [gasp]) are strictly OPTIONAL and must be used VERY SPARINGLY. "
            "Most stories (over 80%) should have ZERO tags. "
            "CRITICAL: Do NOT put an emotion tag at the beginning of Turn 2's response to a headline. "
            "Only include at most 1 tag mid-sentence or in the closing turn if genuinely amusing or ironic."
        )
    )
    lead_instruction = select_story_lead(brief, hosts)
    lead_speaker = "a" if lead_instruction.startswith(f"Lead Host: {hosts[0]}") else "b"
    co_speaker = "b" if lead_speaker == "a" else "a"
    angle_lens = _ANGLE_LENS.get(topics.base_section(brief.get("section") or "top"), _ANGLE_LENS["top"])
    shared_terms = _shared_topic_terms(prev_title, brief["headline"]) if prev_title else []

    brief.update(story_format=fmt_key, shared_prev_terms=shared_terms, prev_lead=prev_lead)
    sys_prompt = STORY_DIALOGUE_PROMPT.format(
        a=hosts[0], b=hosts[1], source=brief["source"], tag_instruction=tag_instruction,
        lead_instruction=lead_instruction,
        format_instruction=f"{fmt_desc}\n- Category Angle ({brief['section_title']}): {angle_lens}",
        transition_instruction=_build_transition_instruction(brief, prev_title, prev_lead, shared_terms),
        lead_speaker=lead_speaker, co_speaker=co_speaker,
        shape_instruction=_dialogue_shape_instruction(fmt_key, hosts, lead_speaker, co_speaker),
    )
    user_payload = {
        "section": brief["section_title"], "rank": brief["rank"], "story_format": fmt_key,
        "tone": brief["tone"], "source": brief["source"], "headline": brief["headline"], "facts": brief["facts"],
        **({"previous_story_headline": prev_title[:120]} if prev_title else {}),
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
                try:
                    content = llm.generate_chat_text(
                        client, model=model, url=url, token=token, provider=provider,
                        messages=messages, temperature=0.55 if attempt == 0 else 0.30,
                        max_tokens=1100, cli_timeout=45.0, bin_lookup=_resolve_agy_bin,
                        on_rate_limit=lambda resp: max(llm.retry_after(resp), 3.0),
                    )
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
                                    "Repair the JSON: ensure valid turns adhering to the format. "
                                    "CRITICAL: Turn 1 MUST explicitly name the specific subject entity from the headline "
                                    "instead of vague references like 'the series' or 'the company'. "
                                    "Keep each sentence under 20 words, no dashes or special characters, and valid fact_refs."
                                ),
                            })
                            continue
                        break
                    result = _story_dialogue_obj(
                        brief, turns, summary=_clean(data.get("summary") or brief["summary"]),
                        writer=model, story_format=fmt_key,
                    )
                    _write_dialogue_cache(cache_path, result)
                    return result
                except llm._RetryAfterSignal as sig:
                    if sig.delay <= 35 and attempt == 0:
                        log.warning("%s rate limit hit (429) during story dialogue. Backing off for %.1fs...", provider, sig.delay)
                        sleep(sig.delay)
                        continue
                    break
                except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
                    log.debug("story dialogue %s (%s) attempt %d failed: %s", provider, model, attempt + 1, exc)
                    continue
    finally:
        if own:
            client.close()

    log.warning("All %d LLM provider(s) failed for story dialogue (%s); using grounded fallback.",
                len(models), brief.get("story_id") or "")
    return fallback_story_dialogue(story, hosts)


def _write_dialogue_cache(cache_path: Path | None, result: StoryDialogue) -> None:
    if not cache_path:
        return
    try:
        cache_path.write_text(json.dumps({
            "story_id": result.story_id, "section": result.section, "headline": result.headline,
            "summary": result.summary, "writer": result.writer, "story_format": result.story_format,
            "turns": [{"speaker": "a" if t.speaker == 0 else "b", "purpose": t.purpose,
                       "fact_refs": t.fact_refs, "text": t.text} for t in result.turns],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def format_dialogue_transcript(turns: list[DialogueTurn], hosts: tuple[str, str] = ("Matthew", "Kelly")) -> str:
    """Format two-host turns as speaker-labeled lines for ``story_audio.script`` and the UI teleprompter."""
    lines: list[str] = []
    for t in turns:
        speaker_name = hosts[t.speaker] if 0 <= t.speaker < len(hosts) else hosts[0]
        clean_turn = strip_speaker_prefix(t.text, hosts)
        clean_line = voice_normalize(strip_tags(clean_turn), preserve_tags=False)
        if clean_line:
            lines.append(f"[{speaker_name}] {clean_line}")
    return "\n".join(lines)


def stitch_turn_audio(
    raw_turns: list[tuple[bytes, float, float]],
    sr: int = SAMPLE_RATE,
) -> tuple[bytes, float, list[tuple[float, float]]]:
    """Decode each turn's audio bytes, stitch with PCM silence, and encode once to MP3."""
    decoded = [(audio.decode_audio(raw_bytes, sr=sr, fallback_duration=dur or 1.2), pause_after)
               for raw_bytes, dur, pause_after in raw_turns]
    combined, marks = audio.stitch_turns(decoded, sr=sr)
    return audio.encode_mp3(combined, sr=sr), round(combined.size / sr, 3), marks


async def synthesise_story_dialogue(
    http: httpx.AsyncClient,
    base: str,
    dialogue: StoryDialogue,
    host_voices: tuple[str, str],
    *,
    cache_dir: Path | None = None,
) -> tuple[bytes, float, list[tuple[float, float]]]:
    """Synthesize each turn of a StoryDialogue, cache per-turn WAVs, and stitch via PCM."""
    from . import storypack

    turn_cache: Path | None = None
    if cache_dir:
        turn_cache = Path(cache_dir) / "podcast_turns"
        turn_cache.mkdir(parents=True, exist_ok=True)

    host_names = tuple(v.split("_", 1)[0].strip().capitalize() for v in host_voices[:2] if v and isinstance(v, str))
    hosts_tuple = (host_names[0], host_names[1]) if len(host_names) >= 2 else ("Matthew", "Kelly")

    raw_turns: list[tuple[bytes, float, float]] = []
    for turn in dialogue.turns:
        voice_id = host_voices[turn.speaker]
        spoken_text = strip_speaker_prefix(turn.text, hosts_tuple) or _clean(turn.text)
        word_count = len(strip_tags(spoken_text).split())

        turn_pace, turn_temp = (0.93, 0.82) if turn.speaker == 0 else (0.97, 0.88)
        if turn.purpose == "reaction" and word_count <= 4:
            turn_pace, turn_temp = 0.98, 0.90

        key = hashlib.sha256(f"wav|{voice_id}|{turn_pace:.2f}|{turn_temp:.2f}|{spoken_text}".encode("utf-8")).hexdigest()[:16]
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

        raw_audio, seconds = await storypack.synthesise(
            http, base, spoken_text, voice_id, pace=turn_pace, temperature=turn_temp, fmt="wav",
        )
        if cached_wav and cached_meta:
            try:
                cached_wav.write_bytes(raw_audio)
                cached_meta.write_text(json.dumps({
                    "duration": seconds, "voice": voice_id, "pace": turn_pace, "temp": turn_temp,
                }), encoding="utf-8")
            except Exception:
                pass
        raw_turns.append((raw_audio, seconds, turn.pause_after))

    return await asyncio.to_thread(stitch_turn_audio, raw_turns)
