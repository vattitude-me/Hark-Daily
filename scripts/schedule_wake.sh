#!/usr/bin/env bash
# Hark Daily - Power Schedule Relay Manager for macOS
# Manages wake-from-sleep hardware timers so the Mac wakes up on AC power
# with lid closed for both Morning (05:00) and Evening (18:00) editions.
set -euo pipefail

TARGET="${1:-next}"

case "$TARGET" in
  evening)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Evening batch is currently paused; keeping morning-only schedule."
    exit 0
    ;;

  morning)
    NOW_HOUR=$(date '+%H')
    if [ "$NOW_HOUR" -lt 5 ]; then
      WAKE_TIME="$(date '+%m/%d/%y 04:58:00')"
    else
      WAKE_TIME="$(date -v+1d '+%m/%d/%y 04:58:00')"
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Scheduling Morning wake at $WAKE_TIME..."
    if sudo -n /usr/bin/pmset schedule wake "$WAKE_TIME" 2>/dev/null; then
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
    # Evening batch paused: keep only morning schedule
    exec "$0" morning
    ;;

  *)
    echo "Usage: $0 [evening|morning|next|status]"
    exit 1
    ;;
esac
