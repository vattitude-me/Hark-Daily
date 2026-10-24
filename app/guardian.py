"""A story pack where each section has its own source, and no AI in the path.

This is the collector for the no-AI approach: seven sections, the top five
stories each, every section taken from its own provider's RSS feed. Fetching
uses ``feedparser`` and article text uses ``trafilatura`` — the same
open-source tooling the worker already relies on — and the summary is the
built-in extractive summarizer in ``app/summarizer.py``. No LLM is involved
at any step.

Why the sources are split the way they are (see :data:`SECTIONS`):

* CBC News carries most sections: it is Canada's public broadcaster, its
  per-section RSS is clean and free to syndicate, and the feed order is the
  editor's ranking, so "top 5" is just the first five — no ranking model
  required.
* CBC has no AI feed, so AI comes from TechCrunch's dedicated AI feed.
* CBC has no general tech feed either — its technology feed is where its
  science, health and environment stories live — so Science uses that feed
  and Tech is BetaKit, the Canadian tech publication.
* This module used to read a single source (The Guardian, hence the name);
  the per-section map replaced that. To move a section, change its entry in
  :data:`SECTIONS`; nothing else changes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .fetcher import Item, enrich_items, fetch_source, make_client
from .summarizer import drop_boilerplate, summarize

log = logging.getLogger(__name__)

# key -> that section's own source: its provider and the provider's feed for
# the category. Order is the reading order. A section moves house by editing
# its entry here; the collector only needs a feed whose order is the editor's
# ranking.
SECTIONS: dict[str, dict] = {
    "top":           {"title": "Top stories",   "provider": "CBC News",   "feed": "https://www.cbc.ca/webfeed/rss/rss-topstories"},
    "ai":            {"title": "AI",            "provider": "TechCrunch", "feed": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    "tech":          {"title": "Tech",          "provider": "BetaKit",    "feed": "https://betakit.com/feed/"},
    "politics":      {"title": "Politics",      "provider": "CBC News",   "feed": "https://www.cbc.ca/webfeed/rss/rss-politics"},
    "entertainment": {"title": "Entertainment", "provider": "CBC News",   "feed": "https://www.cbc.ca/webfeed/rss/rss-arts"},
    "science":       {"title": "Science",       "provider": "CBC News",   "feed": "https://www.cbc.ca/webfeed/rss/rss-technology"},
    "sports":        {"title": "Sports",        "provider": "CBC News",   "feed": "https://www.cbc.ca/webfeed/rss/rss-sports"},
}

# The pack has no single provider anymore; this label only fills pack-level
# fields that predate per-section sources.
PROVIDER = "Mixed sources"

MAX_AGE = timedelta(hours=48)
DEFAULT_PER_SECTION = 5


def feed_url(key: str) -> str:
    return SECTIONS[key]["feed"]


def source_for(key: str) -> dict:
    """The worker's own source dict shape, so the existing fetcher reads the feed unchanged."""
    return {
        "id": 0,
        "name": f"{SECTIONS[key]['provider']} · {SECTIONS[key]['title']}",
        "url": SECTIONS[key]["feed"],
        "section": key,
        "weight": 1.0,
        "kind": "feed",
    }


def top_n(items: list[Item], n: int = DEFAULT_PER_SECTION, max_age: timedelta = MAX_AGE) -> list[Item]:
    """The editor's top ``n``: the feed is already ranked, so keep its order.

    Dead links and stale items are dropped first, but if a feed is entirely older
    than ``max_age`` we still return its head rather than nothing.
    """
    now = datetime.now(timezone.utc)
    seen: set[str] = set()
    fresh: list[Item] = []
    for item in items:
        if not item.title or not item.url or item.url in seen:
            continue
        seen.add(item.url)
        if item.published and (now - item.published) > max_age:
            continue
        fresh.append(item)
    return (fresh or items)[:n]


def script_for(item: Item, max_words: int = 60, title: str = "") -> str:
    """The spoken script: the built-in extractive summary, never an LLM."""
    body = drop_boilerplate(item.text) or item.summary or item.title
    return summarize(body, fallback=item.summary or item.title, max_words=max_words, title=item.title or title)


async def collect_section(client, key: str, limit: int = DEFAULT_PER_SECTION) -> list[Item]:
    items = await fetch_source(client, source_for(key))
    return top_n(items, limit)


async def collect(limit: int = DEFAULT_PER_SECTION, sections: list[str] | None = None) -> dict[str, list[Item]]:
    """Top ``limit`` stories for each section. One bad feed never sinks the rest."""
    keys = [k for k in (sections or list(SECTIONS)) if k in SECTIONS]
    async with make_client() as client:
        results = await asyncio.gather(*(collect_section(client, k, limit) for k in keys),
                                       return_exceptions=True)
    out: dict[str, list[Item]] = {}
    for key, res in zip(keys, results):
        if isinstance(res, Exception):  # noqa: BLE001 — report, keep going
            log.warning("%s · %s failed: %s", SECTIONS[key]["provider"], key, res)
            out[key] = []
        else:
            out[key] = res
    return out


def dedupe_sections(picked: dict[str, list[Item]]) -> dict[str, list[Item]]:
    """One telling per link across the whole pack.

    The section feeds overlap the top feed, so the same story can be a
    section's top item and also appear in Top stories. Sections are walked
    in reading order (top first) and the first telling wins."""
    seen: set[str] = set()
    out: dict[str, list[Item]] = {}
    for key, items in picked.items():
        kept = []
        for item in items:
            if item.url in seen:
                continue
            seen.add(item.url)
            kept.append(item)
        out[key] = kept
    return out


async def build_pack(per_section: int = DEFAULT_PER_SECTION, sections: list[str] | None = None,
                     max_words: int = 60) -> list[dict]:
    """The day's story pack: every section's top stories as ready-to-voice scripts."""
    picked = dedupe_sections(await collect(per_section, sections))
    await enrich_items([item for items in picked.values() for item in items])
    pack: list[dict] = []
    for key, items in picked.items():
        for rank, item in enumerate(items, 1):
            pack.append({
                "id": item.id,
                "section": key,
                "rank": rank,
                "title": item.title,
                "source": item.source_name or PROVIDER,
                "url": item.url,
                "published": item.published.isoformat() if item.published else None,
                "image": item.image,
                "script": script_for(item, max_words=max_words, title=item.title),
            })
    return pack


async def _amain(args: argparse.Namespace) -> int:
    sections = args.sections.split(",") if args.sections else None
    pack = await build_pack(per_section=args.per_section, sections=sections, max_words=args.max_words)
    payload = {"date": args.date, "provider": PROVIDER, "stories": pack}
    if args.out:
        args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.out}  ({len(pack)} stories)")
        return 0
    for story in pack:
        print(f"[{story['section']:>2} #{story['rank']}] {story['title']}")
        print(f"        {story['script']}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Top stories per section, each from its own source, no AI.")
    ap.add_argument("--per-section", type=int, default=DEFAULT_PER_SECTION)
    ap.add_argument("--sections", help="Comma-separated subset (default: all seven)")
    ap.add_argument("--max-words", type=int, default=60, help="Script length per story")
    ap.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    ap.add_argument("--out", type=Path, help="Write the pack as JSON instead of printing it")
    return asyncio.run(_amain(ap.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
