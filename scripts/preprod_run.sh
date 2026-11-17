#!/usr/bin/env bash
# Safe runner for Hark Daily Pre-Prod / Dev tasks against standalone Supabase (hhcygubulddewtwkedkz).
#
# Usage:
#   ./scripts/preprod_run.sh web [port]       # Serve web/ on http://localhost:3000 (auto-targets Pre-prod)
#   ./scripts/preprod_run.sh check            # Verify Pre-prod Supabase + AI/TTS connectivity
#   ./scripts/preprod_run.sh pack [args...]   # Run `python -m app pack` strictly against Pre-prod
#   ./scripts/preprod_run.sh voice            # Start local Chatterbox voice service on 127.0.0.1:8090

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_PATH="$ROOT/.env.preprod"
PROD_PROJECT_REF="oohbmeffdncyzujmeqcz"

usage() {
  echo "Usage: $0 {web [port]|check|pack [args...]|voice}" >&2
  exit 2
}

cmd="${1:-}"
[ -n "$cmd" ] || usage
shift || true

if [ "$cmd" = "web" ]; then
  port="${1:-3000}"
  echo "Serving Pre-prod web UI at http://localhost:$port (routing to hhcygubulddewtwkedkz.supabase.co)"
  if command -v npx >/dev/null 2>&1; then
    exec npx serve "$ROOT/web" -l "$port"
  fi
  exec python3 -m http.server "$port" -d "$ROOT/web"
fi

if [ "$cmd" = "voice" ]; then
  export VOICE_DIR="$ROOT/voice_service/data/voices"
  export PRELOAD_VOICE="${PRELOAD_VOICE:-1}"
  cd "$ROOT/voice_service"
  exec "$ROOT/voice_service/.venv/bin/uvicorn" api.app:app --app-dir . --host 127.0.0.1 --port 8090
fi

if [ ! -f "$ENV_PATH" ]; then
  echo "Missing $ENV_PATH. Copy $ROOT/.env.preprod.example to .env.preprod first." >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source "$ENV_PATH"
set +a

if [[ "${SUPABASE_URL:-}" == *"$PROD_PROJECT_REF"* ]] || [ -z "${SUPABASE_URL:-}" ]; then
  echo "Refusing to run: SUPABASE_URL must point to your Pre-prod project, not production." >&2
  exit 1
fi

if [ -z "${SUPABASE_SECRET_KEY:-}" ] || [[ "$SUPABASE_SECRET_KEY" == *"REPLACE_WITH_YOUR_PREPROD_SECRET_KEY"* ]]; then
  echo "Paste your Pre-prod Secret key into $ENV_PATH (from Supabase project hhcygubulddewtwkedkz -> Settings -> API)." >&2
  exit 1
fi

export ENV_FILE="$ENV_PATH"
PY="${ROOT}/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

case "$cmd" in
  check)
    exec "$PY" -m app check "$@"
    ;;
  pack)
    exec "$PY" -m app pack "$@"
    ;;
  *)
    usage
    ;;
esac
