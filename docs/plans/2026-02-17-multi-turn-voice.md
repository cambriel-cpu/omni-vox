# Multi-Turn Voice Conversations — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable Omni Vox to maintain conversation context across multiple voice exchanges, so the LLM can reference what was said in prior turns.

**Architecture:** Since OpenClaw hooks always create new sessions per request (confirmed bug: github.com/openclaw/openclaw/issues/11665), we manage conversation history client-side. The frontend maintains a conversation buffer in memory (and persists to localStorage). On each voice request, the backend reads the last N turns from its own server-side buffer and injects them as conversation context into the hook message. This avoids any OpenClaw API changes and works today.

**Tech Stack:** Python (FastAPI backend), JavaScript (frontend), existing OpenClaw hooks API

**Key Constraint:** OpenClaw hooks don't support multi-turn sessions — each request creates a new session. We CANNOT rely on session reuse. We must inject conversation history into the prompt ourselves.

---

## Architecture Overview

```
[Frontend: app.js]
  - Maintains conversation display (already done)
  - No history management needed (backend handles it)

[Backend: server.py]  
  - NEW: ConversationBuffer class (in-memory, per model session key)
  - Stores last MAX_TURNS (configurable, default 20) user/assistant pairs
  - On each /api/voice request:
    1. Transcribe audio (existing)
    2. Build context: format prior turns as conversation block
    3. Prepend context to voice_message before sending to hook
    4. Receive response (existing polling)
    5. Store new turn (transcript + response) in buffer
  - NEW: /api/voice/clear endpoint to reset conversation
  - NEW: /api/voice/history endpoint to retrieve current buffer

[Frontend: app.js]
  - NEW: "New Chat" button to call /api/voice/clear
  - NEW: Visual separator when conversation is cleared
```

**Why server-side buffer (not client-side)?**
- Single source of truth — no sync issues
- Works across page refreshes (in-memory is fine; we accept loss on container restart)
- Keeps the hook message construction logic in one place
- Client already displays the conversation — doesn't need to re-send history

**Why inject into prompt (not session reuse)?**
- OpenClaw bug #11665: hooks always create new sessions
- Injecting history as context is the documented workaround
- We control the format and can optimize token usage

---

### Task 1: ConversationBuffer class

**Files:**
- Create: `scripts/voice-gateway/conversation.py`

**Step 1: Create the conversation buffer module**

```python
"""
Conversation memory for Omni Vox multi-turn voice interactions.
Stores recent turns per session key, formats them for LLM context injection.
"""
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class Turn:
    """A single conversation turn (user + assistant)"""
    user: str
    assistant: str
    timestamp: float = field(default_factory=time.time)


class ConversationBuffer:
    """Per-session conversation history buffer.
    
    Maintains a rolling window of recent turns per session key.
    Thread-safe for async usage (GIL protects list operations).
    """
    
    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self._buffers: dict[str, list[Turn]] = {}
    
    def add_turn(self, session_key: str, user_text: str, assistant_text: str) -> None:
        """Record a completed turn"""
        if session_key not in self._buffers:
            self._buffers[session_key] = []
        buf = self._buffers[session_key]
        buf.append(Turn(user=user_text, assistant=assistant_text))
        # Trim to max
        if len(buf) > self.max_turns:
            self._buffers[session_key] = buf[-self.max_turns:]
    
    def get_history(self, session_key: str) -> list[Turn]:
        """Get all turns for a session"""
        return list(self._buffers.get(session_key, []))
    
    def format_context(self, session_key: str) -> Optional[str]:
        """Format conversation history as a context block for the LLM.
        
        Returns None if no history exists.
        """
        turns = self._buffers.get(session_key, [])
        if not turns:
            return None
        
        lines = ["[Previous conversation:]"]
        for turn in turns:
            lines.append(f"Chris: {turn.user}")
            lines.append(f"Omni: {turn.assistant}")
        
        return "\n".join(lines)
    
    def clear(self, session_key: Optional[str] = None) -> None:
        """Clear history for a session, or all sessions if key is None"""
        if session_key:
            self._buffers.pop(session_key, None)
        else:
            self._buffers.clear()
    
    def turn_count(self, session_key: str) -> int:
        """Get number of stored turns for a session"""
        return len(self._buffers.get(session_key, []))
```

