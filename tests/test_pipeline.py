from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app import audio
from app.fetcher import Item, detect, extract_page_links, parse_feed
from app.ranking import select_top, tokens
from app.summarizer import summarize
from app.tts.text import speakable

from . import fakenews
from .conftest import BASE


def test_parse_feed_reads_items_images_and_dates():
    name, items = parse_feed(fakenews.rss("tech", BASE).encode(), {"id": 1, "name": "Circuit", "section": "tech"})
    assert name == "Circuit Report"
    assert len(items) == len(fakenews.STORIES["tech"])
    first = items[0]
    assert first.title.startswith("New open-source AI model")
    assert first.image and first.image.startswith("https://picsum.photos/")
    assert first.published and first.published.tzinfo is not None


def _item(title, section="canada", source="A", pos=0, hours=1):
    return Item(title=title, url=f"https://x/{hash(title)}{source}", source_id=1, source_name=source,
                section=section, published=datetime.now(timezone.utc) - timedelta(hours=hours), position=pos, feed_len=5)


def test_ranking_merges_same_story_from_two_outlets():
    items = [
        _item("Bank of Canada holds key interest rate steady at 2.5 per cent", source="Maple"),
        _item("Bank of Canada leaves interest rate unchanged as inflation cools", source="Northern", pos=1),
        _item("Blue Jays clinch playoff spot with walk-off win", source="Maple", pos=2),
    ]
    picked = select_top(items, {"canada": 5})
    top = picked["canada"][0]
    assert "Bank of Canada" in top.lead.title
    assert set(top.sources) == {"Maple", "Northern"}
    assert len(picked["canada"]) == 2


def test_ranking_prefers_ai_and_drops_stale_and_deals():
    items = [
        _item("Best laptop deals this week: 30% off", section="tech", pos=0),
        _item("New AI model tops coding benchmark", section="tech", pos=3),
        _item("Ancient story about phones", section="tech", pos=0, hours=100),
    ]
    picked = select_top(items, {"tech": 3})["tech"]
    assert picked[0].lead.title.startswith("New AI model")
    assert all("Ancient" not in s.lead.title for s in picked)


def test_tokens_ignore_stopwords():
    assert tokens("The Bank of Canada holds rates") == {"bank", "canada", "hold", "rate"}


def test_summarize_prefers_lead_and_respects_length():
    text = " ".join(fakenews.STORIES["canada"][0][1].split(". "))
    summary = summarize(fakenews.STORIES["canada"][0][1], max_words=60)
    assert summary.startswith("The Bank of Canada kept its benchmark rate")
    assert len(summary.split()) <= 61
    assert summarize("", fallback="Short fallback text.") == "Short fallback text."
    assert text  # sanity


def test_speakable_expands_symbols_for_the_voice():
    out = speakable("Startup raises $120M (Series B) — up 30% vs. last year 🚀 https://x.co/a")
    assert "120 million dollars" in out
    assert "30 percent" in out
    assert "versus" in out
    assert "http" not in out and "🚀" not in out and "(" not in out
    assert speakable("C$2.5 billion deal").startswith("2.5 billion Canadian dollars")


def test_audio_assemble_tracks_chapters_and_encodes_mp3():
    tone = (0.3 * np.sin(np.linspace(0, 400, 24000))).astype(np.float32)
    pcm, marks = audio.assemble([("a", tone, 0.5), ("b", tone, 0.5)])
    assert marks["a"][0] < marks["a"][1] <= marks["b"][0] < marks["b"][1]
    assert np.max(np.abs(pcm)) <= 1.0
    mp3 = audio.encode_mp3(pcm)
    assert len(mp3) > 1000 and (mp3[:3] == b"ID3" or mp3[0] == 0xFF)


def test_extract_page_links_finds_headlines():
    page = """<html><body>
      <a href="/about">About us</a>
      <a href="/news/2026/09/city-council-approves-new-bike-lanes">City council approves new bike lanes on Bloor Street</a>
      <a href="/news/2026/09/local-bakery-wins-award">Local bakery wins national award for sourdough bread</a>
      <a href="https://other.com/news/x-y-z">Offsite link that should be ignored by the scraper</a>
    </body></html>"""
    links = extract_page_links(page, "https://local.example/news")
    assert [t for t, _ in links] == [
        "City council approves new bike lanes on Bloor Street",
        "Local bakery wins national award for sourdough bread",
    ]


@pytest.mark.parametrize(
    "url,kind",
    [
        (f"{BASE}/tech/feed.xml", "feed"),
        (f"{BASE}/", "feed"),  # home page advertises its feed via <link rel=alternate>
        (f"{BASE}/tech/articles/" + fakenews.slug(fakenews.STORIES["tech"][1][0]), "article"),
    ],
)
def test_detect_source_kinds(url, kind):
    d = asyncio.run(detect(url, allow_private=True))
    assert d.kind == kind
    assert d.sample
