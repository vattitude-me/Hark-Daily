#!/usr/bin/env python3
"""Non-prod demo CLI for trending quirky news banter.

Runs completely isolated from production (zero Supabase writes, zero bucket uploads).
Curates trending quirky topics without social media brand mentions, generates dual-host
banter between Matthew & Kelly, and outputs review decks, interactive HTML players,
and synthesized demo audio.

Usage:
    python scripts/demo_trending_banter.py --list
    python scripts/demo_trending_banter.py --review
    python scripts/demo_trending_banter.py --schedule morning
    python scripts/demo_trending_banter.py --schedule evening
    python scripts/demo_trending_banter.py --topic desk-bombing
    python scripts/demo_trending_banter.py --synthesise
    python scripts/demo_trending_banter.py --html
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import audio, podcast, trending  # noqa: E402
from app.storypack import synthesise  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("trending_demo")

def resolve_output_dir() -> Path:
    """Finds a writable output directory for demo assets."""
    custom = os.environ.get("DEMO_OUTPUT_DIR")
    if custom:
        p = Path(custom)
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Preferred location: brain artifact directory if active
    artifact_dir = Path("/Users/vattitude/.gemini/antigravity-cli/brain/76b36c9f-d81c-4712-8b3d-6a75a270ab77/trending_banter")
    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return artifact_dir
    except Exception:
        pass

    fallback = Path("/tmp/trending_banter")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


OUTPUT_DIR = resolve_output_dir()


def generate_html_player(deck: trending.DailyReviewDeck, audio_files: dict[str, str] | None = None) -> Path:
    """Generates a standalone, beautiful HTML preview player for testing."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = OUTPUT_DIR / "preview.html"
    audio_files = audio_files or {}

    m_audio = audio_files.get("morning", "")
    e_audio = audio_files.get("evening", "")

    def render_turns_html(turns, host_a="Matthew", host_b="Kelly"):
        items = []
        for who, text in turns:
            speaker = host_a if who == 0 else host_b
            badge_class = "speaker-matthew" if who == 0 else "speaker-kelly"
            # Highlight paralinguistic voice tags
            tagged_text = text
            for tag in ("laugh", "chuckle", "sigh", "gasp"):
                tagged_text = tagged_text.replace(f"[{tag}]", f'<span class="voice-tag">[{tag}]</span>')
            items.append(f"""
                <div class="turn-row {badge_class}">
                    <span class="speaker-pill">{speaker}</span>
                    <span class="speaker-text">{tagged_text}</span>
                </div>
            """)
        return "\n".join(items)

    m_turns_html = render_turns_html(deck.morning_turns, deck.hosts[0], deck.hosts[1])
    e_turns_html = render_turns_html(deck.evening_turns, deck.hosts[0], deck.hosts[1])

    m_audio_html = f'<audio controls class="audio-ctrl" src="{m_audio}"></audio>' if m_audio else '<div class="audio-placeholder">🔊 Run with <code>--synthesise</code> to generate audio</div>'
    e_audio_html = f'<audio controls class="audio-ctrl" src="{e_audio}"></audio>' if e_audio else '<div class="audio-placeholder">🔊 Run with <code>--synthesise</code> to generate audio</div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hark Daily — Trending Banter Demo Lab</title>
