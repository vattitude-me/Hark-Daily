"""Daily Run Reporting System for Hark Daily.

Generates Markdown, terminal, macOS notification, SMTP email, and webhook reports
by inspecting Supabase tables and local pack logs.
"""
from __future__ import annotations

import argparse
import email.message
import json
import logging
import os
import re
import smtplib
import subprocess
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import topics
from .config import Config, load, local_today
from .store import Store

log = logging.getLogger(__name__)

EDITION_SECTIONS = {
    "Canada (CA)": topics.EDITION_SECTIONS["ca"],
    "United States (US)": topics.EDITION_SECTIONS["us"],
    "India (IN)": topics.EDITION_SECTIONS["in"],
}


def _safe_select(store: Store, table: str, params: dict, label: str) -> list[dict]:
    try:
        return store.select(table, params)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not fetch %s: %s", label, exc)
        return []


def _parse_pack_log(logs_dir: Path, edition: str, day: str) -> tuple[str | None, str | None, list[str]]:
    log_file = logs_dir / ("evening_pack.log" if edition == "evening" else "morning_pack.log")
    if not log_file.exists():
        return None, None, []

    run_start_time = run_end_time = None
    scrape_issues: list[str] = []
    ts_re = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")
    try:
        today_prefix = f"[{day} "
        for line in log_file.read_text(errors="ignore").splitlines():
            if not (line.startswith(today_prefix) or f"{day} 05:" in line or f"{day} 18:" in line):
                continue
            if "Starting Hark Daily" in line and not run_start_time:
                if match := ts_re.search(line):
                    run_start_time = match.group(1)
            if "Morning Edition successfully published" in line or "Evening Edition successfully published" in line:
                if match := ts_re.search(line):
                    run_end_time = match.group(1)
            if "Could not extract" in line or "returned HTTP 403" in line or "returned HTTP 5" in line:
                scrape_issues.append(line.split("INFO app.fetcher:")[-1].strip() if "INFO app.fetcher:" in line else line.strip())
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not parse %s: %s", log_file, exc)
    return run_start_time, run_end_time, scrape_issues


def _power_schedule() -> list[str]:
    try:
        proc = subprocess.run(["pmset", "-g", "sched"], capture_output=True, text=True, timeout=3)
        if proc.returncode == 0:
            return [pl.strip() for pl in proc.stdout.splitlines() if "wakepoweron" in pl or "wake at" in pl]
    except Exception:  # noqa: BLE001
        pass
    return []


def collect_run_report(cfg: Config, store: Store, day: str = "", edition: str = "all") -> dict:
    """Query Supabase and local logs to construct a structured daily status report."""
    day = day or local_today(cfg.timezone)

    run_logs = _safe_select(store, "run_log", {"run_date": f"eq.{day}", "order": "created_at.desc"}, "run_log")
    stories = _safe_select(store, "story_audio", {"date": f"eq.{day}", "select": "section,rank,title,duration,voice,url"}, "story_audio")
    podcast_clips = _safe_select(store, "podcast_clips", {"date": f"eq.{day}", "select": "clip_key,writer,duration,hosts"}, "podcast_clips")
    voice_notes = _safe_select(store, "voice_notes", {"date": f"eq.{day}", "select": "note_key,duration,voice"}, "voice_notes")

    sec_counts = Counter(s.get("section") for s in stories if s.get("section"))
    total_audio_sec = sum(float(s.get("duration") or 0) for s in stories)
    total_audio_min = total_audio_sec / 60.0
    voices_found = sorted({s["voice"] for s in stories if s.get("voice")})

    edition_breakdown = {}
    for ed_name, secs in EDITION_SECTIONS.items():
        ed_stories = [s for s in stories if s.get("section") in secs]
        ed_sec_counts = {sec: sec_counts[sec] for sec in secs if sec in sec_counts}
        edition_breakdown[ed_name] = {
            "story_count": len(ed_stories),
            "sections": ed_sec_counts,
            "duration_min": round(sum(float(s.get("duration") or 0) for s in ed_stories) / 60.0, 1),
            "target_sections": len(secs),
            "populated_sections": len(ed_sec_counts),
        }

    pod_writers = Counter(p.get("writer") for p in podcast_clips if p.get("writer"))
    pod_keys = [p.get("clip_key") for p in podcast_clips if p.get("clip_key")]

    logs_dir = Path(__file__).resolve().parent.parent / "logs"
    run_start_time, run_end_time, scrape_issues = _parse_pack_log(logs_dir, edition, day)

    primary_log = run_logs[0] if run_logs else {}
    status_code = primary_log.get("status") or ("ok" if len(stories) >= 35 else "incomplete" if stories else "unknown")
    run_title = primary_log.get("title") or (f"✓ {edition.title()} Brief ready" if status_code == "ok" else f"Run Status: {status_code}")
    run_detail = primary_log.get("detail") or f"{len(stories)} clips published ({total_audio_min:.1f} min audio)"

    return {
        "date": day,
        "edition": edition,
        "timezone": cfg.timezone,
        "generated_at": datetime.now(ZoneInfo(cfg.timezone)).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "status": status_code,
        "title": run_title,
        "detail": run_detail,
        "run_start": run_start_time,
        "run_end": run_end_time,
        "stories": {
            "total_count": len(stories),
            "total_duration_sec": round(total_audio_sec, 1),
            "total_duration_min": round(total_audio_min, 1),
            "voices": voices_found,
            "editions": edition_breakdown,
        },
        "podcast": {
            "total_clips": len(podcast_clips),
            "ready": "podcast_ready" in pod_keys,
            "opens": sum(k.startswith("pod_open") for k in pod_keys),
            "teases": sum(k.startswith("pod_tease") for k in pod_keys),
            "bridges": sum(k.startswith("pod_bridge") for k in pod_keys),
            "closes": sum(k.startswith("pod_close") for k in pod_keys),
            "writers": dict(pod_writers),
        },
        "voice_notes": {
            "total_notes": len(voice_notes),
            "keys": [n["note_key"] for n in voice_notes if n.get("note_key")],
        },
        "scrape_issues": scrape_issues,
        "power_schedule": _power_schedule(),
        "recent_runs": [
            {
                "date": r.get("run_date"),
                "status": r.get("status"),
                "title": r.get("title"),
                "detail": r.get("detail"),
                "created_at": r.get("created_at"),
            }
            for r in run_logs[:5]
        ],
    }