**Step 2: Verify the file is syntactically correct**

Run: `cd /root/.openclaw/workspace/scripts/voice-gateway && python3 -c "from conversation import ConversationBuffer; b = ConversationBuffer(); b.add_turn('test', 'hello', 'hi'); assert b.format_context('test') is not None; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add scripts/voice-gateway/conversation.py
git commit -m "feat: add ConversationBuffer for multi-turn voice history"
```

---

### Task 2: Integrate ConversationBuffer into server.py

**Files:**
- Modify: `scripts/voice-gateway/server.py`

**Step 1: Import and initialize the buffer**

At the top of server.py, after the existing imports, add:

```python
from conversation import ConversationBuffer
```

In the global state section (after `hooks_token = None`), add:

```python
conversation = ConversationBuffer(max_turns=20)
```

**Step 2: Update call_openclaw to accept and inject history context**

In the `call_openclaw` function, change the `voice_message` construction to include conversation history:

Replace this line:
```python
    voice_message = f"[Voice conversation from Chris via Omni Vox. Respond naturally and concisely - this will be spoken aloud via TTS. Do NOT use any tools (exec, sonos-play, tts, etc.) — just return text. Audio playback is handled by Omni Vox, not by you. Do NOT echo or quote back what Chris said — the transcript is already displayed in the UI. Just respond directly.]\n\n{message}"
```

With:
```python
    # Build voice message with conversation context
    voice_prefix = "[Voice conversation from Chris via Omni Vox. Respond naturally and concisely - this will be spoken aloud via TTS. Do NOT use any tools (exec, sonos-play, tts, etc.) — just return text. Audio playback is handled by Omni Vox, not by you. Do NOT echo or quote back what Chris said — the transcript is already displayed in the UI. Just respond directly.]"
    
    # Inject conversation history if available
    history_context = conversation.format_context(session_key)
    if history_context:
        voice_message = f"{voice_prefix}\n\n{history_context}\n\nChris: {message}"
    else:
        voice_message = f"{voice_prefix}\n\n{message}"
```

Note: `session_key` is already computed above this line (the model-specific key like `hook:voice:haiku`).

**Step 3: Store the completed turn after getting the response**

In the `/api/voice` endpoint, after `llm_response, llm_usage = await call_openclaw(...)` and after computing `clean_response`, add this line (before the return statement, after the Obsidian log try/except):

```python
        # Store turn in conversation buffer for multi-turn context
        # Use the same session key logic as call_openclaw
        conv_session_key = HOOKS_SESSION_KEY
        if llm_model:
            short_name = llm_model.split("/")[-1].split("-")[1] if "/" in llm_model else llm_model
            conv_session_key = f"{HOOKS_SESSION_KEY}:{short_name}"
        conversation.add_turn(conv_session_key, transcript, clean_response)
```

**Step 4: Test manually**

Run: `cd /root/.openclaw/workspace/scripts/voice-gateway && python3 -c "
from conversation import ConversationBuffer
c = ConversationBuffer()
c.add_turn('hook:voice:haiku', 'what is 2+2', 'Four.')
c.add_turn('hook:voice:haiku', 'and times 3', 'Twelve.')
ctx = c.format_context('hook:voice:haiku')
assert 'what is 2+2' in ctx
assert 'Twelve' in ctx
assert 'Previous conversation' in ctx
print('Integration logic OK')
print(ctx)
"`
Expected: Shows formatted conversation context with both turns.

**Step 5: Commit**

```bash
git add scripts/voice-gateway/server.py
git commit -m "feat: integrate ConversationBuffer into voice endpoint for multi-turn context"
```

---

### Task 3: Add /api/voice/clear and /api/voice/history endpoints

**Files:**
- Modify: `scripts/voice-gateway/server.py`

**Step 1: Add the clear endpoint**

Add these two endpoints BEFORE the static file mount line (`app.mount("/", StaticFiles...`):

