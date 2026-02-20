#!/bin/bash
set -e

echo "🚀 Deploying OmniVox WebSocket Streaming v2.0..."

# Configuration
CONTAINER_NAME="omni-vox"
NEW_VERSION="v2.0.0-websocket-streaming"
REMOTE_HOST="omni@192.168.68.51"
SSH_KEY="/root/.openclaw/omni_ssh_key"
SSH_OPTS="-i $SSH_KEY -o StrictHostKeyChecking=no -o IdentitiesOnly=yes"

# Build deployment package
echo "📦 Building deployment package..."
tar czf /tmp/omni-vox-deploy.tar.gz \
    --exclude=venv \
    --exclude=__pycache__ \
    --exclude='*.pyc' \
    --exclude='*.backup' \
    --exclude='.pytest_cache' \
    --exclude='.coverage' \
    Dockerfile .dockerignore requirements*.txt \
    server.py validation.py session_manager.py audio_streamer.py metrics.py \
    static/ tests/

# Upload to server
echo "📤 Uploading to server..."
scp $SSH_OPTS /tmp/omni-vox-deploy.tar.gz $REMOTE_HOST:/tmp/

# Deploy on server
echo "🏗️  Building and deploying container..."
ssh $SSH_OPTS $REMOTE_HOST << 'EOF'
set -e

# Extract and build
cd /tmp
rm -rf omni-vox-build
mkdir omni-vox-build
cd omni-vox-build
tar xzf /tmp/omni-vox-deploy.tar.gz

# Build new image
echo "Building Docker image..."
docker build -t omni-vox:v2.0.0-websocket-streaming .

# Test new container
echo "Testing new container..."
docker run --rm --name omni-vox-test \
    -e KOKORO_BASE_URL=http://192.168.68.51:8880 \
    -e METRICS_PORT=9091 \
    -p 7101:8000 -p 9091:9091 \
    -d omni-vox:v2.0.0-websocket-streaming

# Wait for startup
sleep 10

# Test health endpoints
echo "Testing health endpoints..."
if curl -f http://localhost:7101/health; then
    echo "✅ Health check passed"
else
    echo "❌ Health check failed"
    docker stop omni-vox-test
    exit 1
fi

if curl -f http://localhost:7101/health/ready; then
    echo "✅ Readiness check passed"
else
    echo "❌ Readiness check failed"
    docker stop omni-vox-test
    exit 1
fi

if curl -f http://localhost:7101/health/live; then
    echo "✅ Liveness check passed"
else
    echo "❌ Liveness check failed"
    docker stop omni-vox-test
    exit 1
fi

# Test metrics endpoint
if curl -f http://localhost:9091/metrics >/dev/null 2>&1; then
    echo "✅ Metrics endpoint accessible"
else
    echo "❌ Metrics endpoint failed"
    docker stop omni-vox-test
    exit 1
fi

# Stop test container
docker stop omni-vox-test

# Graceful deployment
echo "Performing graceful deployment..."
if docker ps | grep -q $CONTAINER_NAME; then
    echo "Stopping existing container..."
    docker stop $CONTAINER_NAME
    docker rm $CONTAINER_NAME
fi

# Start new production container
echo "Starting new production container..."
docker run -d --name $CONTAINER_NAME \
    --network host \
    --restart unless-stopped \
    --env-file /mnt/user/appdata/omni-vox/.env \
    -v /mnt/user/appdata/openclaw/config/agents/main/sessions:/sessions:ro \
    -v /mnt/user/appdata/openclaw/config/workspace/SOUL.md:/app/SOUL.md:ro \
    omni-vox:v2.0.0-websocket-streaming

# Wait for startup
sleep 15

# Final validation
echo "🔍 Performing final deployment validation..."

# Health checks
if curl -f http://localhost:7100/health; then
    echo "✅ Production health check passed"
else
    echo "❌ Production health check failed!"
    exit 1
fi

# WebSocket connection test
if curl -f http://localhost:7100/metrics/websocket; then
    echo "✅ WebSocket metrics accessible"
else
    echo "❌ WebSocket metrics failed!"
    exit 1
fi

# Check metrics server
if curl -f http://localhost:9090/metrics >/dev/null 2>&1; then
    echo "✅ Production metrics server accessible"
else
    echo "❌ Production metrics server failed!"
    exit 1
fi

echo "🧹 Cleaning up..."
rm -rf /tmp/omni-vox-build /tmp/omni-vox-deploy.tar.gz
EOF

# Post-deployment browser WebSocket test
echo "🌐 Testing browser WebSocket connection..."

# Create temporary test HTML file
cat > /tmp/websocket_test.html << 'EOF'
<!DOCTYPE html>
<html>
<head><title>WebSocket Test</title></head>
<body>
<script>
const ws = new WebSocket('ws://192.168.68.51:7100/ws');
let testResult = 'FAIL';

ws.onopen = function() {
    console.log('WebSocket connected');
    ws.send(JSON.stringify({type: 'ping'}));
};

ws.onmessage = function(event) {
    const message = JSON.parse(event.data);
    if (message.type === 'pong') {
        testResult = 'PASS';
        console.log('WebSocket test PASSED');
    }
    ws.close();
};

ws.onclose = function() {
    document.body.innerHTML = '<h1>Test Result: ' + testResult + '</h1>';
    if (testResult === 'PASS') {
        document.title = 'WEBSOCKET_TEST_PASS';
    } else {
        document.title = 'WEBSOCKET_TEST_FAIL';
    }
};

ws.onerror = function(error) {
    console.error('WebSocket error:', error);
    testResult = 'FAIL';
    document.body.innerHTML = '<h1>Test Result: FAIL</h1>';
    document.title = 'WEBSOCKET_TEST_FAIL';
};
</script>
</body>
</html>
EOF

# Test with headless browser if available
if command -v google-chrome &> /dev/null; then
    echo "Testing with Chrome headless..."
    timeout 30 google-chrome --headless --disable-gpu --virtual-time-budget=10000 \
        --run-all-compositor-stages-before-draw \
        --dump-dom file:///tmp/websocket_test.html > /tmp/test_result.html 2>/dev/null || true
    
    if grep -q "WEBSOCKET_TEST_PASS" /tmp/test_result.html 2>/dev/null; then
        echo "✅ Browser WebSocket test PASSED"
    else
        echo "⚠️  Browser WebSocket test FAILED or Chrome not available"
        echo "   Manual verification recommended at: http://192.168.68.51:7100/"
    fi
else
    echo "⚠️  Chrome not available for automated browser testing"
    echo "   Manual verification recommended at: http://192.168.68.51:7100/"
fi

# Cleanup
rm -f /tmp/omni-vox-deploy.tar.gz /tmp/websocket_test.html /tmp/test_result.html

echo "🎉 Deployment complete!"
echo "🌐 OmniVox available at: http://192.168.68.51:7100"
echo "📊 Metrics available at: http://192.168.68.51:9090"
echo "📊 WebSocket metrics: http://192.168.68.51:7100/metrics/websocket"
echo "🔍 Monitor with: ssh $SSH_OPTS $REMOTE_HOST 'docker logs -f $CONTAINER_NAME'"

echo "🧪 Running post-deployment validation..."
echo "Health check: $(curl -s http://192.168.68.51:7100/health | jq -r '.status')"
echo "Active sessions: $(curl -s http://192.168.68.51:7100/metrics/websocket | jq -r '.active_sessions')"
echo "Total connections: $(curl -s http://192.168.68.51:7100/metrics/websocket | jq -r '.total_connections')"