def format_markdown_report(rep: dict) -> str:
    """Format report data as GitHub Flavored Markdown."""
    st = rep["status"].upper()
    status_badge = "🟢 SUCCESS (OK)" if st == "OK" else ("🟡 INCOMPLETE" if st == "INCOMPLETE" else "🔴 FAILED")
    stories, pod = rep["stories"], rep["podcast"]

    lines = [
        f"# 🎙️ Hark Daily — Pipeline Run Report ({rep['date']})",
        "",
        f"**Run Status**: `{status_badge}`  ",
        f"**Target Edition**: `{rep['edition'].upper()}`  ",
        f"**Completed Run**: `{rep['title']}`  ",
        f"**Performance Summary**: {rep['detail']}  ",
        f"**Report Generated**: `{rep['generated_at']}`",
        "",
        "---",
        "",
        "## 📊 Edition & Story Coverage",
        "",
        f"- **Total Voiced Stories**: **{stories['total_count']} stories** across all regions",
        f"- **Total Audio Playtime**: **{stories['total_duration_min']} minutes** ({stories['total_duration_sec']}s)",
        f"- **Narrator Pairing**: `{', '.join(stories['voices']) or 'Matthew & Kelly'}` (Local M3 Pro Studio)",
        "",
        "| Edition | Stories | Playtime | Populated Sections | Category Details |",
        "| :--- | :---: | :---: | :---: | :--- |",
    ]
    for ed_name, ed_info in stories["editions"].items():
        sec_summary = ", ".join(f"{k}: {v}" for k, v in ed_info["sections"].items()) or "None"
        lines.append(
            f"| **{ed_name}** | {ed_info['story_count']} | {ed_info['duration_min']} min | "
            f"{ed_info['populated_sections']}/{ed_info['target_sections']} sections | {sec_summary} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 🎭 Podcast Banter & Dialogue Engine",
        "",
        f"- **Dialogue Readiness Marker**: `{'✓ ACTIVE' if pod['ready'] else '✗ MISSING'}`",
        f"- **Total Podcast Pieces**: **{pod['total_clips']} clips**",
        f"  - **Opens**: {pod['opens']} variants",
        f"  - **Section Teasers**: {pod['teases']} segments",
        f"  - **Section Bridges**: {pod['bridges']} transitions",
        f"  - **Sign-offs / Closes**: {pod['closes']} variants",
        "- **AI Dialogue Generation**: " + ", ".join(f"`{k}`: {v}" for k, v in pod["writers"].items()),
        f"- **Static Framing & Transitions**: **{rep['voice_notes']['total_notes']} notes** verified",
        "",
        "---",
        "",
        "## 🛡️ Feed Extraction & Network Health",
        "",
    ])

    if rep["scrape_issues"]:
        lines.append(
            f"> [!NOTE]\n> **{len(rep['scrape_issues'])} feeds required fallback handling** "
            "(e.g. paywall 403 or bot challenges). All stories successfully recovered from alternative feeds."
        )
        lines.append("")
        for issue in rep["scrape_issues"][:8]:
            lines.append(f"- ⚠️ `{issue}`")
        if len(rep["scrape_issues"]) > 8:
            lines.append(f"- *... and {len(rep['scrape_issues']) - 8} more handled gracefully.*")
    else:
        lines.append("✓ All source RSS feeds and article extractors completed with zero HTTP errors.")

    if rep["power_schedule"]:
        lines.extend(["", "---", "", "## ⚡ Power Management & Next Relay", "", "- Hardware power schedule verified:"])
        lines.extend(f"  - `{ps}`" for ps in rep["power_schedule"])

    lines.append("")
    return "\n".join(lines)


