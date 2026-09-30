"""Turn ranked stories into card copy and a spoken briefing script.

With ANTHROPIC_API_KEY set, Claude writes the script in a natural radio
style. Without it (or if the call fails) a template writer built on the
extractive summarizer takes over, so the briefing always ships.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel

from .ranking import Story
from .sources import SECTIONS
from .summarizer import summarize

log = logging.getLogger(__name__)


@dataclass
class StoryCopy:
    headline: str
    summary: str
    spoken: str


@dataclass
class Script:
    intro: str
    section_leads: dict[str, str]
    stories: dict[str, StoryCopy]
    outro: str
    writer: str = "template"
    notes: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ template
CONNECTORS = ["", "Next,", "Meanwhile,", "Also today,", "In other news,", "Elsewhere,", "And"]


def _source_phrase(story: Story) -> str:
    names = story.sources
    if len(names) >= 3:
        return f"{names[0]}, {names[1]} and others"
    return " and ".join(names)


def template_copy(story: Story, index: int) -> StoryCopy:
    lead = story.lead
    summary = summarize(lead.text, fallback=lead.summary, max_words=60, title=lead.title) or lead.summary or lead.title
    spoken_body = summarize(lead.text, fallback=lead.summary, max_words=55, max_sentences=2, title=lead.title)
    if spoken_body.endswith("…"):
        # Never stop mid-sentence out loud: drop the clipped tail.
        head, dot, _ = spoken_body.rpartition(". ")
        spoken_body = head + dot.strip() if dot else ""
    connector = CONNECTORS[index % len(CONNECTORS)]
    title = lead.title.rstrip(".")
    opener = f"{connector} from {_source_phrase(story)}: {title}." if connector else f"From {_source_phrase(story)}: {title}."
    spoken = f"{opener} {spoken_body}".strip()
    return StoryCopy(headline=lead.title, summary=summary, spoken=spoken)


def template_script(picked: dict[str, list[Story]], when: datetime, weather: str | None) -> Script:
    counts = {k: len(v) for k, v in picked.items()}
    parts = []
    if counts.get("canada"):
        parts.append(f"{counts['canada']} stories from across Canada")
    if counts.get("tech"):
        parts.append(f"{counts['tech']} in AI and tech")
    if counts.get("custom"):
        parts.append(f"{counts['custom']} from your own sources")
    rundown = ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1] if parts else "your news"
    date = f"{when:%A}, {when:%B} {when.day}"
    intro = f"Good morning! It's {date}. {weather + ' ' if weather else ''}Here's your briefing: {rundown}."

    stories: dict[str, StoryCopy] = {}
    for section_stories in picked.values():
        for i, story in enumerate(section_stories):
            stories[story.id] = template_copy(story, i)
    return Script(
        intro=intro,
        section_leads={k: SECTIONS[k]["lead"] for k in picked},
        stories=stories,
        outro=f"That's your briefing for this {when:%A}. Have a wonderful day, and I'll talk to you tomorrow morning.",
    )


# -------------------------------------------------------------------- Claude
class StoryDraft(BaseModel):
    id: str
    headline: str
    summary: str
    spoken: str


class SectionLeadDraft(BaseModel):
    section: str
    line: str


class ScriptDraft(BaseModel):
    intro: str
    section_leads: list[SectionLeadDraft]
    stories: list[StoryDraft]
    outro: str


SYSTEM_PROMPT = """You write and host a warm, trustworthy morning audio news briefing for a listener in {city}, Canada.
The script is read aloud by a neural text-to-speech voice, and the summaries appear on news cards in an app.

For each story you're given (id, section, headline, outlets, article text):
- headline: a clear, neutral headline of at most 12 words.
- summary: the card text, 40 to 60 words, plain factual prose built only from the supplied text.
- spoken: what the host says, 2 to 4 sentences and 45 to 85 words, conversational like a good radio host.
  Mention the outlet naturally once ("CBC reports…"). Vary how stories open so it never sounds repetitive.

Write for the ear: no URLs, emoji, bullet points, brackets or markdown; spell out symbols and awkward abbreviations
(say "percent", "billion dollars"); keep sentences short enough to read in one breath.
Stay strictly factual and neutral. Never add facts that aren't in the text; if the text is thin, say less.

Also write:
- intro: a friendly greeting of at most 45 words with the weekday and date, the weather line if one is given, and a
  one-sentence preview of the biggest story.
- section_leads: one short spoken transition (at most 15 words) per section present, in the order given.
- outro: a brief warm sign-off of at most 25 words.
Return every story id exactly once."""


def _story_payload(section: str, story: Story) -> dict:
    lead = story.lead
    text = (lead.text or lead.summary or "")[:3000]
    return {
        "id": story.id,
        "section": SECTIONS[section]["title"],
        "headline": lead.title,
        "outlets": story.sources,
        "published": lead.published.isoformat() if lead.published else None,
        "text": text,
    }


def claude_script(
    picked: dict[str, list[Story]], when: datetime, weather: str | None, *, api_key: str, model: str, city: str
) -> Script | None:
    try:
        import anthropic
    except ImportError:
        return None

    payload = {
        "date": f"{when:%A}, {when:%B} {when.day}, {when:%Y}",
        "weather": weather,
        "sections": [SECTIONS[k]["title"] for k in picked],
        "stories": [_story_payload(sec, s) for sec, stories in picked.items() for s in stories],
    }
    client = anthropic.Anthropic(api_key=api_key, timeout=300, max_retries=2)
    try:
        response = client.messages.parse(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT.format(city=city),
            output_config={"effort": "medium"},
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            output_format=ScriptDraft,
        )
    except anthropic.AuthenticationError:
        log.error("ANTHROPIC_API_KEY was rejected; using the built-in writer")
        return None
    except anthropic.APIError as exc:
        log.warning("Claude request failed (%s); using the built-in writer", exc)
        return None

    if response.stop_reason in ("refusal", "max_tokens") or response.parsed_output is None:
        log.warning("Claude stopped with %s; using the built-in writer", response.stop_reason)
        return None

    draft: ScriptDraft = response.parsed_output
    fallback = template_script(picked, when, weather)
    by_id = {s.id: s for s in draft.stories}
    stories: dict[str, StoryCopy] = {}
    missing = []
    for sid, copy in fallback.stories.items():
        d = by_id.get(sid)
        if d and d.summary.strip() and d.spoken.strip():
            stories[sid] = StoryCopy(headline=d.headline.strip(), summary=d.summary.strip(), spoken=d.spoken.strip())
        else:
            stories[sid] = copy
            missing.append(sid)

    titles = {SECTIONS[k]["title"].lower(): k for k in picked}
    leads = dict(fallback.section_leads)
    for lead in draft.section_leads:
        key = titles.get(lead.section.strip().lower()) or (lead.section if lead.section in picked else None)
        if key and lead.line.strip():
            leads[key] = lead.line.strip()

    return Script(
        intro=draft.intro.strip() or fallback.intro,
        section_leads=leads,
        stories=stories,
        outro=draft.outro.strip() or fallback.outro,
        writer="claude",
        notes=[f"{len(missing)} stories used the built-in writer"] if missing else [],
    )


def write_script(
    picked: dict[str, list[Story]], when: datetime, weather: str | None, *, api_key: str | None, model: str, city: str
) -> Script:
    if api_key:
        script = claude_script(picked, when, weather, api_key=api_key, model=model, city=city)
        if script:
            return script
    return template_script(picked, when, weather)
