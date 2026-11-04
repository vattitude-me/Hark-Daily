from __future__ import annotations

import pytest
from app import trending


def test_curated_trends_catalog_integrity():
    assert len(trending.CURATED_TRENDS) >= 8
    morning = [t for t in trending.CURATED_TRENDS if t.slot == "morning"]
    evening = [t for t in trending.CURATED_TRENDS if t.slot == "evening"]
    assert len(morning) >= 4
    assert len(evening) >= 4
    for topic in trending.CURATED_TRENDS:
        assert topic.topic_id
        assert topic.term
        assert topic.headline
        assert topic.summary
        assert topic.category in ("workplace", "lifestyle", "habits", "culture")


def test_sanitize_text_removes_social_platforms():
    text = "Did you see that video on TikTok about desk bombing from Twitter and Reddit?"
    cleaned = trending.sanitize_text(text)
    assert "tiktok" not in cleaned.lower()
    assert "twitter" not in cleaned.lower()
    assert "reddit" not in cleaned.lower()
    assert "online" in cleaned.lower()


def test_validate_banter_turns_happy_path():
    turns = [
        (0, "Kelly, did you hear about coffee badging?"),
        (1, "Wait, what does that mean?"),
        (0, "Showing up to the office just for coffee and heading home. [chuckle]"),
        (1, "[laugh] That is ridiculous! Well, let's get into the top headlines."),
    ]
    is_valid, msg = trending.validate_banter_turns(turns)
    assert is_valid, msg


def test_validate_banter_turns_rejects_banned_socials():
    turns = [
        (0, "Did you see this trend on TikTok?"),
        (1, "No, what was on TikTok?"),
        (0, "Everyone is talking about it on Twitter. [chuckle]"),
        (1, "Let's check the top headlines."),
    ]
    is_valid, msg = trending.validate_banter_turns(turns)
    assert not is_valid
    assert "Banned social media platform" in msg


def test_validate_banter_turns_rejects_vulgarity():
    turns = [
        (0, "Kelly, look at this damn buzzword."),
        (1, "What is it?"),
        (0, "People are acting crazy. [chuckle]"),
        (1, "Let's check the top headlines."),
    ]
    is_valid, msg = trending.validate_banter_turns(turns)
    assert not is_valid
    assert "Vulgar or inappropriate" in msg


def test_validate_banter_turns_requires_news_bridge():
    turns = [
        (0, "Kelly, have you heard about silent walking making the rounds online?"),
        (1, "No, what on earth is that supposed to be?"),
        (0, "Just walking outside with no headphones and no smartphone in your hand."),
        (1, "[laugh] That is literally just walking! Why do people invent silly names for basic life? See ya later."),
    ]
    is_valid, msg = trending.validate_banter_turns(turns)
    assert not is_valid
    assert "Final turns must bridge smoothly into the news" in msg


def test_all_curated_dialogues_pass_validation():
    for topic_id, turns in trending.CURATED_DIALOGUES.items():
        is_valid, msg = trending.validate_banter_turns(turns)
        assert is_valid, f"Curated dialogue for '{topic_id}' failed validation: {msg}"


def test_daily_review_deck_formatting():
    morning, evening = trending.get_schedule_pair()
    m_turns = trending.build_trending_script(morning)
    e_turns = trending.build_trending_script(evening)
    deck = trending.DailyReviewDeck(
        morning_topic=morning,
        morning_turns=m_turns,
        evening_topic=evening,
        evening_turns=e_turns,
        hosts=("Matthew", "Kelly"),
    )
    output = deck.format_terminal()
    assert "HARK DAILY — NON-PROD TRENDING BANTER REVIEW DECK" in output
    assert "MORNING SCHEDULE" in output
    assert "EVENING SCHEDULE" in output
    assert "[Matthew]:" in output
    assert "[Kelly]:" in output

    data = deck.to_dict()
    assert "morning" in data
    assert "evening" in data
    assert data["morning"]["topic"]["term"] == morning.term
