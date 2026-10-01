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


def _filler(n, section="tech"):
    """Unrelated headlines, so the pool is big enough for word rarity to mean something."""
    return [_item(f"Topic{k} update on item{k} from place{k}", section=section, source=f"F{k}", pos=4)
            for k in range(n)]


def test_ranking_merges_differently_worded_headlines_about_the_same_rare_names():
    items = [
        _item("Google announces Gemini 4 Argon AI model, but you can't use it yet", section="tech", source="Ars"),
        _item("Google announces Gemini 4 and says it's so capable that only trusted cyber defenders can have it",
              section="tech", source="Verge"),
        _item("Gemini 4 Argon", section="tech", source="HN"),
        _item("Sam Altman says OpenAI won't go public until its models are safe", section="tech", source="Verge"),
        _item("Why is Sam Altman a free man?", section="tech", source="HN"),
        _item("Google tests a new Pixel feature for photos", section="tech", source="Ars"),
        *_filler(60),
    ]
    picked = select_top(items, {"tech": 70})["tech"]
    gemini = [s for s in picked if "Gemini" in s.lead.title]
    assert len(gemini) == 1 and set(gemini[0].sources) == {"Ars", "Verge", "HN"}
    assert len([s for s in picked if "Altman" in s.lead.title]) == 2, "a shared name alone isn't the same story"
    assert any("Pixel" in s.lead.title for s in picked)


def test_ranking_skips_stories_already_heard():
    told = _item("Saskatchewan mayor stepping down now that Queen of Canada cult is gone", source="CBC")
    items = [
        told,
        _item("Saskatchewan mayor who clashed with Queen of Canada cult to step down", source="Globe"),
        _item("Minimum wage hike is now in effect across five provinces", source="Globe", pos=1),
        _item("Province names new health minister", source="CBC", pos=2),
    ]
    heard = [{"url": "https://elsewhere/1", "original_title": "Minimum wage hikes set to begin across five provinces",
              "links": [{"source": "CBC", "url": told.url}]}]
    picked = select_top(items, {"canada": 5}, heard=heard)["canada"]
    assert [s.lead.title for s in picked] == ["Province names new health minister"]


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


def test_every_request_must_reach_a_public_address(monkeypatch):
    """Redirects and scraped links go through the client hook, so none can reach the home network."""
    import httpx
    import pytest

    from app import fetcher
    from app.fetcher import FetchError

    monkeypatch.setattr(fetcher, "ALLOW_PRIVATE", False)
    for url in ("http://10.0.0.233:8080/", "http://127.0.0.1/", "http://192.168.1.1/admin", "http://169.254.169.254/"):
        with pytest.raises(FetchError):
            asyncio.run(fetcher._public_only(httpx.Request("GET", url)))
    monkeypatch.setattr(fetcher, "ALLOW_PRIVATE", True)
    asyncio.run(fetcher._public_only(httpx.Request("GET", "http://10.0.0.233/")))
