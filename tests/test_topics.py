from __future__ import annotations

from app.fetcher import Item
from app.topics import PROVIDER, SECTIONS, feed_url, source_for, top_n


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


def test_headline_overlap_and_deduplication():
    from app.summarizer import headline_overlap, summarize

    headline = "Ottawa announces new $5,000 EV rebate program for Canadian car buyers"
    dup_lead = "The federal government in Ottawa announced a new $5,000 electric vehicle rebate program for Canadian car buyers on Friday."
    fresh_body = "The initiative aims to accelerate zero-emission adoption ahead of 2035 targets. Dealerships will apply the discount directly at point of sale."
    article = f"{dup_lead}\n\n{fresh_body}"

    # Overlap should be >= 0.60
    assert headline_overlap(headline, dup_lead) >= 0.60

    # Summarize with title should skip the duplicate lead sentence
    summary = summarize(article, title=headline, max_words=60)
    assert "The initiative aims to accelerate" in summary
    assert "The federal government in Ottawa announced" not in summary


def test_script_for_includes_headline_and_rotating_connector():
    from app.summarizer import CONNECTORS
    from app.topics import script_for

    item1 = Item(
        title="Bank of Canada holds benchmark interest rate",
        url="https://example.com/story-1",
        text="The central bank kept its key overnight rate at 2.5 per cent amid steady economic signals.",
        source_id=1,
        source_name="CBC",
        section="top",
    )
    script1 = script_for(item1, rank=1)
    assert script1.startswith("Bank of Canada holds benchmark interest rate.")
    assert CONNECTORS[0] in script1
    assert "2.5 per cent" in script1

    item2 = Item(
        title="Tech stocks surge following breakthrough chip earnings",
        url="https://example.com/story-2",
        text="Major semiconductor firms saw double-digit growth as enterprise AI demand hit new records.",
        source_id=2,
        source_name="TechCrunch",
        section="ai",
    )
    script2 = script_for(item2, rank=2)
    assert script2.startswith("Tech stocks surge following breakthrough chip earnings.")
    assert CONNECTORS[1] in script2


def test_clean_sentence_strips_editorial_label_prefixes():
    from app.summarizer import clean_sentence, split_sentences, strip_headline_and_filler

    raw_para = "The news: On Thursday, the CSCA announced that Tara June Misra had stepped into the executive director role."
    cleaned = clean_sentence(raw_para)
    assert cleaned.startswith("On Thursday, the CSCA announced")
    assert "The news:" not in cleaned

    sents = split_sentences(raw_para)
    assert sents[0].startswith("On Thursday, the CSCA announced")

    title = "Canadian Startup Capital Association names new interim executive director"
    script = (
        "Canadian Startup Capital Association names new interim executive director. "
        "Taking a closer look: The news: On Thursday, the CSCA announced that Tara June Misra "
        "had stepped into the executive director role."
    )
    clean = strip_headline_and_filler(title, script)
    assert clean.startswith("On Thursday, the CSCA announced")
    assert "Canadian Startup Capital" not in clean
    assert "Taking a closer look:" not in clean
    assert "The news:" not in clean


