#!/usr/bin/env python3
"""Regenerate dialogue and audio for specific stories in Hark Daily.

Allows on-demand, granular updates to individual stories or topic groups (e.g. Nvidia,
broken transcripts, cut-offs) without needing to re-run the entire 35-minute daily pack.

Usage:
    # Regenerate a single story by section and rank
    python scripts/regen_story.py --section top --rank 1

    # Regenerate all stories containing a specific search phrase
    python scripts/regen_story.py --query "drug possession"
    python scripts/regen_story.py --all-nvidia

    # Dry run to preview matched stories
    python scripts/regen_story.py --all-nvidia --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load
from app.fetcher import extract_article
from app import podcast, topics
from app.storypack import (
    _publish_audio_file,
    voice_name,
)
from app.store import Store

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
log = logging.getLogger("regen_story")


def ensure_voice_service(url: str, auto_start: bool = True) -> tuple[subprocess.Popen | None, str]:
    """Check if voice service is running; if not and auto_start is True, spawn it locally."""
    clean_url = url.rstrip("/")
    try:
        r = httpx.get(f"{clean_url}/health", timeout=2.0)
        if r.status_code == 200:
            log.info("✓ Connected to active voice service at %s", clean_url)
            return None, clean_url
    except Exception:
        pass

    if not auto_start:
        raise RuntimeError(f"Voice service is not running at {clean_url}. Start it or pass --auto-start.")

    log.info("Starting local Chatterbox-Turbo voice service on Apple Silicon MPS...")
    svc_dir = ROOT / "voice_service"
    log_file = ROOT / "logs" / "voice_service_regen.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fp = log_file.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(svc_dir / ".venv" / "bin" / "uvicorn"), "api.app:app", "--host", "127.0.0.1", "--port", "8090"],
        cwd=str(svc_dir),
        stdout=fp,
        stderr=fp,
    )
    for _ in range(60):
        time.sleep(1)
        try:
            r = httpx.get("http://127.0.0.1:8090/health", timeout=1.0)
            if r.status_code == 200:
                log.info("✓ Local voice service is online at http://127.0.0.1:8090")
                return proc, "http://127.0.0.1:8090"
        except Exception:
            pass

    proc.terminate()
    raise RuntimeError("Timed out waiting for local voice service to start.")


def clean_existing_script(text: str) -> str:
    """Extract clean, complete sentences from existing script, filtering truncated fragments."""
    if not text:
        return ""
    import re
    # Split by speaker tags first: e.g. [Matthew] ..., [Kelly] ...
    parts = re.split(r"\[(?:Matthew|Kelly|Host|Speaker\s*\d+)\]\s*", text, flags=re.I)
    cleaned_sentences: list[str] = []
    seen = set()
    for p in parts:
        chunk = " ".join(p.split()).strip()
        if not chunk:
            continue
        for s in podcast._split_sentences(chunk):
            s = podcast.strip_repetition_stutter(" ".join(s.split()).strip())
            if not s or len(s.split()) < 4:
                continue
            # Filter out boilerplate placeholders so they don't get recycled as news facts
            if any(ph in s.lower() for ph in [
                "full details on that story",
                "reporting there from",
                "reporting from",
                "key developments we are tracking",
                "leading our coverage today",
            ]):
                continue
            # Ensure sentence ends in terminal punctuation
            if not s.endswith((".", "!", "?", '"', "”")):
                continue
            norm = s.lower().rstrip(".")
            if norm not in seen:
                seen.add(norm)
                cleaned_sentences.append(s)
    return " ".join(cleaned_sentences)


async def regenerate_story(
    cfg,
    store: Store,
    story_row: dict,
    voice_url: str,
    voice: str = "matthew_reference+kelly_reference",
    force: bool = True,
) -> dict:
    """Re-extract, re-script, and re-voice a single story row, updating Supabase."""
    day = story_row["date"]
    section = story_row["section"]
    rank = int(story_row["rank"])
    title = story_row.get("title", "")
    url = story_row.get("url", "")
    duo_names = ("Matthew", "Kelly")

    log.info("→ Processing [%s #%d] %s", section, rank, title[:60])

    # 1. Fetch fresh article content if URL exists to ensure high-fidelity body sentences
    article_text = ""
    summary = story_row.get("summary") or ""
    if url:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as http:
                resp = await http.get(url)
                if resp.status_code == 200:
                    art = extract_article(resp.text, url)
                    article_text = art.get("text", "")
                    if not summary:
                        summary = art.get("summary", "")
        except Exception as exc:
            log.warning("Could not refresh article text for %s: %s", url, exc)

    raw_script = clean_existing_script(story_row.get("script", ""))
    story_dict = {
        "id": story_row.get("id"),
        "section": section,
        "rank": rank,
        "title": title,
        "headline": title,
        "source": story_row.get("source") or "News wire",
        "url": url,
        "summary": summary or raw_script,
        "article_text": article_text or raw_script,
    }

    # 2. Invalidate old dialogue cache files for this story
    brief = podcast.build_story_brief(story_dict)
    fmt_key, _ = podcast.select_story_format(section, rank, sober=brief["sober"])
    cache_path = podcast._dialogue_cache_path(cfg, brief, duo_names, fmt_key)
    if cache_path and cache_path.exists():
        cache_path.unlink()
        log.info("  Cleaned cached dialogue at %s", cache_path.name)

    # 3. Generate brand new dialogue with strict anti-slop, clean pronunciation, and no headline repetition
    dialogue = await asyncio.to_thread(
        podcast.generate_story_dialogue,
        cfg,
        story_dict,
        duo_names,
        force=True,
    )
    log.info("  Writer: %s · Format: %s · %d turns", dialogue.writer, dialogue.story_format, len(dialogue.turns))
    for i, t in enumerate(dialogue.turns, 1):
        spk = duo_names[t.speaker] if t.speaker in (0, 1) else f"Speaker {t.speaker}"
        log.info("    Turn %d [%s]: %s", i, spk, t.text)

    # 4. Synthesize WAV audio + exact turn marks on the voice service
    parts = [p.strip() for p in voice.split("+") if p.strip()]
    duo_voices = (parts[0], parts[1]) if len(parts) >= 2 else (parts[0], parts[0])
    async with httpx.AsyncClient(timeout=900) as client:
        audio, duration, marks = await podcast.synthesise_story_dialogue(
            client, voice_url, dialogue, duo_voices, cache_dir=getattr(cfg, "cache_dir", None)
        )

    # 5. Build storage audio path with content hash
    content_hash = hashlib.sha256(audio).hexdigest()[:8]
    voice_slug = voice.replace("+", "__")
    path = f"stories/{day}/{section}-{rank}-{voice_slug}-{content_hash}.mp3"
    spoken_script = podcast.format_dialogue_transcript(dialogue.turns, duo_names)
    marks_payload = [{"start": round(m[0], 3), "end": round(m[1], 3)} for m in marks]

    # 6. Upload new audio file to Supabase Storage
    log.info("  Uploading %.1fs audio to %s...", duration, path)
    await asyncio.to_thread(_publish_audio_file, store, path, audio)

    # 7. Upsert updated row in Supabase story_audio
    updated_row = {
        "date": day,
        "section": section,
        "rank": rank,
        "voice": voice,
        "title": title[:500],
        "url": url,
        "source": story_row.get("source", "")[:200],
        "image": story_row.get("image"),
        "script": spoken_script,
        "duration": round(duration, 3),
        "audio_path": path,
        "marks": marks_payload,
    }
    try:
        store.insert("story_audio", updated_row, on_conflict="date,section,rank,voice")
    except Exception as exc:
        if "marks" in str(exc).lower():
            fallback_row = {k: v for k, v in updated_row.items() if k != "marks"}
            store.insert("story_audio", fallback_row, on_conflict="date,section,rank,voice")
        else:
            raise

    log.info("✓ Updated [%s #%d] successfully in Supabase!", section, rank)
    return updated_row


def main() -> int:
    parser = argparse.ArgumentParser(description="Hark Daily — Dynamic Story Regenerator")
    parser.add_argument("--date", help="Target date YYYY-MM-DD (defaults to today)")
    parser.add_argument("--section", help="Section key (e.g. top, markets, ai, tech_us)")
    parser.add_argument("--rank", type=int, help="Story rank (1-5)")
    parser.add_argument("--query", help="Case-insensitive search query in title or script")
    parser.add_argument("--all-nvidia", action="store_true", help="Regenerate all stories mentioning Nvidia")
    parser.add_argument("--voice", default="matthew_reference+kelly_reference", help="Narrator voice id")
    parser.add_argument("--voice-url", help="Voice service URL (defaults to VOICE_SERVICE_URL or 127.0.0.1:8090)")
    parser.add_argument("--dry-run", action="store_true", help="Find and display matching stories without regenerating")
    parser.add_argument("--auto-start", action="store_true", default=True, help="Auto-start local voice service if offline")
    args = parser.parse_args()

    cfg = load()
    store = Store(cfg.supabase_url, cfg.supabase_secret_key, cfg.bucket)
    day = args.date or datetime.now(ZoneInfo(cfg.timezone)).date().isoformat()
    voice = args.voice

    # Find existing stories in Supabase
    log.info("Querying Supabase story_audio for %s (voice: %s)...", day, voice)
    query_params = {"date": f"eq.{day}", "voice": f"eq.{voice}"}
    if args.section:
        query_params["section"] = f"eq.{args.section}"
    if args.rank:
        query_params["rank"] = f"eq.{args.rank}"

    rows = store.select("story_audio", query_params)
    if not rows:
        log.warning("No stories found for date %s matching query parameters.", day)
        return 1

    # Filter by query if requested
    matched: list[dict] = []
    search_term = "nvidia" if args.all_nvidia else (args.query or "").lower().strip()
    for r in sorted(rows, key=lambda x: (x.get("section", ""), int(x.get("rank", 0)))):
        text_corpus = f"{r.get('title', '')} {r.get('script', '')}".lower()
        if not search_term or search_term in text_corpus:
            matched.append(r)

    log.info("Found %d matching story(ies) to regenerate for %s:", len(matched), day)
    for r in matched:
        print(f"  • [{r.get('section')} #{r.get('rank')}] {r.get('title')} ({r.get('duration')}s)")

    if args.dry_run:
        log.info("Dry run complete. Exiting without modifying database or audio.")
        return 0

    if not matched:
        log.info("Nothing to regenerate.")
        return 0

    # Ensure voice service is up
    url = args.voice_url or cfg.voice_url or "http://127.0.0.1:8090"
    proc, active_url = ensure_voice_service(url, auto_start=args.auto_start)

    try:
        for i, r in enumerate(matched):
            if i > 0:
                time.sleep(2.0)
            asyncio.run(regenerate_story(cfg, store, r, voice_url=active_url, voice=voice, force=True))
    finally:
        if proc:
            log.info("Stopping temporary local voice service (PID: %d)...", proc.pid)
            proc.terminate()
            proc.wait(timeout=10)
            log.info("Voice service stopped.")

    log.info("🎉 All %d stories regenerated and published successfully!", len(matched))
    return 0


if __name__ == "__main__":
    sys.exit(main())
