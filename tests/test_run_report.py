import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.config import Config
from app.run_report import (
    collect_run_report,
    format_markdown_report,
    format_terminal_summary,
    local_today,
    notify_macos,
    run_and_dispatch,
    save_report_file,
    send_email_report,
    send_webhook_report,
)


def test_local_today():
    today = local_today("America/Toronto")
    assert len(today.split("-")) == 3
    assert today.startswith("202")


def test_collect_run_report_mocked():
    store = MagicMock()
    store.select.side_effect = lambda table, params: {
        "run_log": [
            {
                "run_date": "2026-11-03",
                "status": "ok",
                "title": "✓ Morning Brief ready: Matthew & Kelly",
                "detail": "Took 24m 26s · 85 clips (27.9 min audio)",
                "created_at": "2026-11-03T10:24:30Z",
            }
        ],
        "story_audio": [
            {"section": "top", "rank": 1, "duration": 18.0, "voice": "matthew_reference+kelly_reference"},
            {"section": "ai", "rank": 1, "duration": 22.0, "voice": "matthew_reference+kelly_reference"},
            {"section": "top_us", "rank": 1, "duration": 20.0, "voice": "matthew_reference+kelly_reference"},
            {"section": "top_in", "rank": 1, "duration": 19.0, "voice": "matthew_reference+kelly_reference"},
        ],
        "podcast_clips": [
            {"clip_key": "pod_open_1", "writer": "openai/gpt-oss-120b", "duration": 8.0},
            {"clip_key": "pod_tease_top", "writer": "openai/gpt-oss-120b", "duration": 9.0},
            {"clip_key": "pod_bridge_top", "writer": "built-in", "duration": 2.5},
            {"clip_key": "pod_close_1", "writer": "openai/gpt-oss-120b", "duration": 6.0},
            {"clip_key": "podcast_ready", "writer": "marker", "duration": 0.0},
        ],
        "voice_notes": [
            {"note_key": "greeting_morning", "duration": 1.0, "voice": "matthew_reference+kelly_reference"},
            {"note_key": "intro_top", "duration": 1.5, "voice": "matthew_reference+kelly_reference"},
        ],
    }.get(table, [])

    cfg = Config()
    rep = collect_run_report(cfg, store, day="2026-11-03", edition="morning")

    assert rep["date"] == "2026-11-03"
    assert rep["status"] == "ok"
    assert rep["stories"]["total_count"] == 4
    assert rep["podcast"]["total_clips"] == 5
    assert rep["podcast"]["ready"] is True
    assert rep["voice_notes"]["total_notes"] == 2
    assert "Canada (CA)" in rep["stories"]["editions"]
    assert rep["stories"]["editions"]["Canada (CA)"]["story_count"] == 2


def test_format_markdown_report():
    sample_rep = {
        "date": "2026-11-03",
        "edition": "morning",
        "status": "ok",
        "title": "✓ Morning Brief ready: Matthew & Kelly",
        "detail": "Took 24m 26s · 85 clips (27.9 min audio)",
        "generated_at": "2026-11-03 07:00:00 EST",
        "stories": {
            "total_count": 85,
            "total_duration_sec": 1673.3,
            "total_duration_min": 27.9,
            "voices": ["matthew_reference+kelly_reference"],
            "editions": {
                "Canada (CA)": {"story_count": 35, "duration_min": 11.9, "populated_sections": 7, "target_sections": 7, "sections": {"top": 5}},
                "United States (US)": {"story_count": 25, "duration_min": 8.0, "populated_sections": 5, "target_sections": 5, "sections": {"top_us": 5}},
                "India (IN)": {"story_count": 25, "duration_min": 8.0, "populated_sections": 5, "target_sections": 5, "sections": {"top_in": 5}},
            },
        },
        "podcast": {
            "total_clips": 40,
            "ready": True,
            "opens": 3,
            "teases": 17,
            "bridges": 17,
            "closes": 2,
            "writers": {"openai/gpt-oss-120b": 19, "built-in": 20},
        },
        "voice_notes": {"total_notes": 12, "keys": ["greeting_morning"]},
        "scrape_issues": ["Could not extract https://example.com: HTTP 403"],
        "power_schedule": ["wakepoweron at 4:58AM every day"],
    }

    md = format_markdown_report(sample_rep)
    assert "# 🎙️ Hark Daily — Pipeline Run Report (2026-11-03)" in md
    assert "SUCCESS (OK)" in md
    assert "Total Voiced Stories" in md
    assert "85 stories" in md
    assert "Podcast Banter & Dialogue Engine" in md
    assert "Feed Extraction & Network Health" in md
    assert "HTTP 403" in md


