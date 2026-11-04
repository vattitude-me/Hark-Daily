#!/usr/bin/env python3
"""Hark Daily — 24/7 NAS Watchdog Sentinel & Disaster Recovery Alert.

Runs on the always-on NAS (10.0.0.233). Operates as an independent Dead Man's Switch:
Checks Supabase at 05:45 AM (morning) and 18:45 PM (evening) to verify whether
the day's audio pack was successfully published by the primary Mac (10.0.0.15).

If Healthy: Sends a clean green run summary to your phone (Discord, Telegram, WhatsApp).
If Missing: Pings Mac, detects sleep/crash, and fires an IMMEDIATE RED DR ALERT.

Usage:
    python3 hark_sentinel.py --edition morning
    python3 hark_sentinel.py --edition evening
    python3 hark_sentinel.py --test
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
log = logging.getLogger("sentinel")

# Default configurations (can be overridden by environment variables)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://qfmsqhlwvyvnhxecfvpy.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")
MAC_IP = os.getenv("MAC_IP", "10.0.0.15")
TIMEZONE = os.getenv("TIMEZONE", "America/Toronto")
ADMIN_URL = os.getenv("ADMIN_URL", "https://hark.vattitude.ca/")

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def get_today_str() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()


def ping_mac(ip: str = MAC_IP) -> bool:
    """Returns True if Mac responds to ping on the local network."""
    try:
        res = subprocess.run(["ping", "-c", "2", "-W", "2", ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0
    except Exception:
        return False


def query_supabase_pack(day: str) -> dict:
    """Queries Supabase REST API for today's story and podcast audio status."""
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    status = {"stories_count": 0, "total_duration_sec": 0, "podcast_ready": False, "regions": set()}

    if not SUPABASE_KEY:
        log.warning("SUPABASE_KEY not provided. Skipping direct Supabase query.")
        return status

    # 1. Query stories
    try:
        url = f"{SUPABASE_URL}/rest/v1/story_audio?date=eq.{day}&select=section,duration,voice"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            status["stories_count"] = len(data)
            status["total_duration_sec"] = sum(float(r.get("duration") or 0) for r in data)
            for r in data:
                sec = r.get("section") or ""
                if sec.endswith("_us"):
                    status["regions"].add("US")
                elif sec.endswith("_in"):
                    status["regions"].add("India")
                else:
                    status["regions"].add("Canada")
    except Exception as exc:
        log.warning("Failed to query stories from Supabase: %s", exc)

    # 2. Query podcast ready marker
    try:
        url = f"{SUPABASE_URL}/rest/v1/podcast_clips?date=eq.{day}&clip_key=eq.podcast_ready"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            status["podcast_ready"] = len(data) > 0
    except Exception as exc:
        log.warning("Failed to query podcast clips from Supabase: %s", exc)

    return status


def send_discord(title: str, description: str, color: int, fields: list[dict] | None = None) -> bool:
    """Sends a rich embed alert to Discord."""
    if not DISCORD_WEBHOOK:
        return False
    payload = {
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color,  # 0x2bd67b (green) or 0xef4444 (red)
                "fields": fields or [],
                "footer": {"text": "Hark Daily 24/7 NAS Sentinel (10.0.0.233)"},
                "timestamp": datetime.now(ZoneInfo(TIMEZONE)).isoformat(),
            }
        ]
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(DISCORD_WEBHOOK, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)
    except Exception as exc:
        log.error("Failed to send Discord alert: %s", exc)
        return False


def send_telegram(text: str) -> bool:
    """Sends a message via Telegram Bot."""
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as exc:
        log.error("Failed to send Telegram alert: %s", exc)
        return False


def dispatch_notification(healthy: bool, title: str, description: str, fields: list[dict]) -> None:
    """Dispatches to all configured channels (Discord / Telegram)."""
    color = 0x2BD67B if healthy else 0xEF4444

    # Discord Dispatch
    if DISCORD_WEBHOOK:
        send_discord(title, description, color, fields)
        log.info("✓ Dispatched to Discord")

    # Telegram Dispatch
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        tg_text = f"*{title}*\n\n{description}\n\n"
        for f in fields:
            tg_text += f"• *{f['name']}*: {f['value']}\n"
        send_telegram(tg_text)
        log.info("✓ Dispatched to Telegram")


def check_and_alert(edition: str = "morning") -> int:
    today = get_today_str()
    log.info("Running Sentinel check for %s edition (%s)...", edition, today)

    pack = query_supabase_pack(today)
    is_healthy = pack["stories_count"] > 0

    if is_healthy:
        mins = round(pack["total_duration_sec"] / 60.0, 1)
        regions_str = ", ".join(sorted(pack["regions"])) or "All"
        banter_str = "Duo Banter Live" if pack["podcast_ready"] else "Mono/Standard"

        title = f"✅ Hark Daily {edition.title()} Run Complete"
        desc = f"Today's {edition} briefing pack is live and ready for listeners."
        fields = [
            {"name": "Date", "value": today, "inline": True},
            {"name": "Stories", "value": f"{pack['stories_count']} voiced ({mins}m)", "inline": True},
            {"name": "Banter", "value": banter_str, "inline": True},
            {"name": "Editions", "value": regions_str, "inline": True},
            {"name": "Status", "value": "🟢 All Systems Nominal", "inline": True},
            {"name": "Admin Mission Control", "value": f"[Open Mission Control]({ADMIN_URL})", "inline": False},
        ]
        dispatch_notification(True, title, desc, fields)
        log.info("Run confirmed healthy.")
        return 0

    # FAILURE / DR EVENT
    mac_online = ping_mac()
    mac_status = "Online (Pingable)" if mac_online else "OFFLINE / Sleeping / Unreachable"

    title = f"🚨 DR ALERT: {edition.title()} Pack Missing!"
    desc = f"By scheduled cutoff time, today's {edition} edition was **not published** to Supabase."
    fields = [
        {"name": "Target Date", "value": today, "inline": True},
        {"name": "Mac Status (10.0.0.15)", "value": f"**{mac_status}**", "inline": True},
        {"name": "Diagnosis", "value": "Mac went to sleep or generation halted midway" if mac_online else "Mac is powered off or sleeping with lid closed", "inline": False},
        {"name": "Required Action", "value": f"1. Wake Mac / check logs\n2. Or trigger [Safe Rebuild via Admin Console]({ADMIN_URL})", "inline": False},
    ]
    dispatch_notification(False, title, desc, fields)
    log.error("Run failed! DR Alert dispatched.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Hark Daily 24/7 NAS Sentinel Watchdog")
    parser.add_argument("--edition", choices=["morning", "evening"], default="morning", help="Edition to check")
    parser.add_argument("--test", action="store_true", help="Send a test notification to verify webhook/bot")
    args = parser.parse_args()

    if args.test:
        log.info("Sending test notification...")
        fields = [
            {"name": "Host", "value": "NAS (10.0.0.233)", "inline": True},
            {"name": "Mac Target", "value": f"{MAC_IP} ({'Up' if ping_mac() else 'Unreachable'})", "inline": True},
            {"name": "Status", "value": "Sentinel Watchdog Connected", "inline": True},
        ]
        dispatch_notification(True, "🛡️ Hark Sentinel Watchdog Test", "Your 24/7 NAS monitoring alert channel is active and functioning.", fields)
        print("✓ Test notification dispatched.")
        return 0

    return check_and_alert(args.edition)


if __name__ == "__main__":
    sys.exit(main())
