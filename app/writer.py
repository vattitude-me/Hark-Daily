"""Turn ranked stories into card copy and a spoken briefing script.

Story copy (headline, card summary, spoken lines) is written once per story and
shared by every user whose briefing includes it. Groq writes it when a key is
set, falling through GROQ_MODELS as each one hits its free-tier limit; the
extractive template writer is the last resort, so a briefing always ships.
The intro, section transitions and sign-off are templates, personalised per user.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

from .ranking import Story
from .report import RunReport
from .sources import SECTIONS
from .summarizer import summarize

log = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_WAIT = 65          # longest per-minute back-off we'll sit through, in seconds
MAX_ARTICLE_CHARS = 2500


@dataclass
class StoryCopy:
    headline: str
    summary: str
    spoken: str
    writer: str = "built-in"


@dataclass
class Script:
    intro: str
    section_leads: dict[str, str]
    stories: dict[str, StoryCopy]
    outro: str
    writer: str = "built-in"
    notes: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ template
CONNECTORS = ["", "Next,", "Meanwhile,", "Also today,", "In other news,", "Elsewhere,", "And"]


def _source_phrase(story: Story) -> str:
    names = story.sources
    if len(names) >= 3:
        return f"{names[0]}, {names[1]} and others"
    return " and ".join(names)


def template_copy(story: Story) -> StoryCopy:
    lead = story.lead
    summary = summarize(lead.text, fallback=lead.summary, max_words=60, title=lead.title) or lead.summary or lead.title
    spoken_body = summarize(lead.text, fallback=lead.summary, max_words=55, max_sentences=2, title=lead.title)
    if spoken_body.endswith("…"):
        # Never stop mid-sentence out loud: drop the clipped tail.
        head, dot, _ = spoken_body.rpartition(". ")
        spoken_body = head + dot.strip() if dot else ""
    # The connector depends on the story, not its position, so the same story sounds the same
    # in everyone's briefing and its audio can be shared.
    connector = CONNECTORS[int(story.id, 16) % len(CONNECTORS)]
    title = lead.title.rstrip(".")
    opener = f"{connector} from {_source_phrase(story)}: {title}." if connector else f"From {_source_phrase(story)}: {title}."
    spoken = f"{opener} {spoken_body}".strip()
    return StoryCopy(headline=lead.title, summary=summary, spoken=spoken, writer="built-in")


def compose(picked: dict[str, list[Story]], copies: dict[str, StoryCopy], when: datetime,
            weather: str | None, name: str | None = None) -> Script:
    """Wrap shared story copy in a personal intro, section transitions and sign-off."""
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
    hello = f"Good morning, {name}!" if name else "Good morning!"
    intro = f"{hello} It's {date}. {weather + ' ' if weather else ''}Here's your briefing: {rundown}."
    stories = {s.id: copies[s.id] for group in picked.values() for s in group}
    used = {c.writer for c in stories.values()}
    writer = "built-in" if used == {"built-in"} else ("groq" if "built-in" not in used else "mixed")
    return Script(
        intro=intro,
        section_leads={k: SECTIONS[k]["lead"] for k in picked},
        stories=stories,
        outro=f"That's your briefing for this {when:%A}. Have a wonderful day, and I'll talk to you tomorrow morning.",
        writer=writer,
    )


# ---------------------------------------------------------------------- Groq
SYSTEM_PROMPT = """You write copy for a warm, trustworthy morning audio news briefing for listeners in Canada.
The spoken text is read aloud by a text-to-speech voice; the summary appears on a news card.

Return a JSON object with exactly these keys:
- "headline": a clear, neutral headline of at most 12 words.
- "summary": the card text, 40 to 60 words of plain factual prose built only from the supplied text.
- "spoken": what the host says, 2 to 4 sentences and 45 to 85 words, conversational like a good radio host.
  Name the outlet from "outlets" naturally once, using its exact name (for example "<outlet> reports...");
  never name any other outlet. Start with the news itself, not a greeting.

Write for the ear: no URLs, emoji, bullet points, brackets or markdown; spell out symbols
("percent", "billion dollars"); keep sentences short. Stay strictly factual and neutral.
Never add facts that aren't in the text; if the text is thin, say less."""


class LimitHit(Exception):
    """This model can't be used again in this run."""


class AuthFailed(Exception):
    """The API key was rejected: no Groq model will work in this run."""


def _retry_after(resp: httpx.Response) -> float:
    try:
        return float(resp.headers.get("retry-after", ""))
    except ValueError:
        pass
    # Groq also says "Please try again in 7.66s" / "in 2m59.5s" in the message.
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", resp.text)
    if m:
        h, mins, s = (float(x) if x else 0.0 for x in m.groups())
        return h * 3600 + mins * 60 + s
    return 10.0