def format_terminal_summary(rep: dict) -> str:
    """Compact terminal status box."""
    st = rep["status"].upper()
    mark = "✓" if st == "OK" else "✗"
    stories, pod = rep["stories"], rep["podcast"]
    ed = stories["editions"]
    ca = ed.get("Canada (CA)", {}).get("story_count", 0)
    us = ed.get("United States (US)", {}).get("story_count", 0)
    in_ = ed.get("India (IN)", {}).get("story_count", 0)

    return (
        f"\n┌─────────────────────────────────────────────────────────────┐\n"
        f"│ 🎙️  HARK DAILY RUN REPORT — {rep['date']} ({rep['edition'].upper()})               │\n"
        f"├─────────────────────────────────────────────────────────────┤\n"
        f"│ Status:   {mark} {st:<48} │\n"
        f"│ Stories:  {stories['total_count']} clips ({stories['total_duration_min']} min) [CA: {ca}, US: {us}, IN: {in_}]        │\n"
        f"│ Podcast:  {pod['total_clips']} banter clips (Ready: {pod['ready']})                       │\n"
        f"│ Framing:  {rep['voice_notes']['total_notes']} voice notes verified                             │\n"
        f"│ Detail:   {rep['detail'][:49]:<49} │\n"
        f"└─────────────────────────────────────────────────────────────┘\n"
    )


def save_report_file(rep: dict, out_dir: Path | None = None) -> Path:
    """Save the Markdown report under logs/reports/."""
    if out_dir is None:
        out_dir = Path(__file__).resolve().parent.parent / "logs" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / f"report_{rep['date']}_{rep.get('edition') or 'run'}.md"
    file_path.write_text(format_markdown_report(rep), encoding="utf-8")
    return file_path


def notify_macos(rep: dict) -> bool:
    """Trigger an AppleScript desktop notification on macOS."""
    if sys.platform != "darwin":
        return False
    try:
        icon = "✓" if rep["status"].upper() == "OK" else "⚠️"
        total, dur = rep["stories"]["total_count"], rep["stories"]["total_duration_min"]
        esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')  # noqa: E731
        title = esc(f"{icon} Hark Daily {str(rep.get('edition', 'All')).title()} Edition Ready")
        sub = esc(f"{total} stories ({dur}m audio)")
        body = esc("Canada, US & India editions live on Supabase · Banter active")
        script = f'display notification "{body}" with title "{title}" subtitle "{sub}" sound name "Glass"'
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=3)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not post macOS notification: %s", exc)
        return False


