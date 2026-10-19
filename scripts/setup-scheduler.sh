#!/usr/bin/env bash
# Setup Google Cloud Scheduler and Cloud Run Jobs to run the morning briefing daily.
# - 05:00 AM: Main story pack synthesis (with 50 min deadline, 0 retries to prevent runaway GPU billing)
# - 06:15 AM: Safety-net report & retry (checks if all voices completed, re-renders any missing, notifies admin)
#
# Usage:
#   scripts/setup-scheduler.sh [PROJECT_ID] [REGION]
#
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"

PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null || echo 'project-67937e0a-4d2d-43ea-9ba')}"
REGION="${2:-us-central1}"
JOB_NAME="morning-brief-pack"
REPORT_JOB_NAME="morning-brief-report"
SCHEDULER_NAME="morning-brief-daily-5am"
REPORT_SCHEDULER_NAME="morning-brief-daily-615am"
TIMEZONE="${BRIEFING_TIMEZONE:-America/Toronto}"

echo "============================================================"
echo "  Setting up Daily Google Cloud Scheduler & Cloud Run Jobs  "
echo "  Project:   $PROJECT_ID"
echo "  Region:    $REGION"
echo "  Timezone:  $TIMEZONE"
echo "============================================================"

# Ensure required APIs are enabled
gcloud services enable cloudscheduler.googleapis.com run.googleapis.com --project="$PROJECT_ID"

# Read environment variables from .env
if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

VOICE_URL="${VOICE_SERVICE_URL:-auto}"

ENV_FILE=$(mktemp /tmp/mb-env-XXXXXX.yaml)
trap 'rm -f "$ENV_FILE"' EXIT

python3 -c "
import json, os
if os.path.exists('$ROOT/.env'):
    with open('$ROOT/.env') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k, v)

vapid_pub, vapid_priv = '', ''
if os.path.exists('$ROOT/data/vapid.json'):
    d = json.load(open('$ROOT/data/vapid.json'))
    vapid_pub = d.get('public_key', '')
    vapid_priv = d.get('private_pem', '').replace('\n', '\\n')

env_map = {
    'VOICE_SERVICE_URL': os.getenv('VOICE_SERVICE_URL', 'auto'),
    'SUPABASE_URL': os.getenv('SUPABASE_URL', ''),
    'SUPABASE_SECRET_KEY': os.getenv('SUPABASE_SECRET_KEY', ''),
    'GROQ_API_KEY': os.getenv('GROQ_API_KEY', ''),
    'TZ': '$TIMEZONE',
    'BRIEFING_TIMEZONE': '$TIMEZONE',
    'ADMIN_EMAILS': 'vatsakrish@gmail.com',
    'GCP_PROJECT': '$PROJECT_ID',
    'GCE_ZONE': 'us-central1-c',
    'GCE_INSTANCE': 'morning-brief-voice',
    'GCE_MANAGE_VM': 'true',
    'GCE_HEALTH_TIMEOUT': '300.0',
    'STORY_VOICES': 'her_reference,him_reference,jerry_reference,c3po_reference',
    'VAPID_PUBLIC_KEY': vapid_pub,
    'VAPID_PRIVATE_KEY': vapid_priv,
}
with open('$ENV_FILE', 'w') as f:
    for k, v in env_map.items():
        if v:
            f.write(f'{k}: {json.dumps(v)}\n')
"

# Build the worker Docker image
WORKER_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/voice-service/morning-brief-worker:latest"
echo "→ Building worker image via Google Cloud Build..."
gcloud builds submit "$ROOT" \
  --tag="$WORKER_TAG" \
  --project="$PROJECT_ID"

# 1. Main Pack Job (05:00 AM)
echo "→ Creating/updating Main Pack Cloud Run Job ($JOB_NAME)..."
gcloud run jobs deploy "$JOB_NAME" \
  --image="$WORKER_TAG" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --command="python" \
  --args="-m,app,pack,--notify,--deadline,50" \
  --env-vars-file="$ENV_FILE" \
  --cpu=2 \
  --memory=2Gi \
  --task-timeout=60m \
  --max-retries=0

# 2. Report & Retry Safety Job (06:15 AM)
echo "→ Creating/updating Report & Retry Cloud Run Job ($REPORT_JOB_NAME)..."
gcloud run jobs deploy "$REPORT_JOB_NAME" \
  --image="$WORKER_TAG" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --command="python" \
  --args="-m,app,pack,--report,--retry,--deadline,40" \
  --env-vars-file="$ENV_FILE" \
  --cpu=2 \
  --memory=2Gi \
  --task-timeout=60m \
  --max-retries=0

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Grant roles/run.invoker to the service account
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/run.invoker" --condition=None --quiet >/dev/null 2>&1 || true

# 3. Main Schedule (05:00 AM)
echo "→ Creating/updating Cloud Scheduler ($SCHEDULER_NAME) for 05:00 AM..."
gcloud scheduler jobs delete "$SCHEDULER_NAME" --location="$REGION" --project="$PROJECT_ID" --quiet 2>/dev/null || true
gcloud scheduler jobs create http "$SCHEDULER_NAME" \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --schedule="0 5 * * *" \
  --time-zone="$TIMEZONE" \
  --description="Run Morning Brief pack daily at 5:00 AM" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" \
  --http-method="POST" \
  --oauth-service-account-email="$SERVICE_ACCOUNT"

# 4. Report & Retry Schedule (06:15 AM)
echo "→ Creating/updating Cloud Scheduler ($REPORT_SCHEDULER_NAME) for 06:15 AM..."
gcloud scheduler jobs delete "$REPORT_SCHEDULER_NAME" --location="$REGION" --project="$PROJECT_ID" --quiet 2>/dev/null || true
gcloud scheduler jobs create http "$REPORT_SCHEDULER_NAME" \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --schedule="15 6 * * *" \
  --time-zone="$TIMEZONE" \
  --description="Verify Morning Brief completeness, retry missing narrators, and notify admin at 6:15 AM" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${REPORT_JOB_NAME}:run" \
  --http-method="POST" \
  --oauth-service-account-email="$SERVICE_ACCOUNT"

echo ""
echo "============================================================"
echo "✓ Scheduled successfully!"
echo "  1) Main pack at 05:00 AM ($JOB_NAME)"
echo "  2) Report/retry at 06:15 AM ($REPORT_JOB_NAME)"
echo "============================================================"
