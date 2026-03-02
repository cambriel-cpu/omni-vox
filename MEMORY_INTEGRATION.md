# Memory Integration Guide

This document shows how to integrate the persistent conversation memory and memory bridge into the existing omni-vox server.

## Integration Steps

### 1. Import Memory Bridge (Add after other imports)

```python
from conversation import ConversationBuffer
from memory_bridge import MemoryBridge  # ADD THIS LINE
from metrics import metrics, start_metrics_server
```

### 2. Update ConversationBuffer Configuration

Replace the existing conversation buffer initialization:

```python
# OLD
conversation = ConversationBuffer(max_turns=20)

# NEW - with persistent storage
conversation_storage_dir = os.environ.get("CONVERSATION_STORAGE", "/tmp/omni-vox-conversations")
conversation = ConversationBuffer(max_turns=20, storage_dir=conversation_storage_dir)
```

### 3. Initialize Memory Bridge (Add after conversation buffer)

```python
# NEW: Memory bridge for cross-channel memory integration
sessions_dir = os.environ.get("SESSIONS_DIR", "/sessions") 
memory_bridge = MemoryBridge(sessions_dir=sessions_dir, memory_sync_interval=5)
```

### 4. Integrate Memory Sync (Update existing turn recording)

Find the two locations where `conversation.add_turn()` is called and add memory bridge sync:

**Location 1: WebSocket path (around line 252)**
```python
# Add conversation tracking for WebSocket path
conv_session_key = "voice"
conversation.add_turn(conv_session_key, transcript, llm_response)

# NEW: Sync to memory bridge for cross-channel awareness
memory_bridge.sync_session_if_needed(conv_session_key, conversation)
```

**Location 2: HTTP API path (around line 776)**
```python
# Store turn in conversation buffer for multi-turn context
conv_session_key = "voice"
conversation.add_turn(conv_session_key, transcript, clean_response)

# NEW: Sync to memory bridge for cross-channel awareness  
memory_bridge.sync_session_if_needed(conv_session_key, conversation)
```

### 5. Add Memory Management Endpoints (Add new API endpoints)

```python
@app.get("/api/voice/memory/stats")
async def get_memory_stats():
    """Get conversation memory statistics"""
    conversation_stats = conversation.get_session_stats()
    return {
        "conversation_buffer": conversation_stats,
        "storage_directory": conversation_storage_dir,
        "memory_bridge": {
            "sessions_synced": len(memory_bridge.last_sync_counts),
            "sync_interval": memory_bridge.memory_sync_interval
        }
    }

@app.post("/api/voice/memory/cleanup")
async def cleanup_old_conversations(max_age_days: int = Form(30)):
    """Clean up conversations older than specified days"""
    cleaned_count = conversation.cleanup_old_sessions(max_age_days)
    return {
        "cleaned_sessions": cleaned_count,
        "max_age_days": max_age_days
    }

@app.get("/api/voice/memory/context")
async def get_voice_context(hours_back: int = 24):
    """Get recent voice conversation context for cross-channel consistency"""
    context = memory_bridge.get_recent_voice_context("voice", hours_back)
    return {
        "context": context,
        "hours_back": hours_back,
        "has_context": context is not None
    }
```

### 6. Update Environment Configuration

Add to `.env` file:

```bash
# Conversation Storage (persistent across restarts)
CONVERSATION_STORAGE=/tmp/omni-vox-conversations

# Sessions Directory (for memory bridge sync) 
SESSIONS_DIR=/sessions
```

### 7. Update Dockerfile (if needed)

Ensure the conversation storage directory is mounted:

```dockerfile
# Create conversation storage directory
RUN mkdir -p /tmp/omni-vox-conversations

# Mount point for sessions (for memory bridge)
VOLUME ["/sessions"]
```

### 8. Update Docker Deployment

Update the deployment script to mount the conversation storage:

```bash
sudo docker run -d \
  --name omni-vox \
  --network host \
  --restart unless-stopped \
  --env-file /mnt/user/appdata/omni-vox/.env \
  -v /mnt/user/appdata/openclaw/config/agents/main/sessions:/sessions:ro \
  -v /mnt/user/appdata/omni-vox/conversations:/tmp/omni-vox-conversations \
  omni-vox:v2.0.0
```

## Verification Steps

After integration, test these features:

### 1. Persistent Conversation Memory
```bash
# Make a voice request
# Restart the container
# Make another voice request - should remember previous context
```

### 2. Cross-Channel Memory Sync
```bash
# Check daily memory files for voice conversation entries
ls /root/.openclaw/workspace/memory/
cat /root/.openclaw/workspace/memory/$(date +%Y-%m-%d).md
```

### 3. Memory Management APIs
```bash
# Get memory statistics
curl http://localhost:7100/api/voice/memory/stats

# Get recent voice context  
curl http://localhost:7100/api/voice/memory/context?hours_back=24

# Clean up old conversations
curl -X POST http://localhost:7100/api/voice/memory/cleanup -F "max_age_days=7"
```

## Benefits After Integration

1. **Persistent Conversations**: Voice conversations survive container restarts
2. **Cross-Channel Memory**: Voice interactions visible in Discord conversations  
3. **Intelligent Syncing**: Automatic sync to daily memory files every 5 turns
4. **Memory Management**: APIs for monitoring and cleanup
5. **Context Consistency**: Seamless switching between voice and text channels

## Troubleshooting

### Conversation Not Persisting
- Check `CONVERSATION_STORAGE` directory is writable
- Verify conversation files are being created in storage directory
- Check logs for JSON serialization errors

### Memory Bridge Not Syncing
- Verify `SESSIONS_DIR` points to correct OpenClaw sessions directory
- Check `/root/.openclaw/workspace/memory/` directory exists and is writable
- Monitor logs for memory sync operations

### Cross-Channel Memory Missing  
- Ensure memory bridge is calling `sync_session_if_needed()` after turns
- Check daily memory files contain voice conversation sections
- Verify memory search can find voice conversation entries

## Performance Considerations

- Conversation files are JSON - minimal I/O overhead
- Memory sync only occurs every N turns - not every interaction
- Old conversations are automatically cleaned up
- Memory bridge uses async operations to avoid blocking

The integration maintains backward compatibility while adding robust memory capabilities.