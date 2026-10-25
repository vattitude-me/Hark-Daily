"""Multi-provider story topics and section collector.

Collects top stories across configured briefing topics/sections (see :data:`SECTIONS`).
Each section is mapped to its provider and RSS feed. Fetching uses ``feedparser``
and article extraction uses ``trafilatura``, summarized with ``app/summarizer.py``.

Why the topics are configured this way (see :data:`SECTIONS`):
* CBC News provides clean, editorially curated RSS feeds for broad public interest topics:
  Top stories, Politics, Entertainment, Science, and Sports.
* TechCrunch provides specialized industry reporting for AI.
* BetaKit provides Canadian tech ecosystem reporting for Tech.
* To change or re-route any topic, simply update its entry in :data:`SECTIONS`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .fetcher import Item, enrich_items, fetch_source, make_client
from .summarizer import CONNECTORS, drop_boilerplate, format_script, get_connector, summarize

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
# Extra candidates a section keeps in hand, so losing a story to an earlier section does not leave
# it short of its count.
DEDUP_MARGIN = 5


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
        if not item.title or not item.url or item.url in seen or "/player/play/" in item.url:
            continue
        seen.add(item.url)
        if item.published and (now - item.published) > max_age:
            continue
        fresh.append(item)
    return (fresh or items)[:n]


def bare_url(url: str | None) -> str:
    """A link stripped of the parts that differ between two pointers to the same article."""
    return (url or "").split("#")[0].split("?")[0].rstrip("/").lower()


def plain_title(title: str | None) -> str:
    """A headline reduced to its words, for comparing the same story carried by two feeds."""
    return " ".join(re.findall(r"[a-z0-9]+", (title or "").lower()))


def pick_unique(picked: dict[str, list[Item]],
                per_section: int = DEFAULT_PER_SECTION) -> dict[str, list[Item]]:
    """Each story is told once, in the first section that carries it.

    A provider can run the same article in more than one feed, so without this the day's brief can
    read its top story twice: once under Top stories and again under Tech or Sport. Sections keep
    their reading order, so the earlier one wins and the later one moves down its list. Two entries
    count as the same story when their links agree once query strings are dropped, or when their
    headlines do.
    """
    urls: set[str] = set()
    titles: set[str] = set()
    out: dict[str, list[Item]] = {}
    for key, items in picked.items():
        chosen: list[Item] = []
        for item in items:
            url, title = bare_url(item.url), plain_title(item.title)
            if url in urls or (title and title in titles):
                continue
            urls.add(url)
            if title:
                titles.add(title)
            chosen.append(item)
            if len(chosen) == per_section:
                break
        out[key] = chosen
    return out


def body_summary_for(item: Item, max_words: int = 60, title: str = "", rank: int = 1) -> str:
    """The clean body summary for the visual card (no headline, no podcast connector)."""
    headline = (item.title or title or "").strip()
    connector = get_connector(rank)
    head_words = len(headline.split())
    conn_words = len(connector.split())
    body_budget = max(25, max_words - head_words - conn_words)

    body = drop_boilerplate(item.text) or item.summary or item.title
    return summarize(body, fallback=item.summary or item.title, max_words=body_budget, title=headline)


def script_for(item: Item, max_words: int = 60, title: str = "", rank: int = 1) -> str:
    """The spoken broadcast script: [Headline] + [Podcast Banter Filler] + [Body Summary]."""
    headline = (item.title or title or "").strip()
    connector = get_connector(rank)
    summary = body_summary_for(item, max_words=max_words, title=headline, rank=rank)
    return format_script(headline, summary, rank=rank, connector=connector)


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


async def build_pack(per_section: int = DEFAULT_PER_SECTION, sections: list[str] | None = None,
                     max_words: int = 60) -> list[dict]:
    """The day's story pack: every section's top stories as ready-to-voice scripts.

    A story carried by two feeds is told once, under the earlier section, and that section's next
    candidate takes its place.
    """
    keys = [k for k in (sections or list(SECTIONS)) if k in SECTIONS]
    # Ask each feed for more than we need, since a section can lose its head to an earlier section.
    collected = await collect(per_section + DEDUP_MARGIN, sections)
    picked = pick_unique({k: collected.get(k, []) for k in keys}, per_section)
    # Only the stories that made it are read, which also saves the article fetches for the rest.
    await enrich_items([item for items in picked.values() for item in items])
    pack: list[dict] = []
    for key in keys:
        for rank, item in enumerate(picked.get(key, []), 1):
            summary = body_summary_for(item, max_words=max_words, title=item.title, rank=rank)
            pack.append({
                "id": item.id,
                "section": key,
                "rank": rank,
                "title": item.title,
                "source": item.source_name or PROVIDER,
                "url": item.url,
                "published": item.published.isoformat() if item.published else None,
                "image": item.image,
                "summary": summary,
                "script": format_script(item.title, summary, rank=rank),
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
