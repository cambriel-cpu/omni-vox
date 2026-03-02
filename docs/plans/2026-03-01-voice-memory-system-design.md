# Voice Memory System Design
**Date:** 2026-03-01  
**Goal:** Implement seamless conversation memory for servo skull voice interactions  
**North Star:** 2-second conversation latency  

## Problem Statement

**Current Issue:** Voice interactions have zero conversation context - every request treated as completely new, even within the same WebSocket session.

**User Experience Impact:** 
- No follow-up questions work
- Conversational AI feels broken and impersonal
- Context switching between voice and Discord is jarring

**Primary Interface:** Servo skull Pi 5 with wake word activation, not web interface testing.

## Success Criteria

1. **Conversation Continuity**: Follow-up questions reference previous context correctly
2. **Performance Target**: <2 seconds total response latency (north star goal)
3. **Session Management**: Proper boundaries between conversation sessions  
4. **Cross-Channel Memory**: Voice context available in Discord interactions
5. **Reliability**: Context preserved across container restarts

## Architecture: Three-Layer Memory System

### Layer 1: Immediate Context Buffer (In-Memory, <1ms)
- **Purpose**: Fast access to last 3-5 turns for immediate follow-ups
- **Storage**: In-memory, ephemeral within session
- **Performance**: Always included in context, zero latency impact

### Layer 2: Session Memory (Persistent, <10ms)  
- **Purpose**: Full conversation from wake word to session end
- **Storage**: JSON files, persistent across container restarts
- **Performance**: Lazy loaded, cached in memory during active session

### Layer 3: Cross-Channel Memory Bridge (<50ms, async)
- **Purpose**: Sync important voice details to daily memory files
- **Storage**: Daily memory files (`/root/.openclaw/workspace/memory/YYYY-MM-DD.md`)
- **Performance**: Async syncing every 3-5 turns, doesn't block responses

## Session Management (Simplified)

### Session States
- **LISTENING**: Waiting for wake word detection  
- **ACTIVE**: Session running, mic open, processing conversation
- **ENDED**: Session archived to persistent storage

### Session Flow
1. **Wake word detected** → Start session, mic open for `WAKE_WORD_TIMEOUT` (5s)
2. **User speaks** → Process with full context, respond, extend mic for `MIC_OPEN_DURATION` (15s) 
3. **Follow-up within window** → Continue session, reset timer
4. **Silence timeout** → End session, archive conversation
5. **Next wake word** → New session (can reference previous when relevant)

### Configurable Timing (Environment Variables)
```bash
MIC_OPEN_DURATION=15      # Seconds mic stays open after response
WAKE_WORD_TIMEOUT=5       # Initial listening window 
CONTEXT_SYNC_INTERVAL=5   # Turns between memory bridge syncs
```

## Performance Optimizations (2-Second Target)

### Audio Processing
- **Codec**: Opus for maximum efficiency and minimal latency
- **STT**: Whisper with streaming/chunked processing where possible
- **TTS**: Kokoro (local) prioritized over ElevenLabs (cloud) for latency

### Context Building Pipeline
```
Context Assembly (Target: <10ms total)
├── Immediate Context (3-5 turns) → <1ms (in-memory)
├── Session History (if >5 turns) → <5ms (JSON deserialize)  
├── Personality Context (SOUL.md) → <1ms (cached)
└── Relevant Memory (optional) → <3ms (async, can skip if slow)
```

### Memory Operations  
- **Session storage**: JSON (simple, fast) over SQLite (query overhead)
- **Memory bridge sync**: Fully async, never blocks voice responses
- **Context caching**: Keep current session context in memory, no repeated disk I/O

## Data Flow Architecture

```
Wake Word → STT → Context Building → LLM → TTS → Audio Output
     ↓       ↓         ↓             ↓      ↓         ↓
Session    Voice    [Immediate +   AI     Audio   Sonos/Speaker
 Start    to Text   Session +    Response  Stream   Playback
          (Opus)    Memory]      (Claude)  (Opus)    
                        ↓
                   Memory Bridge
                   (Async Sync)
```

## Core Components

### 1. SessionManager
- **Responsibility**: Session lifecycle (start/continue/end)
- **Key Methods**: `start_session()`, `extend_session()`, `end_session()`
- **Performance**: <1ms for state transitions

### 2. LayeredMemorySystem
- **Responsibility**: Three-layer memory architecture coordination
- **Key Methods**: `get_immediate_context()`, `load_session()`, `sync_to_bridge()`
- **Performance**: <10ms for full context assembly

### 3. ContextBuilder  
- **Responsibility**: Assemble complete context for LLM requests
- **Key Methods**: `build_context()`, `format_for_llm()`
- **Performance**: <5ms for context formatting

### 4. MemoryBridge
- **Responsibility**: Cross-channel memory integration  
- **Key Methods**: `sync_session_summary()`, `get_voice_context_for_discord()`
- **Performance**: Async, non-blocking

### 5. ConfigurableTimers
- **Responsibility**: Runtime-adjustable timing parameters
- **Key Methods**: Environment variable loading and validation
- **Performance**: Zero runtime impact (loaded once)

## Testing Strategy: Real Hardware End-to-End

### Servo Skull Hardware Testing (Pi 5 at 100.69.9.99)
1. **Basic Conversation Flow**:
   - "Hey Omni, what's the weather?" 
   - "Should I bring an umbrella?"
   - Verify: Second question references weather from first

2. **Session Boundary Testing**:
   - Complete conversation → 15s silence → "Hey Omni" again
   - Verify: New session started, previous context available if relevant

3. **Performance Validation**:
   - Measure: Wake word → final audio output latency
   - Target: <2 seconds total, <10ms for context building

4. **Cross-Channel Memory**:
   - Voice conversation about project X
   - Discord: "How's that project going?"
   - Verify: Voice context included in Discord response

### Verification via SSH Monitoring
```bash
# Real-time conversation monitoring
ssh omni@100.69.9.99 "tail -f /var/log/omni-vox/conversation.log"

# Session persistence verification  
ssh omni@100.69.9.99 "ls -la /tmp/omni-vox-conversations/"

# Memory bridge validation
tail -20 /root/.openclaw/workspace/memory/$(date +%Y-%m-%d).md
```

## Error Handling & Reliability

### Session Recovery
- **Lost session state**: Gracefully start new session, continue conversation
- **Memory corruption**: Fallback to immediate context, log error  
- **Context building timeout**: Skip optional components, proceed with essential context

### Performance Degradation Handling
- **Memory bridge slow**: Skip sync, prioritize response speed
- **Large session history**: Truncate to most recent turns, maintain performance
- **STT/TTS latency spikes**: Monitor and alert, but maintain conversation flow

## Implementation Success Metrics

### Performance Metrics
- **Total latency**: <2 seconds (north star)
- **Context building**: <10ms 
- **Session operations**: <5ms
- **Memory sync**: Async, <100ms when it occurs

### Functional Metrics  
- **Follow-up success rate**: >95% (questions reference previous context)
- **Session boundary accuracy**: >90% (correct session start/end detection)
- **Cross-channel integration**: Voice context available in Discord within 1 turn
- **Reliability**: Context preserved through container restarts

## Next Steps: Implementation Planning

This design is approved for implementation. Next phase: Use `writing-plans` skill to create detailed implementation plan with:

1. Task breakdown with time estimates
2. Test-driven development approach  
3. Performance validation at each step
4. Integration with existing omni-vox codebase
5. Deployment strategy for servo skull hardware

**Priority Order**: Performance-critical components first (context building, session management), then reliability features (persistence, cross-channel sync).