def _is_daily(resp: httpx.Response) -> bool:
    text = resp.text.lower()
    return "per day" in text or "(tpd)" in text or "(rpd)" in text or "daily" in text


class StoryWriter:
    """Writes copy for each story once, caches it on disk, and records every limit it runs into."""

    def __init__(self, cache_dir: Path, report: RunReport, *, api_key: str | None, models: tuple[str, ...],
                 client: httpx.Client | None = None, sleep=time.sleep):
        self.cache_dir = cache_dir / "copy"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.report = report
        self.api_key = api_key
        self.models = list(models) if api_key else []
        self.client = client or httpx.Client(timeout=60)
        self.sleep = sleep
        self.failures = 0
        if not api_key:
            report.add("ai_off", "GROQ_API_KEY is not set", level="info")

    # ---------------------------------------------------------------- public
    def copy(self, section: str, story: Story) -> StoryCopy:
        path = self.cache_dir / f"{story.id}.json"
        if path.exists():
            try:
                cached = StoryCopy(**json.loads(path.read_text()))
                self.report.writers[cached.writer] += 1
                return cached
            except (ValueError, TypeError):
                pass
        result = self._ai(section, story) or template_copy(story)
        self.report.writers[result.writer] += 1
        if result.writer != "built-in":  # retry the AI next run rather than caching the fallback
            path.write_text(json.dumps(result.__dict__, ensure_ascii=False))
        return result

    # --------------------------------------------------------------- private
    def _ai(self, section: str, story: Story) -> StoryCopy | None:
        while self.models:
            model = self.models[0]
            try:
                return self._call(model, section, story)
            except LimitHit as exc:
                log.warning("Groq %s unavailable for the rest of this run: %s", model, exc)
                self.models.pop(0)
            except AuthFailed as exc:
                self.report.add("ai_auth", str(exc), level="error")
                self.models.clear()
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                # One bad story (timeout, malformed JSON): fall back for this story only,
                # but give up on the service after repeated failures.
                self.failures += 1
                log.warning("Groq failed on %s: %s", story.id, exc)
                if self.failures >= 3:
                    self.report.add("ai_unavailable", f"{exc.__class__.__name__}: {exc}"[:200])
                    self.models.clear()
                return None
        return None

    def _call(self, model: str, section: str, story: Story) -> StoryCopy:
        lead = story.lead
        payload = {
            "section": SECTIONS[section]["title"],
            "headline": lead.title,
            "outlets": story.sources,
            "text": (lead.text or lead.summary or lead.title)[:MAX_ARTICLE_CHARS],
        }
        body = {
            "model": model,
            "temperature": 0.4,
            "max_tokens": 1200,
            "response_format": {"type": "json_object"},
            **({"reasoning_effort": "low"} if model.startswith("openai/gpt-oss") else {}),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        }
        for attempt in range(4):
            resp = self.client.post(GROQ_URL, json=body, headers={"Authorization": f"Bearer {self.api_key}"})
            if resp.status_code in (401, 403):
                raise AuthFailed(f"Groq returned {resp.status_code}: {resp.text[:150]}")
            if resp.status_code == 429:
                wait = _retry_after(resp)
                if _is_daily(resp) or wait > MAX_WAIT:
                    self.report.add("ai_daily_limit", f"{model}: {resp.text[:200]}")
                    raise LimitHit(f"daily limit ({wait:.0f}s wait)")
                self.report.add("ai_rate_limited", f"{model}: waited {wait:.0f}s", level="info")
                self.sleep(wait + 0.5)
                continue
            if resp.status_code in (404, 400) and "model" in resp.text.lower():
                self.report.add("ai_model_gone", f"{model}: {resp.text[:150]}")
                raise LimitHit(f"model not available: {resp.text[:150]}")
            if resp.status_code >= 500:
                if attempt < 2:
                    self.sleep(2 * (attempt + 1))
                    continue
                resp.raise_for_status()
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            headline, summary, spoken = (str(data.get(k, "")).strip() for k in ("headline", "summary", "spoken"))
            if not (summary and spoken):
                raise ValueError("empty summary or spoken text")
            self.failures = 0
            return StoryCopy(headline=headline or lead.title, summary=summary, spoken=spoken, writer=model)
        self.report.add("ai_daily_limit", f"{model}: still rate limited after retries")
        raise LimitHit("still rate limited after retries")


def copy_key(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]
