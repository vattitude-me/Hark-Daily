#!/usr/bin/env bash
# Hark Daily - Standalone Evening Edition Runner for macOS (Apple Silicon MPS)
#
# Runs entirely locally on your Mac using the M3 Pro GPU (Metal Performance Shaders).
# Zero GCP components, zero cloud GPU billing, 100% free.
# Pushes the evening edition audio and metadata directly to Supabase.

set -euo pipefail

# Ensure the Mac stays awake while running, even with the lid closed on AC power
if [ -z "${CAFFEINATED:-}" ] && command -v caffeinate >/dev/null 2>&1; then
  export CAFFEINATED=1
  exec caffeinate -i -s -m "$0" "$@"
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$ROOT/logs/evening_pack.log"
SERVICE_LOG="$ROOT/logs/voice_service_evening.log"

mkdir -p "$ROOT/logs"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "============================================================"
log "Starting Hark Daily Evening Edition on macOS (Local M3 Pro)"
log "============================================================"

# Load project .env if present
if [ -f "$ROOT/.env" ]; then
  set -a
  source "$ROOT/.env"
  set +a
fi

# Strict local overrides: NEVER touch GCP
export GCE_MANAGE_VM="false"
export GCE_INSTANCE=""
export GCP_PROJECT=""
export VOICE_SERVICE_URL="http://127.0.0.1:8090"
export VOICE_DIR="$ROOT/voice_service/data/voices"
export PRELOAD_VOICE="1"
export PODCAST_ENABLED="true"
export PODCAST_HOSTS="matthew_reference,kelly_reference"
export STORY_VOICE="matthew_reference+kelly_reference"
export STORY_VOICES="matthew_reference+kelly_reference"
export VOICE_PACE="0.94"
export VOICE_TEMPERATURE="0.90"
export VOICE_TOP_P="0.98"
export VOICE_EXAGGERATION="0.75"

# Start the local voice service using Apple Silicon MPS
log "Starting local Chatterbox-Turbo voice service on Apple Silicon MPS..."
cd "$ROOT/voice_service"
.venv/bin/uvicorn api.app:app --host 127.0.0.1 --port 8090 > "$SERVICE_LOG" 2>&1 &
VOICE_PID=$!

cleanup() {
  log "Shutting down local voice service (PID: $VOICE_PID)..."
  kill "$VOICE_PID" 2>/dev/null || true
  wait "$VOICE_PID" 2>/dev/null || true
  log "Voice service stopped."
}
trap cleanup EXIT INT TERM

# Wait for local voice service to report healthy
log "Waiting for local voice service at http://127.0.0.1:8090/health..."
HEALTHY=0
for i in $(seq 1 45); do
  if curl -s --connect-timeout 2 http://127.0.0.1:8090/health | grep -q '"device"'; then
    HEALTHY=1
    log "✓ Local voice service is online and ready (took ${i}s)!"
    break
  fi
  sleep 1
done

if [ "$HEALTHY" -ne 1 ]; then
  log "ERROR: Local voice service failed to report healthy within 45s."
  cat "$SERVICE_LOG" | tail -n 30 >> "$LOG_FILE"
  exit 1
fi

# Run the storypack generation pipeline and push to Supabase
# Evening edition voices India (timed for IST morning), reusing today's shared AI, Tech, and Science
cd "$ROOT"
log "Running briefing pack generation for India edition (voicing on M3 Pro, pushing to Supabase)..."
"$ROOT/.venv/bin/python" -m app pack --edition in --notify "${@:---force}" >> "$LOG_FILE" 2>&1

log "✓ Evening Edition successfully published to Supabase!"

# Option B Relay: Re-affirm tomorrow's morning edition wake event (04:58)
if [ -x "$ROOT/scripts/schedule_wake.sh" ]; then
  "$ROOT/scripts/schedule_wake.sh" morning 2>&1 | tee -a "$LOG_FILE" || true
fi

log "============================================================"
