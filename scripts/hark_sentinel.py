#!/usr/bin/env python3
"""Hark Daily — 24/7 Sentinel Watchdog & Disaster Recovery Alert.

Runs on an independent watchdog host. Operates as an independent Dead Man's Switch:
Checks Supabase at 05:45 AM (morning) and 18:45 PM (evening) to verify whether
the day's audio pack was successfully published by the primary runner.

If Healthy: Sends a clean green run summary card to Discord.
If Missing: Pings Mac, sends Wake-on-LAN magic packet, and fires an IMMEDIATE RED DR ALERT.

Usage:
    python3 hark_sentinel.py --edition morning
    python3 hark_sentinel.py --edition evening
    python3 hark_sentinel.py --test
    python3 hark_sentinel.py --wol
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
log = logging.getLogger("sentinel")

# Load .env if present in same directory or parent
for candidate in (Path(__file__).parent / ".env", Path(__file__).resolve().parent.parent / ".env"):
    if candidate.exists():
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        break

# Target configurations
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://oohbmeffdncyzujmeqcz.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
MAC_IP = os.getenv("MAC_IP", "127.0.0.1")
MAC_HW_ADDR = os.getenv("MAC_HW_ADDR", "")
BROADCAST_IP = os.getenv("BROADCAST_IP", "255.255.255.255")
TIMEZONE = os.getenv("TIMEZONE", "America/Toronto")
EVENING_RUN_PAUSED = os.getenv("EVENING_RUN_PAUSED", "true").lower() in ("true", "1", "yes")

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL") or os.getenv("REPORT_WEBHOOK_URL", "")


def get_today_str() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()


def ping_mac(ip: str = MAC_IP) -> bool:
    """Returns True if Mac responds to ping on the local network."""
    try:
        res = subprocess.run(["ping", "-c", "2", "-W", "2", ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0
    except Exception:
        return False


def send_magic_packet(mac: str = MAC_HW_ADDR, broadcast: str = BROADCAST_IP, port: int = 9) -> bool:
    """Sends a Wake-on-LAN magic packet over the local broadcast address to wake the Mac."""
    try:
        mac_clean = mac.replace(":", "").replace("-", "")
        if len(mac_clean) != 12:
            log.warning("Invalid MAC address length for WoL: %s", mac)
            return False
        mac_bytes = bytes.fromhex(mac_clean)
        payload = b"\xff" * 6 + mac_bytes * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(payload, (broadcast, port))
        log.info("✓ Wake-on-LAN magic packet sent to %s via %s:%d", mac, broadcast, port)
        return True
    except Exception as exc:
        log.warning("Failed to send WoL magic packet: %s", exc)
        return False


def _supabase_get(path_query: str, headers: dict[str, str]) -> list[dict]:
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{path_query}", headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


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

    try:
        data = _supabase_get(f"story_audio?date=eq.{day}&select=section,duration,voice", headers)
        status["stories_count"] = len(data)
        status["total_duration_sec"] = sum(float(r.get("duration") or 0) for r in data)
        for r in data:
            sec = r.get("section") or ""
            status["regions"].add("US" if sec.endswith("_us") else ("India" if sec.endswith("_in") else "Canada"))
    except Exception as exc:
        log.warning("Failed to query stories from Supabase: %s", exc)

    try:
        data = _supabase_get(f"podcast_clips?date=eq.{day}&clip_key=eq.podcast_ready", headers)
        status["podcast_ready"] = len(data) > 0
    except Exception as exc:
        log.warning("Failed to query podcast clips from Supabase: %s", exc)

    return status


def send_discord(title: str, description: str, color: int, fields: list[dict] | None = None) -> bool:
    """Sends a rich embed alert to Discord."""
    webhook = DISCORD_WEBHOOK
    if not webhook:
        log.warning("No Discord Webhook configured. Alert skipped.")
        return False

    payload = {
        "username": "Hark Sentinel",
        "avatar_url": "https://hark.vattitude.ca/icons/icon-192.png",
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color,  # 0x2bd67b (green) or 0xef4444 (red)
                "fields": fields or [],
                "footer": {"text": "24/7 Watchdog Sentinel • Hark Daily"},
                "timestamp": datetime.now(ZoneInfo(TIMEZONE)).isoformat(),
            }
        ]
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(webhook, data=data, headers={"Content-Type": "application/json", "User-Agent": "HarkSentinel/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)
    except Exception as exc:
        log.error("Failed to send Discord alert: %s", exc)
        return False


def check_evening_health(day: str | None = None) -> int:
    """Runs a lightweight evening health check when the evening audio run is paused."""
    if not day:
        day = get_today_str()
    log.info("Running Sentinel Evening Health Check (%s)...", day)

    pack = query_supabase_pack(day)
    supabase_ok = pack["stories_count"] > 0
    mac_online = ping_mac()
    mac_status = "🟢 Online" if mac_online else "💤 Standby / Sleep (Next wake ~04:58 AM)"

    mins = round(pack["total_duration_sec"] / 60.0, 1)
    regions_str = ", ".join(sorted(pack["regions"])) or "All"
    daily_pack_str = f"{pack['stories_count']} voiced ({mins}m) · {regions_str}" if supabase_ok else "No stories found today"

    title = "🌙 Hark Daily — Evening Health Check"
    desc = "Evening audio run is paused (morning-only schedule active). Service health verified."
    fields = [
        {"name": "Date", "value": day, "inline": True},
        {"name": "Supabase Status", "value": "🟢 Connected & Serving" if supabase_ok else "⚠️ No Stories Found", "inline": True},
        {"name": "Daily Pack", "value": daily_pack_str, "inline": True},
        {"name": "Mac Producer", "value": f"{mac_status} ({MAC_IP})", "inline": True},
        {"name": "Schedule", "value": "Morning-only • Next run 05:00 AM", "inline": True},
        {"name": "Watchdog Host", "value": os.getenv("WATCHDOG_HOST_LABEL", "Ubuntu Sentinel"), "inline": True},
    ]

    # Calm twilight blue (0x58A6FF) or alert amber if Supabase has zero stories
    color = 0x58A6FF if supabase_ok else 0xE67E22
    send_discord(title, desc, color, fields)
    log.info("Evening health check dispatched to Discord.")
    return 0 if supabase_ok else 1


def check_and_alert(edition: str = "morning") -> int:
    today = get_today_str()
    log.info("Running Sentinel check for %s edition (%s)...", edition, today)

    # If edition is evening and evening run is paused, run the simpler health check
    if edition in ("evening", "health"):
        if edition == "health" or EVENING_RUN_PAUSED:
            return check_evening_health(today)

    pack = query_supabase_pack(today)
    is_healthy = pack["stories_count"] > 0

    if is_healthy:
        mins = round(pack["total_duration_sec"] / 60.0, 1)
        regions_str = ", ".join(sorted(pack["regions"])) or "All"
        banter_str = "Duo Banter Live" if pack["podcast_ready"] else "Mono/Standard"

        title = f"🎙️ Hark Daily — {edition.title()} Run Complete"
        desc = f"Today's {edition} briefing pack is live and verified in Supabase."
        fields = [
            {"name": "Date", "value": today, "inline": True},
            {"name": "Stories", "value": f"{pack['stories_count']} voiced ({mins}m)", "inline": True},
            {"name": "Banter", "value": banter_str, "inline": True},
            {"name": "Editions", "value": regions_str, "inline": True},
            {"name": "Producer", "value": f"Mac ({MAC_IP})", "inline": True},
            {"name": "Status", "value": "🟢 All Systems Nominal", "inline": True},
        ]
        send_discord(title, desc, 0x2BD67B, fields)
        log.info("Run confirmed healthy and green report dispatched.")
        return 0

    # FAILURE / DR EVENT
    mac_online = ping_mac()
    mac_status = "Online (Pingable, but pack stalled)" if mac_online else "OFFLINE / Sleeping / Unreachable"

    # Level 1 DR: Attempt Wake-on-LAN if Mac is sleeping/offline
    wol_attempted = False
    if not mac_online:
        wol_attempted = send_magic_packet()

    title = f"🚨 DR ALERT: {edition.title()} Pack Not Published!"
    desc = f"By scheduled cutoff time, today's {edition} edition was **not published** to Supabase."
    fields = [
        {"name": "Target Date", "value": today, "inline": True},
        {"name": "Mac Status", "value": f"**{mac_status}** ({MAC_IP})", "inline": True},
        {"name": "Automated DR Action", "value": "✓ Sent Wake-on-LAN magic packet to wake Mac" if wol_attempted else "Mac is pingable; pack may have encountered an error midway", "inline": False},
        {"name": "Manual Investigation", "value": f"Please wake Mac ({MAC_IP}) or inspect `logs/{edition}_pack.log`", "inline": False},
    ]
    send_discord(title, desc, 0xEF4444, fields)
    log.error("Run failed! DR Alert dispatched.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Hark Daily 24/7 NAS Sentinel Watchdog")
    parser.add_argument("--edition", choices=["morning", "evening", "health"], default="morning", help="Edition or check type")
    parser.add_argument("--test", action="store_true", help="Send a test notification to verify Discord webhook")
    parser.add_argument("--wol", action="store_true", help="Send a test Wake-on-LAN packet to the Mac")
    parser.add_argument("--webhook", help="Override Discord Webhook URL for testing")
    args = parser.parse_args()

    global DISCORD_WEBHOOK
    if args.webhook:
        DISCORD_WEBHOOK = args.webhook

    if args.wol:
        send_magic_packet()
        print("✓ WoL magic packet sent to Mac.")
        return 0

    if args.test:
        log.info("Sending test notification to Discord...")
        mac_up = ping_mac()
        fields = [
            {"name": "Watchdog Host", "value": os.getenv("WATCHDOG_HOST_LABEL", "Ubuntu Sentinel"), "inline": True},
            {"name": "Mac Ping Status", "value": f"{MAC_IP} ({'🟢 Online' if mac_up else '🔴 Offline'})", "inline": True},
            {"name": "Wake-on-LAN Target", "value": f"{MAC_HW_ADDR}", "inline": True},
            {"name": "Status", "value": "🛡️ Sentinel Connected", "inline": True},
        ]
        ok = send_discord("🛡️ Hark Sentinel Watchdog Test", "Your 24/7 NAS monitoring alert channel is active and functioning.", 0x58A6FF, fields)
        if ok:
            print("✓ Test notification delivered to Discord successfully!")
            return 0
        else:
            print("✗ Failed to deliver. Did you set DISCORD_WEBHOOK_URL?")
            return 1

    return check_and_alert(args.edition)


if __name__ == "__main__":
    sys.exit(main())
