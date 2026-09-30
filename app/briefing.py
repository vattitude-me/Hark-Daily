"""The daily pipeline: fetch → rank → read → write → record."""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from . import audio, tts, weather
from .config import Config
from .db import Database, now_iso
from .fetcher import enrich_items, fetch_all
from .ranking import select_top
from .sources import SECTIONS
from .writer import write_script

log = logging.getLogger(__name__)

Progress = Callable[[str, float], None]


class BriefingError(Exception):
    pass


def _noop(step: str, fraction: float) -> None:  # pragma: no cover - default progress sink
    log.info("[%3d%%] %s", int(fraction * 100), step)


def build_briefing(cfg: Config, db: Database, progress: Progress = _noop) -> dict:
    settings = db.get_settings()
    tz = ZoneInfo(cfg.timezone)
    now_local = datetime.now(tz)
    started = time.monotonic()

    # 1. Gather ------------------------------------------------------------
    progress("Gathering today's headlines", 0.03)
    sources = db.active_sources()
    if not sources:
        raise BriefingError("No sources are switched on. Enable at least one in Sources.")
    items, statuses = asyncio.run(fetch_all(sources))
    stamp = now_iso()
    counts: dict[int, int] = {}
    for it in items:
        counts[it.source_id] = counts.get(it.source_id, 0) + 1
    for sid, status in statuses.items():
        db.update_source(sid, last_fetched_at=stamp, last_status=status, last_count=counts.get(sid, 0))
    if not items:
        raise BriefingError("Couldn't reach any news sources. Check your internet connection and try again.")

    # 2. Rank --------------------------------------------------------------
    progress("Picking the top stories", 0.15)
    limits = {k: int(settings["stories"].get(k, 0)) for k in SECTIONS}
    picked = select_top(items, limits)
    if not picked:
        raise BriefingError("No fresh stories found in the last two days.")

    # 3. Read full articles --------------------------------------------------
    progress("Reading the full articles", 0.22)
    leads = [s.lead for stories in picked.values() for s in stories]
    asyncio.run(enrich_items(leads))

    wx = None
    if settings.get("weather"):
        wx = weather.forecast(settings["latitude"], settings["longitude"], settings["city"], cfg.timezone)

    # 4. Write -------------------------------------------------------------
    progress("Writing your briefing" + (" with Claude" if cfg.anthropic_api_key else ""), 0.35)
    script = write_script(
        picked, now_local, weather.spoken(wx),
        api_key=cfg.anthropic_api_key, model=cfg.claude_model, city=settings["city"],
    )

    # 5. Record ------------------------------------------------------------
    voice_id = settings["voice"]
    speed = float(settings["speed"])
    try:
        tts.resolve(voice_id)
    except ValueError:
        voice_id = tts.default_voice()

    segments: list[tuple[str, str, float]] = [("intro", script.intro, 0.9)]
    for section, stories in picked.items():
        segments.append((f"section:{section}", script.section_leads[section], 0.6))
        for i, story in enumerate(stories):
            last = i == len(stories) - 1
            segments.append((story.id, script.stories[story.id].spoken, 1.2 if last else 0.8))
    segments.append(("outro", script.outro, 0.8))

    rendered = []
    for n, (key, text, pause) in enumerate(segments):
        progress("Recording the audio", 0.45 + 0.5 * n / len(segments))
        rendered.append((key, tts.synthesize(voice_id, text, speed), pause))
    pcm, marks = audio.assemble(rendered)
    mp3 = audio.encode_mp3(pcm)

    # 6. Save --------------------------------------------------------------
    progress("Saving", 0.97)
    day = now_local.date().isoformat()
    out_dir = cfg.briefings_dir / day
    out_dir.mkdir(parents=True, exist_ok=True)
    version = int(time.time())
    tmp = out_dir / "briefing.mp3.tmp"
    tmp.write_bytes(mp3)
    tmp.replace(out_dir / "briefing.mp3")

    chapters = [{"id": "intro", "kind": "intro", "title": "Good morning", "start": 0.0, "end": marks["intro"][1],
                 "text": script.intro}]
    cards = []
    for section, stories in picked.items():
        s_start = marks[f"section:{section}"][0]
        chapters.append({"id": f"section:{section}", "kind": "section", "section": section,
                         "title": SECTIONS[section]["title"], "start": s_start, "end": s_start,
                         "text": script.section_leads[section]})
        for story in stories:
            copy = script.stories[story.id]
            start, end = marks[story.id]
            chapters.append({"id": story.id, "kind": "story", "section": section,
                             "title": copy.headline, "start": start, "end": end, "text": copy.spoken})
            lead = story.lead
            cards.append({
                "id": story.id,
                "section": section,
                "headline": copy.headline,
                "original_title": lead.title,
                "summary": copy.summary,
                "url": lead.url,
                "source": lead.source_name,
                "also": [s for s in story.sources if s != lead.source_name],
                "links": [{"source": i.source_name, "url": i.url} for i in story.items[:5]],
                "image": lead.image if lead.image and lead.image.startswith(("http://", "https://")) else None,
                "published": lead.published.isoformat() if lead.published else None,
                "start": start,
                "end": end,
            })
    chapters.append({"id": "outro", "kind": "outro", "title": "Sign-off", "start": marks["outro"][0],
                     "end": marks["outro"][1], "text": script.outro})

    voice_meta = next((v for v in tts.all_voices() if v["id"] == voice_id), {"id": voice_id, "name": voice_id})
    briefing = {
        "date": day,
        "title": f"{now_local:%A}, {now_local:%B} {now_local.day}",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration": round(pcm.size / tts.SAMPLE_RATE, 2),
        "audio_url": f"/media/{day}/briefing.mp3?v={version}",
        "voice": {"id": voice_id, "name": voice_meta.get("name"), "accent": voice_meta.get("accent")},
        "writer": script.writer,
        "notes": script.notes,
        "weather": wx,
        "intro": script.intro,
        "sections": [{"key": k, "title": SECTIONS[k]["title"], "emoji": SECTIONS[k]["emoji"], "count": len(v)}
                     for k, v in picked.items()],
        "chapters": chapters,
        "stories": cards,
        "build_seconds": round(time.monotonic() - started, 1),
    }
    (out_dir / "briefing.json").write_text(json.dumps(briefing, ensure_ascii=False, indent=1))

    for src in sources:
        if src["kind"] == "article" and statuses.get(src["id"]) == "ok":
            db.mark_consumed(src["id"])
    prune(cfg.briefings_dir, cfg.keep_days, now_local.date())
    progress("Done", 1.0)
    return briefing


def prune(root: Path, keep_days: int, today: date) -> None:
    cutoff = today - timedelta(days=keep_days)
    for child in root.iterdir():
        try:
            if date.fromisoformat(child.name) < cutoff:
                shutil.rmtree(child)
        except ValueError:
            continue


def list_briefings(cfg: Config) -> list[dict]:
    out = []
    for child in sorted(cfg.briefings_dir.iterdir(), reverse=True):
        meta = child / "briefing.json"
        if meta.exists():
            try:
                data = json.loads(meta.read_text())
            except json.JSONDecodeError:
                continue
            out.append({"date": data["date"], "title": data["title"], "duration": data["duration"],
                        "stories": len(data["stories"])})
    return out


def load_briefing(cfg: Config, day: str | None = None) -> dict | None:
    if day is None:
        items = list_briefings(cfg)
        if not items:
            return None
        day = items[0]["date"]
    try:
        date.fromisoformat(day)
    except ValueError:
        return None
    meta = cfg.briefings_dir / day / "briefing.json"
    return json.loads(meta.read_text()) if meta.exists() else None
