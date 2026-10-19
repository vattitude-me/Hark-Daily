#!/usr/bin/env bash
# Runs the daily story pack generation with automated GCE GPU start and stop.
# GCE VM lifecycle, dynamic IP resolution, lease locking, and verified shutdown
# are managed automatically by the application (app.gce.voice_vm_session).
set -euo pipefail

cd "$(dirname "$0")/.."
echo "[$(date -u)] Running story pack generation..."
python3 -m app pack "$@"
echo "[$(date -u)] Pack generation complete!"
