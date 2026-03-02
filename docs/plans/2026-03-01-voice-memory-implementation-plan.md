# Voice Memory System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

## MDD Documentation

### Goal & Context
**Goal:** Build three-layer conversation memory system for servo skull voice interactions with <2 second response latency
**Why:** Current voice system has zero conversation context, making follow-up questions impossible and creating broken conversational AI experience
**Success Criteria:** Follow-up questions reference previous context correctly, cross-channel memory integration works, <2 second total response latency achieved

### Architecture & Approach  
**Pattern:** Layered memory architecture (immediate context + session memory + cross-channel bridge)
**Tech Stack:** Python 3.11+, FastAPI, WebSockets, JSON storage, Opus audio codec
**Dependencies:** Existing omni-vox server, OpenClaw memory system, servo skull Pi 5 hardware

### API Design (WebSocket Extensions)
**Message Types:**
- `voice_request` - Audio input with session context
- `session_start` - New conversation session initiated  
- `session_continue` - Follow-up within existing session
- `context_debug` - Debug information about context building

**Data Models:**
```python
@dataclass
class ConversationSession:
    session_id: str
    state: SessionState  # LISTENING | ACTIVE | ENDED
    start_time: float
    turns: List[ConversationTurn]
    context_buffer: List[str]
    
@dataclass  
class ConversationTurn:
    user_input: str
    assistant_response: str
    timestamp: float
    session_id: str
```

### Quality Requirements
**Performance:** <2 seconds total latency (north star), <10ms context building, <50ms memory operations
**Security:** No voice data logging beyond conversation context, secure session management
**Error Handling:** Graceful degradation when memory components fail, session recovery on restart

---

## Test Strategy

### Unit Tests (tests/memory/)
- `test_session_manager.py` - Session lifecycle and state transitions
- `test_layered_memory.py` - Three-layer memory coordination  
- `test_context_builder.py` - Context assembly and formatting
- `test_memory_bridge.py` - Cross-channel sync functionality
- `test_performance.py` - Latency and performance validation

### Integration Tests (tests/integration/)
- `test_voice_conversation_flow.py` - Complete voice request with context
- `test_session_persistence.py` - Context survival across restarts
- `test_cross_channel_memory.py` - Voice context in Discord memory

### Hardware Tests (tests/hardware/)
- `test_servo_skull_end_to_end.py` - Real wake word → response cycles
- `test_latency_measurement.py` - Performance validation on Pi 5
- `test_session_boundaries.py` - Wake word session management

### Test Data & Fixtures
- Mock conversation sessions with 3-20 turns
- Sample voice transcripts with follow-up questions  
- Cross-channel context scenarios
- Performance benchmark datasets

---

## Implementation Phases

### Phase 1: Core Memory Infrastructure (Estimated: 45 min)

#### Task 1: SessionManager Class (15 min)
**MDD Context:** Central coordinator for conversation session lifecycle, handles state transitions and timing

**Requirements:**
- MUST: Handle LISTENING/ACTIVE/ENDED state transitions  
- MUST: Configurable timing via environment variables
- SHOULD: Session recovery on restart
- MAY: Debug logging for session transitions

**Files:**
- Create: `src/session_manager.py` - Session lifecycle management
- Create: `tests/test_session_manager.py` - Session state and timing tests

**Step 1: Document Session Behavior (2 min)**
```python
describe('SessionManager', () => {
  describe('session lifecycle', () => {
    it('should start session on wake word');
    it('should extend session on follow-up');
    it('should end session on timeout');
  });
  
  describe('timing configuration', () => {
    it('should load timing from environment');
    it('should use defaults when env vars missing');  
  });
  
  describe('session recovery', () => {
    it('should restore session state on restart');
  });
});
```

