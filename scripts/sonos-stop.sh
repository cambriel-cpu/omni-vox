#!/bin/bash
# Stop Sonos playback via the Magnus bridge
# Usage: sonos-stop.sh [speaker_name]
# If no speaker specified, stops all active playback.

SPEAKER="${1:-}"

SSH_KEY="/root/.openclaw/omni_ssh_key"
SSH_OPTS="-o StrictHostKeyChecking=no -o IdentitiesOnly=yes"
UNRAID="omni@192.168.68.51"
BRIDGE="http://100.72.144.77:5111"

if [ -n "$SPEAKER" ]; then
    SPEAKER_ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$SPEAKER'))")
    ENDPOINT="${BRIDGE}/stop/${SPEAKER_ENCODED}"
else
    ENDPOINT="${BRIDGE}/stop"
fi

RESULT=$(ssh -i "$SSH_KEY" $SSH_OPTS "$UNRAID" \
    "curl -s -X POST '${ENDPOINT}' 2>&1")

echo "$RESULT"
