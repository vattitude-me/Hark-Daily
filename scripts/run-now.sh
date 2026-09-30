#!/usr/bin/env bash
# Build briefings right now, from a clean slate, and print them.
#
#   scripts/run-now.sh                       # everyone
#   scripts/run-now.sh --user you@mail.com   # just one user (repeat --user for more)
#   scripts/run-now.sh --no-push ...         # without notifications
#
# Deletes today's briefing(s) for those users, clears cached summaries and audio,
# re-queues article links used today, then rebuilds with each user's current links.
set -euo pipefail
cd "$(dirname "$0")/.."
exec docker compose exec worker python -m app run --fresh "$@"