```python
@app.post("/api/voice/clear")
async def clear_conversation(llm_model: Optional[str] = Form(None)):
    """Clear conversation history for a model session"""
    if llm_model:
        short_name = llm_model.split("/")[-1].split("-")[1] if "/" in llm_model else llm_model
        session_key = f"{HOOKS_SESSION_KEY}:{short_name}"
        conversation.clear(session_key)
        return {"cleared": session_key, "status": "ok"}
    else:
        conversation.clear()
        return {"cleared": "all", "status": "ok"}


@app.get("/api/voice/history")
async def get_conversation_history(llm_model: Optional[str] = None):
    """Get conversation history for a model session"""
    if llm_model:
        short_name = llm_model.split("/")[-1].split("-")[1] if "/" in llm_model else llm_model
        session_key = f"{HOOKS_SESSION_KEY}:{short_name}"
    else:
        session_key = HOOKS_SESSION_KEY
    
    turns = conversation.get_history(session_key)
    return {
        "session_key": session_key,
        "turns": [{"user": t.user, "assistant": t.assistant, "timestamp": t.timestamp} for t in turns],
        "count": len(turns),
    }
```

**Step 2: Verify syntax**

Run: `cd /root/.openclaw/workspace/scripts/voice-gateway && python3 -c "import server; print('Imports OK')"`
Expected: Should print `Imports OK` (or at least not syntax error — startup events won't run)

**Step 3: Commit**

```bash
git add scripts/voice-gateway/server.py
git commit -m "feat: add /api/voice/clear and /api/voice/history endpoints"
```

---

### Task 4: Add "New Chat" button to frontend

**Files:**
- Modify: `scripts/voice-gateway/static/index.html`
- Modify: `scripts/voice-gateway/static/app.js`

**Step 1: Add the button to HTML**

In `index.html`, find the header section:
```html
        <div class="header">
            <h1>⚙️ Omni Vox</h1>
            <div class="subtitle">Machine Spirit Interface</div>
        </div>
```

Replace with:
```html
        <div class="header">
            <h1>⚙️ Omni Vox</h1>
            <div class="subtitle">Machine Spirit Interface</div>
            <button id="new-chat-btn" class="new-chat-btn" title="Start new conversation">New Chat</button>
        </div>
```

**Step 2: Add the button styling**

In `style.css`, add this rule (at the end of the file or after the `.header` styles):

```css
.new-chat-btn {
    position: absolute;
    top: 10px;
    right: 10px;
    background: rgba(255,255,255,0.1);
    border: 1px solid rgba(255,255,255,0.2);
    color: #ccc;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 0.8em;
    cursor: pointer;
    transition: all 0.2s;
}
.new-chat-btn:hover {
    background: rgba(255,255,255,0.2);
    color: #fff;
}
.header {
    position: relative;
}
.conversation .separator {
    text-align: center;
    color: rgba(255,255,255,0.3);
    font-size: 0.8em;
    padding: 8px 0;
    border-top: 1px solid rgba(255,255,255,0.1);
    margin: 8px 0;
}
```

**Step 3: Add JavaScript handler in app.js**

At the end of app.js, before the `setStatus('', 'Ready — hold to talk');` line, add:

```javascript
// --- New Chat ---

const newChatBtn = document.getElementById('new-chat-btn');

newChatBtn.addEventListener('click', async () => {
    try {
        const formData = new FormData();
        if (llmSelect.value) {
            formData.append('llm_model', llmSelect.value);
        }
        
        const res = await fetch(`${API}/api/voice/clear`, {
            method: 'POST',
            body: formData,
        });
        
        if (res.ok) {
            // Add visual separator
            const sep = document.createElement('div');
            sep.className = 'separator';
            sep.textContent = '— new conversation —';
            convoEl.appendChild(sep);
            convoEl.scrollTop = convoEl.scrollHeight;
            setStatus('', 'New conversation started');
        }
    } catch (err) {
        console.error('Failed to clear conversation:', err);
    }
});
```

**Step 4: Verify by checking HTML/JS syntax**

Run: `cd /root/.openclaw/workspace/scripts/voice-gateway && python3 -c "
import json
# Quick check that all files are readable
for f in ['static/index.html', 'static/app.js', 'static/style.css', 'server.py', 'conversation.py']:
    open(f).read()
    print(f'{f}: OK')
"`
Expected: All files OK

**Step 5: Commit**

```bash
git add scripts/voice-gateway/static/
git commit -m "feat: add New Chat button to clear conversation history"
```

---

### Task 5: Add turn count indicator to frontend

**Files:**
- Modify: `scripts/voice-gateway/static/app.js`
- Modify: `scripts/voice-gateway/static/index.html`

**Step 1: Add turn counter to the UI**

In `index.html`, after the subtitle div, add:
```html
            <div id="turn-count" class="turn-count"></div>
```

In `style.css`, add:
```css
.turn-count {
    font-size: 0.75em;
    color: rgba(255,255,255,0.4);
    margin-top: 2px;
}
```

**Step 2: Update app.js to show turn count from usage response**

In the response JSON from `/api/voice`, we need to include turn count. This requires a small backend change.

In `server.py`, in the `/api/voice` return dict, add `"turnCount"` to the returned JSON:

After the usage block in the return statement, add:
```python
            "turnCount": conversation.turn_count(conv_session_key),
```

Then in `app.js`, after `addMessage('assistant', ...)`, add:
```javascript
        // Update turn counter
        if (result.turnCount !== undefined) {
            document.getElementById('turn-count').textContent = 
                result.turnCount > 0 ? `${result.turnCount} turn${result.turnCount !== 1 ? 's' : ''} in conversation` : '';
        }
```

Also clear the counter in the new chat handler:
```javascript
        if (res.ok) {
            document.getElementById('turn-count').textContent = '';
            // ... existing separator code
```

**Step 3: Commit**

```bash
git add scripts/voice-gateway/
git commit -m "feat: show conversation turn count in UI"
```

---

### Task 6: Build, deploy, and verify

**Files:**
- No new files — deployment only

**Step 1: Build and deploy the container**

```bash
cd /root/.openclaw/workspace/scripts/voice-gateway
tar czf /tmp/omni-vox-build.tar.gz --exclude=venv --exclude=__pycache__ --exclude='*.pyc' Dockerfile .dockerignore requirements.txt server.py conversation.py static/
scp -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes /tmp/omni-vox-build.tar.gz omni@192.168.68.51:/tmp/
ssh -i /root/.openclaw/omni_ssh_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes omni@192.168.68.51 "
  cd /tmp/omni-vox-build && tar xzf /tmp/omni-vox-build.tar.gz && \
  docker build -q -t omni-vox:v1.1.0 . && \
  docker stop omni-vox && docker rm omni-vox && \
  docker run -d --name omni-vox --network host --restart unless-stopped \
    --env-file /mnt/user/appdata/omni-vox/.env \
    -v /mnt/user/appdata/openclaw/config/agents/main/sessions:/sessions:ro \
    -v /mnt/user/appdata/openclaw/config/workspace/SOUL.md:/app/SOUL.md:ro \
    omni-vox:v1.1.0 && \
  sleep 3 && echo 'deployed'
"
```

Note: Version bumped to v1.1.0 for the multi-turn feature. Also note `conversation.py` is now included in the tar.

**Step 2: Verify endpoints**

```bash
# Health check
curl -s http://192.168.68.51:7100/health | python3 -m json.tool

# History should be empty
curl -s "http://192.168.68.51:7100/api/voice/history?llm_model=anthropic/claude-haiku-4-5-20251001" | python3 -m json.tool

# LLM models should list 3
curl -s http://192.168.68.51:7100/api/llm/models | python3 -m json.tool
```

**Step 3: Manual integration test**

Use Omni Vox from phone/browser:
1. Send voice: "What is the capital of France?"
2. Expect response about Paris
3. Send voice: "And what language do they speak there?"
4. Expect response referencing France (proving multi-turn context works)
5. Check turn count shows "2 turns in conversation"
6. Click "New Chat"
7. Send voice: "What did I just ask about?"
8. Expect response saying it has no context (proving clear works)

**Step 4: Final commit**

```bash
git add -A
git commit -m "deploy: Omni Vox v1.1.0 with multi-turn voice conversations"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `conversation.py` | NEW — ConversationBuffer class with turn storage, formatting, clear |
| `server.py` | Import buffer, inject history into hook messages, store turns, new endpoints |
| `static/index.html` | New Chat button, turn count display |
| `static/style.css` | New Chat button styling, separator, turn count |
| `static/app.js` | New Chat handler, turn count update |

## What This Does NOT Do (Future Work)

- **Cross-channel context** — Discord and voice remain separate sessions
- **Persistence across container restarts** — buffer is in-memory only
- **Token-aware truncation** — sends all turns up to max_turns regardless of token count
- **Conversation summarization** — no compression of old turns