def test_format_terminal_summary():
    sample_rep = {
        "date": "2026-11-03",
        "edition": "morning",
        "status": "ok",
        "title": "✓ Morning Brief ready",
        "detail": "Took 24m 26s · 85 clips",
        "stories": {
            "total_count": 85,
            "total_duration_min": 27.9,
            "editions": {
                "Canada (CA)": {"story_count": 35},
                "United States (US)": {"story_count": 25},
                "India (IN)": {"story_count": 25},
            },
        },
        "podcast": {"total_clips": 40, "ready": True},
        "voice_notes": {"total_notes": 12},
    }

    term = format_terminal_summary(sample_rep)
    assert "HARK DAILY RUN REPORT — 2026-11-03 (MORNING)" in term
    assert "Status:   ✓ OK" in term
    assert "85 clips (27.9 min) [CA: 35, US: 25, IN: 25]" in term


def test_save_report_file(tmp_path):
    sample_rep = {
        "date": "2026-11-03",
        "edition": "morning",
        "status": "ok",
        "title": "✓ Morning Brief ready",
        "detail": "Took 24m 26s",
        "generated_at": "2026-11-03 07:00:00 EST",
        "stories": {
            "total_count": 85,
            "total_duration_sec": 1673.3,
            "total_duration_min": 27.9,
            "voices": ["matthew_reference+kelly_reference"],
            "editions": {},
        },
        "podcast": {"total_clips": 40, "ready": True, "opens": 3, "teases": 17, "bridges": 17, "closes": 2, "writers": {}},
        "voice_notes": {"total_notes": 12, "keys": []},
        "scrape_issues": [],
        "power_schedule": [],
    }

    path = save_report_file(sample_rep, out_dir=tmp_path)
    assert path.exists()
    assert path.name == "report_2026-11-03_morning.md"
    content = path.read_text(encoding="utf-8")
    assert "Hark Daily" in content


@patch("subprocess.run")
def test_notify_macos(mock_run):
    sample_rep = {
        "status": "ok",
        "edition": "morning",
        "stories": {"total_count": 85, "total_duration_min": 27.9},
    }
    with patch("sys.platform", "darwin"):
        ok = notify_macos(sample_rep)
        assert ok is True
        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert "display notification" in args[2]


@patch("smtplib.SMTP")
def test_send_email_report(mock_smtp, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")
    monkeypatch.setenv("REPORT_EMAIL_TO", "admin@example.com")

    sample_rep = {
        "date": "2026-11-03",
        "edition": "morning",
        "status": "ok",
        "title": "✓ Morning Brief ready",
        "detail": "Took 24m 26s",
        "generated_at": "2026-11-03 07:00:00 EST",
        "stories": {
            "total_count": 85,
            "total_duration_sec": 1673.3,
            "total_duration_min": 27.9,
            "voices": [],
            "editions": {},
        },
        "podcast": {"total_clips": 40, "ready": True, "opens": 3, "teases": 17, "bridges": 17, "closes": 2, "writers": {}},
        "voice_notes": {"total_notes": 12, "keys": []},
        "scrape_issues": [],
        "power_schedule": [],
    }

    cfg = Config()
    sent = send_email_report(sample_rep, cfg)
    assert sent is True
    assert mock_smtp.called
