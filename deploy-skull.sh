#!/bin/bash
# Deploy Omni Vox Skull to servo-skull Pi 5
set -e

SKULL_HOST="omni@100.69.9.99"
SSH_KEY="/root/.ssh/id_ed25519"
SSH="ssh -i $SSH_KEY -o StrictHostKeyChecking=no"
SCP="scp -i $SSH_KEY -o StrictHostKeyChecking=no"

echo "=== Deploying Omni Vox Skull ==="

# Sync skull module
echo "Syncing code..."
$SCP -r skull/ ${SKULL_HOST}:~/omni-vox-skull/skull/

# Install systemd service (requires sudo)
echo "Installing systemd service..."
$SCP omni-vox-skull.service ${SKULL_HOST}:/tmp/omni-vox-skull.service
$SSH $SKULL_HOST 'sudo cp /tmp/omni-vox-skull.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable omni-vox-skull'

# Set audio volume
echo "Configuring audio..."
$SSH $SKULL_HOST 'amixer -c 2 sset PCM 85% > /dev/null 2>&1'

echo "=== Deployment complete ==="
echo "Start with: sudo systemctl start omni-vox-skull"
echo "Logs:       journalctl --user -u omni-vox-skull -f"