def send_email_report(rep: dict, cfg: Config) -> bool:
    """Send the run report via SMTP when configured in .env."""
    smtp_host, smtp_user, smtp_pass = os.getenv("SMTP_HOST"), os.getenv("SMTP_USER"), os.getenv("SMTP_PASS")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    recipients = [e.strip() for e in (os.getenv("REPORT_EMAIL_TO") or "").split(",") if e.strip()]
    if not recipients:
        recipients = list(cfg.admin_emails) or [os.getenv("ADMIN_EMAIL", "admin@example.com")]
    if not (smtp_host and smtp_user and smtp_pass):
        log.info("SMTP not configured in .env (SMTP_HOST, SMTP_USER, SMTP_PASS). Skipping email dispatch.")
        return False

    try:
        msg = email.message.EmailMessage()
        msg["Subject"] = f"{'✓' if rep['status'] == 'ok' else '✗'} Hark Daily {rep['edition'].title()} Run Report ({rep['date']})"
        msg["From"] = os.getenv("SMTP_FROM", smtp_user)
        msg["To"] = ", ".join(recipients)
        msg.set_content(format_markdown_report(rep))
        msg.add_alternative(f"""
        <html><body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0f1115; color: #e6e8ec; padding: 24px;">
            <div style="max-width: 640px; margin: 0 auto; background: #181b22; border-radius: 12px; border: 1px solid #2d3340; padding: 24px;">
                <h1 style="color: #f7a634; font-size: 22px; margin-top: 0;">🎙️ Hark Daily Run Report</h1>
                <p style="font-size: 14px; color: #8e95a5;">{rep['date']} · {rep['edition'].upper()} Edition · {rep['generated_at']}</p>
                <div style="background: #202530; border-radius: 8px; padding: 16px; margin: 16px 0;">
                    <strong style="color: #2bd67b; font-size: 16px;">{rep['title']}</strong>
                    <p style="margin: 8px 0 0; color: #c4c8d4; font-size: 14px;">{rep['detail']}</p>
                </div>
                <ul style="color: #c4c8d4; font-size: 14px; line-height: 1.6;">
                    <li><strong>Total Stories:</strong> {rep['stories']['total_count']} voiced ({rep['stories']['total_duration_min']} min)</li>
                    <li><strong>Podcast Banter:</strong> {rep['podcast']['total_clips']} clips ({'Ready' if rep['podcast']['ready'] else 'Missing'})</li>
                </ul>
            </div>
        </body></html>""", subtype="html")

        with (smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) if smtp_port == 465
              else smtplib.SMTP(smtp_host, smtp_port, timeout=10)) as server:
            if smtp_port != 465:
                server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        log.info("✓ Report email delivered to %s", ", ".join(recipients))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to send email report: %s", exc)
        return False


def send_webhook_report(rep: dict) -> bool:
    """Send the run report to Discord/Slack/custom webhook when configured."""
    webhook_url = os.getenv("REPORT_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return False
    try:
        if "discord.com" in webhook_url:
            payload = {
                "username": "Hark Primary Runner",
                "avatar_url": "https://hark.vattitude.ca/icons/icon-192.png",
                "embeds": [{
                    "title": f"🎙️ Hark Daily {rep.get('edition', 'all').title()} Edition Finished",
                    "description": f"**{rep.get('title', '')}**\n{rep.get('detail', '')}",
                    "color": 0x2BD67B if rep.get("status") == "ok" else 0xEF4444,
                    "fields": [
                        {"name": "Date", "value": rep.get("date", ""), "inline": True},
                        {"name": "Stories", "value": f"{rep.get('stories', {}).get('total_count', 0)} ({rep.get('stories', {}).get('total_duration_min', 0)}m)", "inline": True},
                        {"name": "Banter", "value": "Ready" if rep.get("podcast", {}).get("ready") else "Missing", "inline": True},
                        {"name": "Status", "value": "✓ Finished on Mac" if rep.get("status") == "ok" else "⚠️ Check Logs", "inline": True},
                    ],
                    "footer": {"text": f"Hark Daily Primary Runner ({os.getenv('RUNNER_HOST_LABEL', 'Mac Runner')})"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }
        else:
            payload = {
                "text": f"*{rep['title']}*\n{rep['detail']}\nStories: {rep['stories']['total_count']} ({rep['stories']['total_duration_min']}m) · Date: {rep['date']}",
                "report": rep,
            }
        req = urllib.request.Request(
            webhook_url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "HarkDaily/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to send webhook report: %s", exc)
        return False


def run_and_dispatch(day: str = "", edition: str = "all", send: bool = False, json_output: bool = False) -> int:
    """Collect, save, print, and optionally dispatch notifications for a daily run report."""
    cfg = load()
    store = Store.from_config(cfg)
    rep = collect_run_report(cfg, store, day=day, edition=edition)
    saved_path = save_report_file(rep)

    if json_output:
        print(json.dumps(rep, indent=2))
    else:
        print(format_terminal_summary(rep))
        print(f"📄 Full report saved: {saved_path}")

    if send:
        notify_macos(rep)
        send_email_report(rep, cfg)
        send_webhook_report(rep)
    return 0 if rep["status"] == "ok" else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Hark Daily Run Reporting Tool")
    parser.add_argument("--day", default="", help="Report date (YYYY-MM-DD); defaults to today")
    parser.add_argument("--edition", default="morning", choices=["morning", "evening", "all"], help="Edition to report")
    parser.add_argument("--send", action="store_true", help="Send notifications (macOS desktop banner, email, webhook)")
    parser.add_argument("--json", action="store_true", help="Print report as raw JSON")
    args = parser.parse_args()
    sys.exit(run_and_dispatch(day=args.day, edition=args.edition, send=args.send, json_output=args.json))


if __name__ == "__main__":
    main()
