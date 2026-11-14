"""Targeted unit and regression tests for refactored shared helpers and bug fixes."""
from __future__ import annotations

import dataclasses
from datetime import datetime
from zoneinfo import ZoneInfo

from app import llm, run_report, storypack, topics
from app.tts.text import clean_punctuation


def test_base_section_and_region():
    assert topics.base_section(None) == ""
    assert topics.base_section("") == ""
    assert topics.base_section("top") == "top"
    assert topics.base_section("top_us") == "top"
    assert topics.base_section("sports_in") == "sports"

    assert topics.section_region("top") == "ca"
    assert topics.section_region("tech_us") == "us"
    assert topics.section_region("markets_in") == "in"
    assert topics.section_region("ai_global") == "ca"


def test_config_is_admin_and_local_today(cfg):
    c = dataclasses.replace(cfg, admin_emails=("boss@example.com",), timezone="UTC")
    assert c.is_admin({"is_admin": True, "email": "user@example.com"})
    assert c.is_admin({"is_admin": False, "email": "Boss@Example.com"})
    assert not c.is_admin({"is_admin": False, "email": "user@example.com"})
    assert not c.is_admin({})
    assert c.local_today() == datetime.now(ZoneInfo("UTC")).date().isoformat()


def test_clean_punctuation_variants():
    raw = "Markets surged — and tech followed - despite caution,, today,!"
    assert clean_punctuation(raw) == "Markets surged, and tech followed, despite caution, today!"
    assert clean_punctuation("a  —  b   c", collapse_whitespace=True) == "a, b c"


def test_llm_extract_json_and_chat_body():
    fenced = 'Sure! Here is the JSON:\n```json\n{"headline": "Hello", "ok": true}\n```\nDone.'
    assert llm.extract_json_text(fenced) == '{"headline": "Hello", "ok": true}'

    gpt_oss = llm.build_chat_body("openai/gpt-oss-120b", [{"role": "user", "content": "hi"}],
                                  temperature=0.3, max_tokens=200)
    assert gpt_oss["reasoning_effort"] == "low"
    assert gpt_oss["response_format"] == {"type": "json_object"}

    llama = llm.build_chat_body("llama3.1:8b", [{"role": "user", "content": "hi"}],
                                temperature=0.3, max_tokens=200, json_mode=False)
    assert "reasoning_effort" not in llama
    assert "response_format" not in llama


def test_prune_older_removes_orphans_across_all_tables(store):
    old_day = "2020-01-01"
    # Story audio row AND a podcast clip row plus an orphaned file in storage under stories/{old_day}/.
    store.objects[f"stories/{old_day}/top-1.mp3"] = b"story-audio"
    store.objects[f"stories/{old_day}/orphan-extra.mp3"] = b"orphan"
    store.objects[f"podcast/{old_day}/open-1.mp3"] = b"podcast-clip"
    store.objects["notes/static/intro_top.mp3"] = b"static-keep"

    store.tables["story_audio"] = [
        {"id": 1, "date": old_day, "section": "top", "rank": 1, "voice": "v1",
         "audio_path": f"stories/{old_day}/top-1.mp3"},
    ]
    store.tables["voice_notes"] = [
        {"date": "1900-01-01", "voice": "v1", "note_key": "intro_top",
         "audio_path": "notes/static/intro_top.mp3"},
    ]
    store.tables["podcast_clips"] = [
        {"date": old_day, "clip_key": "open", "voice": "v1",
         "audio_path": f"podcast/{old_day}/open-1.mp3"},
    ]

    removed_calls = []
    orig_remove = store.remove_objects

    def spy_remove(paths):
        removed_calls.append(list(paths))
        orig_remove(paths)

    store.remove_objects = spy_remove
    pruned_days = storypack.prune_older(store, keep="2020-01-05", keep_days=2)

    assert old_day in pruned_days
    assert f"stories/{old_day}/top-1.mp3" not in store.objects
    assert f"stories/{old_day}/orphan-extra.mp3" not in store.objects
    assert f"podcast/{old_day}/open-1.mp3" not in store.objects
    assert "notes/static/intro_top.mp3" in store.objects
    # Orphans check must not re-delete files already deleted from story_audio or podcast_clips.
    all_removed = [p for call in removed_calls for p in call]
    assert len(all_removed) == len(set(all_removed))


def test_run_report_edition_sections_match_topics():
    assert run_report.EDITION_SECTIONS["Canada (CA)"] == topics.EDITION_SECTIONS["ca"]
    assert run_report.EDITION_SECTIONS["United States (US)"] == topics.EDITION_SECTIONS["us"]
    assert run_report.EDITION_SECTIONS["India (IN)"] == topics.EDITION_SECTIONS["in"]
    assert "markets" in run_report.EDITION_SECTIONS["Canada (CA)"]
    assert "ai" in run_report.EDITION_SECTIONS["Canada (CA)"]
    assert "science" in run_report.EDITION_SECTIONS["Canada (CA)"]