**Step 2: Write failing tests (4 min)**
```python
def test_session_starts_on_wake_word():
    manager = SessionManager()
    session = manager.start_session("voice")
    
    assert session.state == SessionState.ACTIVE
    assert session.session_id is not None
    assert session.start_time > 0
    assert len(session.turns) == 0

def test_session_extends_on_followup():
    manager = SessionManager(mic_open_duration=15)
    session = manager.start_session("voice")
    original_end_time = session.estimated_end_time
    
    time.sleep(1)
    manager.extend_session(session.session_id)
    
    assert session.estimated_end_time > original_end_time
    assert session.state == SessionState.ACTIVE
```

**Step 3: Run tests - verify failure (1 min)**
**Step 4: Implement minimal SessionManager (6 min)**
**Step 5: Run quality gates (1 min)**
**Step 6: Verify requirements (1 min)**

#### Task 2: LayeredMemorySystem Class (20 min)
**MDD Context:** Coordinates three memory layers with performance optimization, ensures <10ms context building

**Requirements:**
- MUST: Immediate context buffer (<1ms access)
- MUST: Session memory with persistence (<5ms load)
- MUST: Memory bridge sync (async, non-blocking)
- SHOULD: Context caching for active sessions
- MAY: Memory compression for large sessions

**Files:**
- Create: `src/layered_memory.py` - Three-layer memory coordination
- Create: `tests/test_layered_memory.py` - Memory layer integration tests

**Implementation Steps:** [Same TDD pattern - 2min doc, 4min tests, 1min verify fail, 10min implement, 2min quality gates, 1min verify]

#### Task 3: ContextBuilder Class (10 min)  
**MDD Context:** Assembles complete conversation context for LLM requests, critical path for 2s latency goal

**Requirements:**
- MUST: Context assembly <5ms (performance critical)
- MUST: Include immediate context + session history + personality
- SHOULD: Optional relevant memory (skip if slow)
- MAY: Context truncation for large sessions

**Files:**
- Create: `src/context_builder.py` - Context assembly and formatting  
- Create: `tests/test_context_builder.py` - Context building performance tests

**Implementation Steps:** [Same TDD pattern]

### Phase 2: WebSocket Integration (Estimated: 30 min)

#### Task 4: WebSocket Context Injection (25 min)
**MDD Context:** Modify existing WebSocket handler to inject conversation context into LLM requests

**Requirements:**
- MUST: Inject context into all voice requests  
- MUST: Maintain backward compatibility with existing web interface
- MUST: Handle missing context gracefully
- SHOULD: Context debug information in development mode

**Files:**
- Modify: `server.py:245-280` - WebSocket message handler context injection
- Modify: `server.py:495-510` - LLM request context building
- Create: `tests/test_websocket_context.py` - WebSocket context integration

**Implementation Steps:**
1. **Document Context Injection (3 min)**
2. **Write integration tests (6 min)**  
3. **Verify test failures (1 min)**
4. **Implement context injection (12 min)**
5. **Quality gates (2 min)**
6. **End-to-end verification (1 min)**

#### Task 5: Session Turn Recording (5 min)
**MDD Context:** Record completed conversations for future context building

**Requirements:**
- MUST: Record user input + assistant response after each turn
- MUST: Associate turns with correct session
- SHOULD: Async recording to avoid blocking responses

**Files:**
- Modify: `server.py:775-780` - Turn recording after response completion
- Create: `tests/test_turn_recording.py` - Turn recording verification

### Phase 3: Cross-Channel Memory Bridge (Estimated: 25 min)

#### Task 6: Memory Bridge Integration (15 min)
**MDD Context:** Sync significant voice conversations to OpenClaw daily memory files

**Requirements:**
- MUST: Sync voice conversations to daily memory files
- MUST: Async operation, never block voice responses
- SHOULD: Intelligent conversation summarization  
- MAY: Configurable sync frequency

**Files:**
- Create: `src/memory_bridge.py` - Cross-channel memory sync
- Create: `tests/test_memory_bridge.py` - Memory bridge sync tests

#### Task 7: Cross-Channel Context Retrieval (10 min)
**MDD Context:** Enable Discord conversations to reference recent voice interactions

