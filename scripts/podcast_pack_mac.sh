#!/usr/bin/env bash
# Hark Daily - voice the podcast banter locally on macOS (Apple Silicon MPS).
#
# Same local setup as evening_pack_mac.sh (no GCP, no cloud GPU), but runs only
# `pack --podcast-only`: it writes and voices the two hosts' banter for the stories
# already published today. Extra arguments are passed through (e.g. --force, --day).
set -euo pipefail

if [ -z "${CAFFEINATED:-}" ] && command -v caffeinate >/dev/null 2>&1; then
  export CAFFEINATED=1
  exec caffeinate -i -s -m "$0" "$@"
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$ROOT/logs/podcast_pack.log"
SERVICE_LOG="$ROOT/logs/voice_service_podcast.log"
mkdir -p "$ROOT/logs"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

if [ -f "$ROOT/.env" ]; then
  set -a
  source "$ROOT/.env"
  set +a
fi

# Strict local overrides: never touch GCP.
export GCE_MANAGE_VM="false"
export GCE_INSTANCE=""
export GCP_PROJECT=""
export VOICE_SERVICE_URL="http://127.0.0.1:8090"
export VOICE_DIR="$ROOT/voice_service/data/voices"
export PRELOAD_VOICE="1"
export PODCAST_ENABLED="true"

log "Starting local Chatterbox-Turbo voice service (Apple Silicon MPS)..."
cd "$ROOT/voice_service"
.venv/bin/uvicorn api.app:app --host 127.0.0.1 --port 8090 > "$SERVICE_LOG" 2>&1 &
VOICE_PID=$!

cleanup() {
  log "Shutting down local voice service (PID: $VOICE_PID)..."
  kill "$VOICE_PID" 2>/dev/null || true
  wait "$VOICE_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

HEALTHY=0
for i in $(seq 1 120); do
  if curl -s --connect-timeout 2 http://127.0.0.1:8090/health | grep -q '"device"'; then
    HEALTHY=1
    log "Local voice service ready (${i}s)"
    break
  fi
  sleep 1
done
if [ "$HEALTHY" -ne 1 ]; then
  log "ERROR: local voice service did not become healthy."
  tail -n 30 "$SERVICE_LOG" >> "$LOG_FILE"
  exit 1
fi

cd "$ROOT"
log "Voicing podcast banter..."
"$ROOT/.venv/bin/python" -m app pack --podcast-only "$@" 2>&1 | tee -a "$LOG_FILE"
log "Done."
