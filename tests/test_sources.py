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
