from __future__ import annotations

from app.fetcher import Item
from app.guardian import PROVIDER, SECTIONS, feed_url, source_for, top_n


def test_top_n_skips_media_player_stubs():
    items = [
        Item(title="Watch live stream", url="https://www.cbc.ca/player/play/123", source_id=1, source_name="CBC", section="sports"),
        Item(title="Real sports story", url="https://www.cbc.ca/sports/story-456", source_id=1, source_name="CBC", section="sports"),
    ]
    picked = top_n(items, n=1)
    assert len(picked) == 1
    assert picked[0].title == "Real sports story"


def test_every_section_names_its_own_provider_and_feed():
    for key, section in SECTIONS.items():
        assert section["title"], key
        assert section["provider"], key
        assert section["feed"].startswith("https://"), key


def test_sections_do_not_all_come_from_one_provider():
    providers = {section["provider"] for section in SECTIONS.values()}
    assert len(providers) > 1


def test_source_for_uses_the_sections_own_provider():
    for key, section in SECTIONS.items():
        source = source_for(key)
        assert source["name"] == f"{section['provider']} · {section['title']}"
        assert source["url"] == section["feed"]
        assert source["section"] == key


def test_feed_url_matches_the_section_map():
    for key, section in SECTIONS.items():
        assert feed_url(key) == section["feed"]


def test_pack_label_is_not_a_single_outlet():
    assert PROVIDER != "The Guardian"
