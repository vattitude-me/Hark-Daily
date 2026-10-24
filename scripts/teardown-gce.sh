#!/usr/bin/env bash
# Teardown the Morning Brief Chatterbox-Turbo GCE GPU VM and resources to eliminate recurring GCP costs.
#
# Deleting the GCE VM saves ~$6/month for the 40GB boot persistent disk + prevents any accidental runtime.
#
# Usage:
#   scripts/teardown-gce.sh [PROJECT_ID] [ZONE]
#
set -euo pipefail

INSTANCE_NAME="morning-brief-voice"
ZONE="${2:-us-central1-c}"
PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null || echo 'project-67937e0a-4d2d-43ea-9ba')}"

echo "============================================================"
echo "  Tearing Down Morning Brief Voice Service GCE Resources     "
echo "  Project:  $PROJECT_ID"
echo "  Zone:     $ZONE"
echo "  Instance: $INSTANCE_NAME"
echo "============================================================"

# 1. Delete GCE VM instance (and its attached boot disk)
if gcloud compute instances describe "$INSTANCE_NAME" --zone="$ZONE" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "→ Deleting GCE GPU VM instance ($INSTANCE_NAME) and attached boot disk..."
  gcloud compute instances delete "$INSTANCE_NAME" \
    --zone="$ZONE" \
    --project="$PROJECT_ID" \
    --delete-disks=all \
    --quiet
  echo "✓ Instance and boot disk deleted."
else
  echo "• GCE instance $INSTANCE_NAME does not exist (already deleted)."
fi

# 2. Check for any orphaned disks matching the name
if gcloud compute disks describe "$INSTANCE_NAME" --zone="$ZONE" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "→ Deleting orphaned persistent disk ($INSTANCE_NAME)..."
  gcloud compute disks delete "$INSTANCE_NAME" --zone="$ZONE" --project="$PROJECT_ID" --quiet
  echo "✓ Persistent disk deleted."
fi

# 3. Optional: delete firewall rule
read -rp "Delete firewall rule 'allow-voice-service'? (y/N): " DELETE_FW || true
if [[ "${DELETE_FW:-}" =~ ^[Yy]$ ]]; then
  if gcloud compute firewall-rules describe allow-voice-service --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud compute firewall-rules delete allow-voice-service --project="$PROJECT_ID" --quiet
    echo "✓ Firewall rule deleted."
  fi
fi

echo ""
echo "============================================================"
echo "✓ Teardown complete. Recurring persistent disk costs eliminated."
echo "Note: If Cloud Run jobs run without GCE, ensure either:"
echo "  1) GCE_MANAGE_VM=false with a remote VOICE_SERVICE_URL set, or"
echo "  2) Re-deploy the GCE VM anytime using: scripts/deploy-gce.sh"
echo "============================================================"
