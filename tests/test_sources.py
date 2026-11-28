"""The shared source catalog: sections, local news and followed names."""
from app.fetcher import parse_feed
from app.sources import BUILTIN_SOURCES, SECTIONS, follow_url, is_follow_url, local_sources
from app.writer import section_leads


def test_every_category_offers_five_sources():
    for key in SECTIONS:
        if key in ("local", "follow", "custom"):
            continue
        assert len([s for s in BUILTIN_SOURCES if s["section"] == key]) == 5, key
    assert len({s["url"] for s in BUILTIN_SOURCES}) == len(BUILTIN_SOURCES)


def test_local_news_uses_the_city_with_its_own_outlets_where_we_know_them():
    toronto = local_sources("Toronto")
    assert toronto[0]["name"] == "CBC News · Toronto"
    assert toronto[-1]["url"].startswith("https://news.google.com/rss/headlines/section/geo/Toronto?")
    assert all(s["section"] == "local" for s in toronto)
    assert local_sources("Mississauga")[0]["name"] == "CBC News · Toronto"  # a suburb gets its city's news
    anywhere = local_sources("Prince George, BC")
    assert [s["name"] for s in anywhere] == ["Google News · Prince George"]
    assert "geo/Prince%20George?" in anywhere[0]["url"]
    assert local_sources("") == []


def test_a_followed_name_becomes_a_news_search():
    url = follow_url(' "Connor McDavid" ')
    assert url.startswith("https://news.google.com/rss/search?q=%22Connor+McDavid%22+when:3d")
    assert is_follow_url(url) and not is_follow_url("https://www.cbc.ca/sports")


def test_local_section_names_the_city():
    assert section_leads(["canada", "local"], "Toronto")["local"] == "And finally, the latest from around Toronto."


def test_clean_img_url_handles_schemes_and_blocked_domains():
    from app.fetcher import _clean_img_url
    assert _clean_img_url(None) is None
    assert _clean_img_url("") is None
    assert _clean_img_url("ftp://example.com/pic.jpg") is None
    # http is upgraded to https
    assert _clean_img_url("http://example.com/pic.jpg") == "https://example.com/pic.jpg"
    assert _clean_img_url("https://example.com/pic.jpg") == "https://example.com/pic.jpg"
    # Hotlink-blocking domains (e.g. ESPNcricinfo imgci) return None
    assert _clean_img_url("http://p.imgci.com/db/PICTURES/CMS/424100/424116.jpg") is None
    assert _clean_img_url("https://p.imgci.com/pic.jpg") is None



def test_google_news_items_credit_the_outlet_not_google():
    feed = b"""<rss><channel><title>"Connor McDavid" - Google News</title>
      <item><title>McDavid scores twice in opener - Sportsnet</title>
        <link>https://news.google.com/rss/articles/CBMiABC?oc=5</link>
        <description>&lt;a href="https://news.google.com/rss/articles/CBMiABC"&gt;McDavid scores twice&lt;/a&gt;</description>
        <source url="https://www.sportsnet.ca">Sportsnet</source></item>
    </channel></rss>"""
    _, items = parse_feed(feed, {"id": 9, "name": "Connor McDavid", "section": "follow"})
    assert items[0].title == "McDavid scores twice in opener"
    assert items[0].source_name == "Sportsnet"
    assert items[0].summary == ""


def test_parse_feed_extracts_content_encoded_and_strips_yoast_footer():
    from app.summarizer import summarize

    feed = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>India – DD India</title>
    <item>
      <title>India set to host ITU conference in 2030</title>
      <link>https://ddindia.co.in/2026/11/india-set-to-host-itu-2030/</link>
      <description><![CDATA[<p>India will host the International Telecommunication Union policy conference in 2030 [&#8230;]</p>
<p>The post <a href="https://ddindia.co.in/2026/11/india-set-to-host-itu-2030/">India set to host ITU conference in 2030</a> appeared first on <a href="https://ddindia.co.in">DD India</a>.</p>]]></description>
      <content:encoded><![CDATA[<p>India is set to host the International Telecommunication Union policy-making conference in 2030 following formal acceptance in Doha.</p>
<p>The four-year gathering sets global telecom standards, coordinates radio spectrum policy, and advances digital connectivity initiatives across member nations.</p>
<p>Senior officials noted that India has steadily expanded its technical contributions to international standards bodies over the past decade.</p>
<p>IANS</p>
<p>The post <a href="https://ddindia.co.in/2026/11/india-set-to-host-itu-2030/">India set to host ITU conference in 2030</a> appeared first on <a href="https://ddindia.co.in">DD India</a>.</p>]]></content:encoded>
    </item>
  </channel>
</rss>""".encode("utf-8")

    _, items = parse_feed(feed, {"id": 0, "name": "DD News · Top stories", "section": "top_in"})
    assert len(items) == 1
    item = items[0]
    assert "appeared first on" not in item.summary.lower()
    assert item.summary.endswith("…")
    assert "\n" in item.text
    assert "four-year gathering sets global telecom standards" in item.text
    assert "appeared first on" not in item.text.lower()

    summary = summarize(item.text, fallback=item.summary, title=item.title)
    assert "appeared first on" not in summary.lower()
    assert summary


def test_enrich_items_upgrades_feed_thumbnail_and_keeps_rss_body_on_failure(monkeypatch):
    import asyncio
    import httpx
    from app import fetcher
    from app.fetcher import FetchError, Item, enrich_items

    rss_body = (
        "First paragraph with full context from the RSS feed content block.\n"
        "Second paragraph providing additional reporting details so length stays above two hundred characters."
    )
    ok_item = Item(
        title="Parliament begins winter session discussion",
        url="https://ddindia.co.in/2026/11/winter-session/",
        source_id=0,
        source_name="DD News · Top stories",
        section="top_in",
        summary="Parliament begins discussion.",
        image="https://ddindia.co.in/wp-content/uploads/thumb-150.jpg",
        text=rss_body,
        kind="feed",
    )
    timeout_item = Item(
        title="Joint commission meets in New Delhi",
        url="https://ddindia.co.in/2026/11/joint-commission/",
        source_id=0,
        source_name="DD News · Top stories",
        section="top_in",
        summary="Joint commission meets.",
        image=None,
        text=rss_body,
        kind="feed",
    )

    async def fake_get(client, url):
        if "joint-commission" in url:
            raise FetchError("timeout")
        html_doc = (
            '<html><head>'
            '<meta property="og:image" content="https://ddindia.co.in/wp-content/uploads/hero-full.jpg"/>'
            '</head><body><article><p>Short stub.</p></article></body></html>'
        )
        return httpx.Response(200, text=html_doc, request=httpx.Request("GET", url))

    monkeypatch.setattr(fetcher, "ALLOW_PRIVATE", True)
    monkeypatch.setattr(fetcher, "_get", fake_get)

    asyncio.run(enrich_items([ok_item, timeout_item]))

    assert ok_item.image == "https://ddindia.co.in/wp-content/uploads/hero-full.jpg"
    assert ok_item.text == rss_body
    assert timeout_item.text == rss_body


def test_clean_headline_strips_dd_news_suffixes():
    from app.podcast_text import clean_headline

    assert clean_headline("Major update | DD News") == "Major update"
    assert clean_headline("Major update - DD India") == "Major update"
