#!/usr/bin/env bash
# Deploy EmptyEpsilon integration to Home Assistant, restart, and show logs.
#
# Prerequisites:
#   - rsync, curl, ssh
#   - SSH access to HA (Terminal & SSH add-on or debug SSH)
#   - Home Assistant long-lived access token
#
# Setup: copy deploy-to-ha.env.example to deploy-to-ha.env and fill in values.
# Run: ./deploy-to-ha.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INTEGRATION_DIR="${SCRIPT_DIR}/custom_components/empty_epsilon"

# Load config
if [[ -f "${SCRIPT_DIR}/deploy-to-ha.env" ]]; then
  set -a
  source "${SCRIPT_DIR}/deploy-to-ha.env"
  set +a
else
  echo "Error: deploy-to-ha.env not found. Copy deploy-to-ha.env.example and configure."
  exit 1
fi

: "${HA_URL:=http://homeassistant.local:8123}"
: "${HA_TOKEN:=}"
: "${SSH_HOST:=}"
: "${SSH_USER:=root}"
: "${SSH_PORT:=22}"
: "${REMOTE_CONFIG:=/config}"
: "${RESTART_WAIT:=90}"
: "${LOG_LINES:=100}"

if [[ -z "$HA_TOKEN" ]]; then
  echo "Error: HA_TOKEN not set in deploy-to-ha.env"
  exit 1
fi

# Default SSH host from HA URL if not set
if [[ -z "$SSH_HOST" ]]; then
  SSH_HOST="${HA_URL#http://}"
  SSH_HOST="${SSH_HOST#https://}"
  SSH_HOST="${SSH_HOST%%:*}"
fi

echo "=== Deploy EmptyEpsilon to Home Assistant ==="
echo "HA URL:     $HA_URL"
echo "SSH target: $SSH_USER@$SSH_HOST:$SSH_PORT"
echo "Remote:     $REMOTE_CONFIG/custom_components/empty_epsilon"
echo ""

# 1. Sync files via rsync
echo ">>> Syncing integration files..."
RSYNC_RSH="ssh -p ${SSH_PORT} -o StrictHostKeyChecking=no"
rsync -avz --delete -e "$RSYNC_RSH" \
  "${INTEGRATION_DIR}/" \
  "${SSH_USER}@${SSH_HOST}:${REMOTE_CONFIG}/custom_components/empty_epsilon/"
echo "    Done."
echo ""

# 2. Restart Home Assistant via API
echo ">>> Restarting Home Assistant..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST \
  -H "Authorization: Bearer ${HA_TOKEN}" \
  -H "Content-Type: application/json" \
  "${HA_URL}/api/services/homeassistant/restart")

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "    Warning: Restart returned HTTP $HTTP_CODE (HA may have already started restart)"
fi
echo "    Restart requested."
echo ""

# 3. Wait for HA to come back
echo ">>> Waiting ${RESTART_WAIT}s for HA to restart..."
for i in $(seq 1 "$RESTART_WAIT"); do
  if curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer ${HA_TOKEN}" \
    "${HA_URL}/api/" 2>/dev/null | grep -q 200; then
    echo "    HA is back (after ${i}s)."
    break
  fi
  sleep 1
  if [[ $i -eq $RESTART_WAIT ]]; then
    echo "    Timeout. HA may still be starting."
  fi
done
echo ""

# 4. Fetch and show EmptyEpsilon lines from logs
echo ">>> Recent EmptyEpsilon log entries:"
ssh -p "${SSH_PORT}" -o StrictHostKeyChecking=no "${SSH_USER}@${SSH_HOST}" \
  "tail -n ${LOG_LINES} ${REMOTE_CONFIG}/home-assistant.log 2>/dev/null | grep -i empty_epsilon | tail -n 30" \
  || echo "    (No matching lines or log not found)"
echo ""
echo "Done."
