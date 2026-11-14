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


# --------------------------------------------------------------------------- Pruning safety regressions

def test_prune_older_deduplicates_shared_and_duplicate_paths(store):
    old_day = "2020-01-01"
    shared = f"stories/{old_day}/shared.mp3"
    dup_same_table = f"stories/{old_day}/dup.mp3"
    store.objects[shared] = b"shared"
    store.objects[dup_same_table] = b"dup"

    # Duplicate path within story_audio AND cross-table reference in podcast_clips
    store.tables["story_audio"] = [
        {"id": 1, "date": old_day, "section": "top", "rank": 1, "voice": "v1", "audio_path": dup_same_table},
        {"id": 2, "date": old_day, "section": "top", "rank": 1, "voice": "v2", "audio_path": dup_same_table},
        {"id": 3, "date": old_day, "section": "tech", "rank": 1, "voice": "v1", "audio_path": shared},
    ]
    store.tables["podcast_clips"] = [
        {"date": old_day, "clip_key": "bridge_tech", "voice": "v1", "audio_path": shared},
    ]

    removed_calls: list[list[str]] = []
    orig_remove = store.remove_objects

    def spy_remove(paths):
        removed_calls.append(list(paths))
        orig_remove(paths)

    store.remove_objects = spy_remove
    storypack.prune_older(store, keep="2020-01-05", keep_days=2)

    all_removed = [p for call in removed_calls for p in call]
    assert sorted(all_removed) == sorted([dup_same_table, shared])
    assert len(all_removed) == len(set(all_removed)) == 2


def test_prune_older_db_failure_preserves_storage_and_retries_cleanly(store):
    old_day = "2020-01-01"
    sa_path = f"stories/{old_day}/top-1.mp3"
    pc_path = f"podcast/{old_day}/open-1.mp3"
    store.objects[sa_path] = b"keep-until-db-clears"
    store.objects[pc_path] = b"podcast"

    store.tables["story_audio"] = [
        {"id": 1, "date": old_day, "section": "top", "rank": 1, "voice": "v1", "audio_path": sa_path},
    ]
    store.tables["podcast_clips"] = [
        {"date": old_day, "clip_key": "open", "voice": "v1", "audio_path": pc_path},
    ]

    orig_delete = store.delete
    fail_story_audio = [True]

    def flaky_delete(table, params):
        if table == "story_audio" and fail_story_audio[0]:
            raise RuntimeError("DB timeout deleting story_audio")
        orig_delete(table, params)

    store.delete = flaky_delete
    days_first = storypack.prune_older(store, keep="2020-01-05", keep_days=2)

    # story_audio DB delete failed -> DB row AND its audio file MUST stay intact; podcast_clips still pruned!
    assert len(store.select("story_audio", {"date": f"eq.{old_day}"})) == 1
    assert sa_path in store.objects
    assert len(store.select("podcast_clips", {"date": f"eq.{old_day}"})) == 0
    assert pc_path not in store.objects
    assert days_first == [old_day]

    # Recover DB and re-run prune_older -> remaining data pruned idempotently
    fail_story_audio[0] = False
    days_second = storypack.prune_older(store, keep="2020-01-05", keep_days=2)
    assert days_second == [old_day]
    assert sa_path not in store.objects
    assert len(store.select("story_audio", {"date": f"eq.{old_day}"})) == 0

    # Third run against clean data is a safe no-op
    assert storypack.prune_older(store, keep="2020-01-05", keep_days=2) == []


def test_prune_older_storage_failure_and_partial_row_failure_and_missing_files(store):
    old_day = "2020-01-01"
    # voice_notes with partial DB failure on second row + shared object on failed row
    shared_note = f"notes/{old_day}/shared.mp3"
    ok_note = f"notes/{old_day}/ok.mp3"
    missing_obj = f"stories/{old_day}/already-missing.mp3"
    static_path = "notes/static/intro_top.mp3"
    preserved_story_path = f"stories/{old_day}/top_in-1.mp3"

    store.objects[shared_note] = b"shared-note"
    store.objects[ok_note] = b"ok-note"
    store.objects[static_path] = b"static"
    store.objects[preserved_story_path] = b"preserve-in"
    # Notice missing_obj intentionally NOT in store.objects!

    store.tables["story_audio"] = [
        {"id": 1, "date": old_day, "section": "top", "rank": 1, "voice": "v1", "audio_path": missing_obj},
        {"id": 2, "date": old_day, "section": "top_in", "rank": 1, "voice": "v1", "audio_path": preserved_story_path},
    ]
    store.tables["voice_notes"] = [
        {"date": storypack.STATIC_DATE, "voice": "v1", "note_key": "intro_top", "audio_path": static_path},
        {"date": old_day, "voice": "v1", "note_key": "k1", "audio_path": ok_note},
        {"date": old_day, "voice": "v1", "note_key": "k2", "audio_path": shared_note},
        {"date": old_day, "voice": "v1", "note_key": "k3", "audio_path": shared_note},
    ]

    orig_delete = store.delete
    orig_remove = store.remove_objects

    def partial_delete(table, params):
        # Fail deleting k3 in voice_notes so shared_note stays referenced!
        if table == "voice_notes" and params.get("note_key") == "eq.k3":
            raise RuntimeError("transient row lock")
        orig_delete(table, params)

    def flaky_remove(paths):
        # Fail deleting story_audio storage objects, succeed for voice_notes
        if any("already-missing" in p for p in paths):
            raise RuntimeError("storage delete error")
        orig_remove(paths)

    store.delete = partial_delete
    store.remove_objects = flaky_remove

    pruned_days = storypack.prune_older(
        store, keep="2020-01-05", keep_days=2, preserve_sections=["top_in"],
    )
    assert pruned_days == [old_day]
    # Static note and preserved section (DB + storage under stories/{old_day}) MUST remain untouched!
    assert static_path in store.objects
    assert preserved_story_path in store.objects
    assert len(store.select("story_audio", {"section": "eq.top_in"})) == 1
    # Failed k3 row kept shared_note alive even though k2 DB row deleted
    assert shared_note in store.objects
    assert len(store.select("voice_notes", {"note_key": "eq.k3"})) == 1
    # Succeeded k1 row deleted BOTH DB row and ok_note object
    assert ok_note not in store.objects
    assert len(store.select("voice_notes", {"note_key": "eq.k1"})) == 0
    # Unpreserved story_audio row deleted cleanly even when storage remove failed / file was missing
    assert len(store.select("story_audio", {"section": "eq.top"})) == 0


# --------------------------------------------------------------------------- Compatibility & circular imports

def test_extracted_modules_import_without_cycles_and_preserve_exports():
    import importlib
    import pkgutil
    import app
    from app import pack_ops, podcast, podcast_dialogue, podcast_prompts, podcast_text, showcase

    modules = [importlib.import_module(m.name) for m in pkgutil.walk_packages(app.__path__, "app.")]
    assert len(modules) >= 20

    # Key backward-compatible re-exports on app.podcast and app.storypack
    assert podcast.validate_turns is podcast_text.validate_turns
    assert podcast.SYSTEM_PROMPT is podcast_prompts.SYSTEM_PROMPT
    assert podcast.generate_story_dialogue is podcast_dialogue.generate_story_dialogue
    assert storypack.prune_older is pack_ops.prune_older
    assert storypack.publish_showcase is showcase.publish_showcase