**Requirements:**
- MUST: Provide voice context for Discord memory search
- SHOULD: Recent context (last 24 hours) prioritized
- MAY: Contextual relevance filtering

**Files:**  
- Modify: `memory_bridge.py` - Add voice context retrieval methods
- Create: `tests/test_cross_channel_context.py` - Context retrieval tests

### Phase 4: Performance Optimization & Hardware Testing (Estimated: 40 min)

#### Task 8: Performance Profiling (15 min)
**MDD Context:** Measure and optimize critical path latency to meet 2s north star goal

**Requirements:**
- MUST: Profile context building latency (<10ms target)
- MUST: Profile memory operations (<50ms target)  
- SHOULD: Identify performance bottlenecks
- MAY: Add performance monitoring hooks

**Files:**
- Create: `src/performance_profiler.py` - Latency measurement tools
- Create: `tests/test_performance_benchmarks.py` - Performance validation tests

#### Task 9: Servo Skull Hardware Integration (25 min)
**MDD Context:** Deploy and test on actual Pi 5 servo skull hardware with real wake word detection

**Requirements:**
- MUST: Deploy memory system to servo skull Pi 5
- MUST: Test end-to-end conversation flow with real audio
- SHOULD: Validate session boundaries with wake word detection
- MAY: Performance optimization for Pi 5 hardware

**Files:**
- Create: `deploy/servo_skull_deployment.py` - Hardware deployment script
- Create: `tests/hardware/test_servo_skull_e2e.py` - End-to-end hardware tests

**Hardware Test Scenarios:**
1. **Basic conversation**: "Hey Omni" → question → immediate follow-up
2. **Session boundaries**: Long pause → new wake word → verify new session  
3. **Performance validation**: Measure wake word → audio response latency
4. **Cross-channel test**: Voice conversation → Discord reference verification

---

## Quality Gates Integration

### Security Checklist
- [ ] No hardcoded timing values (environment variable configuration)
- [ ] Voice conversation data properly sanitized before storage
- [ ] Session IDs generated securely (no predictable patterns)  
- [ ] Memory bridge sync permissions validated

### Code Quality Standards  
- [ ] All files < 300 lines (split memory components if needed)
- [ ] All functions < 50 lines (extract context building helpers)
- [ ] Explicit Python type hints (no `Any` types)
- [ ] Comprehensive error handling (no silent failures)

### Performance Standards
- [ ] Context building < 10ms (measured with profiler)
- [ ] Memory operations < 50ms (measured with profiler)  
- [ ] Total response latency < 2 seconds (measured on servo skull)
- [ ] Memory bridge operations fully async (never block responses)

---

## Implementation Readiness Checklist

- [x] Requirements clearly documented (design document completed)
- [x] Test strategy defined (unit, integration, hardware tests)  
- [x] Implementation phases planned with time estimates (140 minutes total)
- [x] Quality gates identified (performance, security, code quality)
- [x] Security considerations addressed (data sanitization, secure sessions)
- [x] Performance requirements specified (2s north star, 10ms context building)
- [x] Error handling strategy defined (graceful degradation, session recovery)

**Approval Required:** Implementation plan ready for execution  
**Time Estimate:** 140 minutes (2 hours 20 minutes)
**Quality Gate:** All tests pass + Python type checking + Linting + Performance benchmarks pass

---

## Execution Handoff

**MDD Plan complete and saved to `docs/plans/2026-03-01-voice-memory-implementation-plan.md`**

**Documentation-driven implementation ready. Execution approaches:**

**1. MDD Sequential** - Document → Test → Implement → Verify each phase with approval gates (Recommended for performance-critical system)

**2. Subagent-Driven** - Fresh writer agent per task with MDD quality gates enforced  

**3. Parallel Session** - Dedicated session for systematic execution with hardware testing checkpoints

**Recommendation: MDD Sequential approach** - Performance requirements and hardware integration need careful sequential validation at each step.

**Next Phase:** Use `superpowers:executing-plans` to implement this plan task-by-task with quality gates enforced.