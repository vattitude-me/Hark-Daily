#!/usr/bin/env bash
# Hark Daily - Power Schedule Relay Manager for macOS
# Manages wake-from-sleep hardware timers so the Mac wakes up on AC power
# with lid closed for both Morning (06:00) and Evening (18:00) editions.
set -euo pipefail

TARGET="${1:-next}"

case "$TARGET" in
  evening)
    NOW_HOUR=$(date '+%H')
    if [ "$NOW_HOUR" -lt 18 ]; then
      WAKE_TIME="$(date '+%m/%d/%y 17:58:00')"
    else
      WAKE_TIME="$(date -v+1d '+%m/%d/%y 17:58:00')"
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Scheduling Evening wake at $WAKE_TIME..."
    if sudo -n true 2>/dev/null; then
      sudo pmset schedule wake "$WAKE_TIME"
      echo "✓ Evening wake event successfully scheduled."
    else
      echo "Notice: sudo pmset requires password or /etc/sudoers.d/hark_pmset rule."
      exit 1
    fi
    ;;

  morning)
    NOW_HOUR=$(date '+%H')
    if [ "$NOW_HOUR" -lt 6 ]; then
      WAKE_TIME="$(date '+%m/%d/%y 05:58:00')"
    else
      WAKE_TIME="$(date -v+1d '+%m/%d/%y 05:58:00')"
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Scheduling Morning wake at $WAKE_TIME..."
    if sudo -n true 2>/dev/null; then
      sudo pmset schedule wake "$WAKE_TIME"
      echo "✓ Morning wake event successfully scheduled."
    else
      echo "Notice: sudo pmset requires password or /etc/sudoers.d/hark_pmset rule."
      exit 1
    fi
    ;;

  status)
    pmset -g sched
    ;;

  next)
    NOW_HOUR=$(date '+%H')
    if [ "$NOW_HOUR" -ge 6 ] && [ "$NOW_HOUR" -lt 18 ]; then
      exec "$0" evening
    else
      exec "$0" morning
    fi
    ;;

  *)
    echo "Usage: $0 [evening|morning|next|status]"
    exit 1
    ;;
esac