<style>
  :root {{
    --bg: #090c10;
    --card: rgba(22, 27, 34, 0.85);
    --border: rgba(240, 246, 252, 0.1);
    --matthew: #58a6ff;
    --kelly: #f778ba;
    --tag: #e3b341;
    --text: #e6edf3;
    --muted: #8b949e;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  body {{ background: var(--bg); color: var(--text); padding: 2rem 1rem; display: flex; justify-content: center; }}
  .container {{ max-width: 900px; width: 100%; display: flex; flex-direction: column; gap: 1.5rem; }}
  .header {{ border-bottom: 1px solid var(--border); padding-bottom: 1.25rem; }}
  .badge {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); }}
  h1 {{ font-size: 1.75rem; margin-top: 0.5rem; }}
  .desc {{ color: var(--muted); font-size: 0.95rem; margin-top: 0.25rem; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 1.5rem; display: flex; flex-direction: column; gap: 1rem; box-shadow: 0 8px 24px rgba(0,0,0,0.4); }}
  .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }}
  .slot-title {{ font-size: 1.25rem; font-weight: 700; }}
  .topic-badge {{ background: rgba(227, 179, 65, 0.15); color: var(--tag); border: 1px solid rgba(227, 179, 65, 0.3); padding: 4px 10px; border-radius: 8px; font-size: 0.8rem; font-weight: 600; }}
  .headline {{ font-size: 1rem; color: #79c0ff; font-weight: 600; }}
  .summary {{ font-size: 0.88rem; color: var(--muted); line-height: 1.4; }}
  .dialogue-box {{ display: flex; flex-direction: column; gap: 0.75rem; background: rgba(13, 17, 23, 0.6); padding: 1.25rem; border-radius: 12px; border: 1px solid var(--border); }}
  .turn-row {{ display: flex; align-items: flex-start; gap: 0.75rem; }}
  .speaker-pill {{ font-size: 0.75rem; font-weight: 700; text-transform: uppercase; padding: 3px 8px; border-radius: 6px; white-space: nowrap; margin-top: 2px; }}
  .speaker-matthew .speaker-pill {{ background: rgba(88, 166, 255, 0.15); color: var(--matthew); border: 1px solid rgba(88, 166, 255, 0.3); }}
  .speaker-kelly .speaker-pill {{ background: rgba(247, 120, 186, 0.15); color: var(--kelly); border: 1px solid rgba(247, 120, 186, 0.3); }}
  .speaker-text {{ font-size: 0.92rem; line-height: 1.45; }}
  .voice-tag {{ color: var(--tag); font-style: italic; font-weight: 600; background: rgba(227, 179, 65, 0.1); padding: 1px 4px; border-radius: 4px; }}
  .audio-ctrl {{ width: 100%; border-radius: 8px; margin-top: 0.5rem; }}
  .audio-placeholder {{ font-size: 0.82rem; color: var(--muted); background: rgba(255,255,255,0.03); padding: 0.75rem; border-radius: 8px; text-align: center; }}
  code {{ background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px; font-size: 0.82rem; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <span class="badge">Non-Prod Laboratory</span>
    <h1>🎙️ Hark Daily — Trending Banter Preview</h1>
    <p class="desc">Two-Host cold open tests featuring Matthew & Kelly • Zero social media mentions • Quirky cultural observations • Smooth news bridge</p>
  </div>

  <div class="card">
    <div class="card-top">
      <div>
        <div class="slot-title">🌅 Morning Edition</div>
        <div class="headline">{deck.morning_topic.headline}</div>
      </div>
      <span class="topic-badge">{deck.morning_topic.term}</span>
    </div>
    <p class="summary">{deck.morning_topic.summary}</p>
    <div class="dialogue-box">
      {m_turns_html}
    </div>
    {m_audio_html}
  </div>

  <div class="card">
    <div class="card-top">
      <div>
        <div class="slot-title">🌆 Evening Edition</div>
        <div class="headline">{deck.evening_topic.headline}</div>
      </div>
      <span class="topic-badge">{deck.evening_topic.term}</span>
    </div>
    <p class="summary">{deck.evening_topic.summary}</p>
    <div class="dialogue-box">
      {e_turns_html}
    </div>
    {e_audio_html}
  </div>
</div>
</body>
</html>
"""
    html_path.write_text(html, encoding="utf-8")
    log.info("✓ HTML Player generated: %s", html_path)
    return html_path


async def synthesise_turns(
    turns: list[tuple[int, str]],
    voice_ids: tuple[str, str],
    voice_service_url: str = "http://127.0.0.1:8090",
) -> tuple[bytes, float]:
    """Synthesises turns locally via Chatterbox-Turbo and stitches them."""
    import httpx

    raw_turns: list[tuple[bytes, float, float]] = []
    async with httpx.AsyncClient(timeout=120) as client:
        for who, text in turns:
            voice_id = voice_ids[who]
            raw_audio, duration = await synthesise(client, voice_service_url, text, voice_id)
            raw_turns.append((raw_audio, duration, 0.40))

    mp3_bytes, total_sec, _ = await asyncio.to_thread(podcast.stitch_turn_audio, raw_turns)
    return mp3_bytes, total_sec


def main() -> int:
    parser = argparse.ArgumentParser(description="Hark Daily Trending Banter Non-Prod Demo")
    parser.add_argument("--list", action="store_true", help="List all available curated trending topics")
    parser.add_argument("--review", action="store_true", help="Print the formatted review deck")
    parser.add_argument("--schedule", choices=["morning", "evening", "both"], default="both", help="Schedule slot")
    parser.add_argument("--topic", help="Select specific topic by id (e.g. coffee-badging)")
    parser.add_argument("--synthesise", action="store_true", help="Synthesise audio locally via voice service")
    parser.add_argument("--html", action="store_true", help="Generate interactive HTML player preview")
    parser.add_argument("--json", action="store_true", help="Output review deck as JSON")
    args = parser.parse_args()

    if args.list:
        print("\nAvailable Curated Trending Topics (Family-Safe, No Social Media Brands):")
        print("-" * 75)
        for t in trending.CURATED_TRENDS:
            print(f"[{t.slot.upper():7}] {t.topic_id:25} | {t.term:20} ({t.category})")
        print("-" * 75)
        return 0

    morning, evening = trending.get_schedule_pair()
    if args.topic:
        chosen = trending.get_curated_topic(args.topic)
        if not chosen:
            print(f"Error: Unknown topic '{args.topic}'. Use --list to see options.")
            return 1
        if chosen.slot == "evening":
            evening = chosen
        else:
            morning = chosen

    m_turns = trending.build_trending_script(morning)
    e_turns = trending.build_trending_script(evening)
    deck = trending.DailyReviewDeck(
        morning_topic=morning,
        morning_turns=m_turns,
        evening_topic=evening,
        evening_turns=e_turns,
        hosts=("Matthew", "Kelly"),
    )

    if args.json:
        print(json.dumps(deck.to_dict(), indent=2))
        return 0

    audio_files: dict[str, str] = {}
    if args.synthesise:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        voice_service = os.environ.get("VOICE_SERVICE_URL", "http://127.0.0.1:8090")
        log.info("Checking local voice service at %s...", voice_service)
        try:
            voices = ("matthew_reference", "kelly_reference")
            if args.schedule in ("morning", "both"):
                log.info("Synthesising Morning Banter: '%s'...", morning.term)
                m_audio, m_dur = asyncio.run(synthesise_turns(m_turns, voices, voice_service))
                m_file = OUTPUT_DIR / f"morning_{morning.topic_id}.mp3"
                m_file.write_bytes(m_audio)
                audio_files["morning"] = str(m_file.name)
                log.info("✓ Saved Morning Banter: %s (%.1fs)", m_file, m_dur)

            if args.schedule in ("evening", "both"):
                log.info("Synthesising Evening Banter: '%s'...", evening.term)
                e_audio, e_dur = asyncio.run(synthesise_turns(e_turns, voices, voice_service))
                e_file = OUTPUT_DIR / f"evening_{evening.topic_id}.mp3"
                e_file.write_bytes(e_audio)
                audio_files["evening"] = str(e_file.name)
                log.info("✓ Saved Evening Banter: %s (%.1fs)", e_file, e_dur)
        except Exception as exc:
            log.warning("Audio synthesis skipped: %s (is local voice service running?)", exc)

    if args.html or args.synthesise:
        html_path = generate_html_player(deck, audio_files)
        print(f"\n✨ Interactive Player generated: file://{html_path.resolve()}\n")

    # Default output is review deck
    print(deck.format_terminal())
    return 0


if __name__ == "__main__":
    sys.exit(main())
