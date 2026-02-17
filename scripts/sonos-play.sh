#!/bin/bash
# Play an audio file on a Sonos speaker via the Magnus bridge
# Usage: sonos-play.sh <audio_file> [speaker_name] [volume]
#
# Non-blocking — returns immediately after playback starts.
# Use sonos-stop.sh to interrupt.

AUDIO_FILE="$1"
SPEAKER="${2:-office}"
VOLUME="${3:-65}"

SSH_KEY="/root/.openclaw/omni_ssh_key"
SSH_OPTS="-o StrictHostKeyChecking=no -o IdentitiesOnly=yes"
UNRAID="omni@192.168.68.51"
BRIDGE="http://100.72.144.77:5111"

if [ -z "$AUDIO_FILE" ]; then
    echo "Usage: sonos-play.sh <audio_file> [speaker_name] [volume]"
    exit 1
fi

if [ ! -f "$AUDIO_FILE" ]; then
    echo "Error: File not found: $AUDIO_FILE"
    exit 1
fi

SPEAKER_ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$SPEAKER'))")

REMOTE_PATH="/tmp/sonos-$(basename "$AUDIO_FILE")"
scp -i "$SSH_KEY" $SSH_OPTS "$AUDIO_FILE" "${UNRAID}:${REMOTE_PATH}" 2>/dev/null

RESULT=$(ssh -i "$SSH_KEY" $SSH_OPTS "$UNRAID" \
    "curl -s -X POST '${BRIDGE}/play/${SPEAKER_ENCODED}?volume=${VOLUME}' -F 'audio=@${REMOTE_PATH}' 2>&1")

ssh -i "$SSH_KEY" $SSH_OPTS "$UNRAID" "rm -f '${REMOTE_PATH}'" 2>/dev/null

echo "$RESULT"
