// Omni Vox — Push-to-talk voice client
const API = '';  // Same origin

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let audioContext = null;

// WebSocket streaming variables
let streamingAudioPlayer = null;
let wsClient = null;
let streamingMode = true; // Default to streaming

// DOM elements
const talkBtn = document.getElementById('talk-btn');
const statusEl = document.getElementById('status');
const convoEl = document.getElementById('conversation');
const speakerSelect = document.getElementById('speaker-select');
const volumeInput = document.getElementById('volume');
const ttsSelect = document.getElementById('tts-select');
const llmSelect = document.getElementById('llm-select');

// --- WebSocket Streaming Mode ---

async function initializeWebSocketMode() {
    if (wsClient) return; // Already initialized
    
    try {
        // Initialize WebSocket client first (doesn't require AudioContext)
        wsClient = new OmniVoxWebSocketClient(null); // Pass null for now, we'll set it later
        
        // Setup event handlers
        wsClient.onConnect = () => {
            updateStatus('WebSocket connected - streaming mode active');
            updateConnectionIndicator(true);
        };
        
        wsClient.onDisconnect = () => {
            updateStatus('WebSocket disconnected - check connection');
            updateConnectionIndicator(false);
        };
        
        wsClient.onError = (error) => {
            updateStatus(`WebSocket error: ${error}`);
            console.error('WebSocket error:', error);
        };
        
        wsClient.onTranscript = (text) => {
            updateStatus(`You said: "${text}"`);
        };
        
        wsClient.onResponseText = (text) => {
            updateStatus(`Omni: ${text.substring(0, 100)}${text.length > 100 ? '...' : ''}`);
        };
        
        wsClient.onAudioStart = () => {
            updateInterruptButton(true);
            setStatus('speaking', 'Streaming audio...');
        };
        
        wsClient.onAudioEnd = () => {
            updateInterruptButton(false);
            setStatus('', 'Ready');
            updateStatus('Ready for next message');
        };
        
        wsClient.onAudioCancelled = () => {
            updateInterruptButton(false);
            setStatus('', 'Ready');
            updateStatus('Audio interrupted');
        };
        
        // Connect WebSocket (this doesn't require AudioContext)
        await wsClient.connect();
        
        // Try to initialize audio components (this may fail on page load)
        await initializeAudioComponents();
        
    } catch (error) {
        console.error('Failed to initialize WebSocket mode:', error);
        updateStatus('WebSocket connection failed, using HTTP fallback');
    }
}

async function initializeAudioComponents() {
    try {
        if (!streamingAudioPlayer) {
            // Initialize streaming audio player
            streamingAudioPlayer = new StreamingAudioPlayer();
            const audioReady = await streamingAudioPlayer.initialize();
            
            if (audioReady) {
                // Link audio player to WebSocket client
                if (wsClient) {
                    wsClient.audioPlayer = streamingAudioPlayer;
                }
                updateStatus('Audio streaming ready');
                return true;
            } else {
                console.warn('Web Audio API not available - will initialize after user gesture');
                updateStatus('WebSocket connected - audio will initialize after first interaction');
                return false;
            }
        }
        return true;
    } catch (error) {
        console.warn('Audio initialization failed:', error);
        updateStatus('WebSocket connected - audio initialization failed, will retry after user gesture');
        return false;
    }
}

async function ensureAudioReady() {
    // Try to initialize audio if not already done (after user gesture)
    if (!streamingAudioPlayer || !streamingAudioPlayer.audioContext) {
        const audioReady = await initializeAudioComponents();
        if (!audioReady) {
            console.warn('Audio still not available, using HTTP fallback for this request');
            return false;
        }
    }
    return true;
}

function updateStatus(text) {
    // Helper function to update status without changing the main status element
    const statusText = document.getElementById('status-text');
    if (statusText) {
        statusText.textContent = text;
    }
}

// --- Audio Recording ---

async function initMediaRecorder() {
    const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: { 
            echoCancellation: true, 
            noiseSuppression: true,
            sampleRate: 16000 
        } 
    });
    
    // Try webm first, fall back to whatever's supported
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') 
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm') 
            ? 'audio/webm'
            : 'audio/mp4';
    
    mediaRecorder = new MediaRecorder(stream, { mimeType });
    
    mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
    };
    
    return mediaRecorder;
}

function startRecording() {
    if (!mediaRecorder || mediaRecorder.state === 'recording') return;
    audioChunks = [];
    mediaRecorder.start(100);  // 100ms chunks
    isRecording = true;
    talkBtn.classList.add('active');
    setStatus('listening', 'Listening...');
}

function stopRecording() {
    return new Promise((resolve) => {
        if (!mediaRecorder || mediaRecorder.state !== 'recording') {
            resolve(null);
            return;
        }
        mediaRecorder.onstop = () => {
            const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
            audioChunks = [];
            isRecording = false;
            talkBtn.classList.remove('active');
            resolve(blob);
        };
        mediaRecorder.stop();
    });
}

// --- API Calls ---

async function sendVoice(audioBlob) {
    const formData = new FormData();
    
    // Determine extension from mime type
    const ext = audioBlob.type.includes('webm') ? 'webm' : 'mp4';
    formData.append('audio', audioBlob, `voice.${ext}`);
    
    // TTS provider
    formData.append('tts_provider', ttsSelect.value || 'kokoro');
    
    // LLM model
    if (llmSelect.value) {
        formData.append('llm_model', llmSelect.value);
    }
    
    // Sonos routing
    const speaker = speakerSelect.value;
    if (speaker && speaker !== 'none') {
        const [name, location] = speaker.split('|');
        formData.append('sonos_speaker', name);
        formData.append('sonos_location', location || 'local');
        formData.append('sonos_volume', volumeInput.value || '65');
    }
    
    const response = await fetch(`${API}/api/voice`, {
        method: 'POST',
        body: formData,
    });
    
    if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(err.detail || `HTTP ${response.status}`);
    }
    
    return response.json();
}

// --- WebSocket vs HTTP Processing ---

async function processRecordingWebSocket(audioBlob) {
    if (!wsClient || !wsClient.isConnected) {
        throw new Error('WebSocket not connected');
    }
    
    try {
        // Convert audio blob to base64
        const arrayBuffer = await audioBlob.arrayBuffer();
        const base64Audio = btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)));
        
        // Send via WebSocket
        await wsClient.sendVoiceRequest(base64Audio);
        
        updateStatus("Processing voice (streaming)...");
        
    } catch (error) {
        console.error('WebSocket voice processing error:', error);
        throw error;
    }
}

async function processRecordingHTTP(audioBlob) {
    updateStatus("Processing voice (HTTP mode)...");
    
    try {
        const result = await sendVoice(audioBlob);
        
        // Show transcript
        addMessage('user', `"${result.transcript}"`);
        
        // Show response
        addMessage('assistant', result.response, result.timing, result.usage);
        
        // Update turn counter
        if (result.turnCount !== undefined) {
            document.getElementById('turn-count').textContent = 
                result.turnCount > 0 ? `${result.turnCount} turn${result.turnCount !== 1 ? 's' : ''} in conversation` : '';
        }
        
        // Play audio — skip local playback if Sonos speaker selected
        const usingSonos = speakerSelect.value && speakerSelect.value !== 'none';
        if (result.audio && !usingSonos) {
            setStatus('speaking', 'Speaking...');
            await playAudioBase64(result.audio);
        } else if (usingSonos) {
            const speakerName = speakerSelect.value.split('|')[0];
            setStatus('speaking', `Playing on ${speakerName}...`);
            // Sonos playback is fire-and-forget on the server side
            await new Promise(r => setTimeout(r, 2000));
        }
        
        return result;
        
    } catch (error) {
        console.error('HTTP processing error:', error);
        throw error;
    }
}

// --- Audio Playback ---

function playAudioBase64(b64) {
    return new Promise((resolve, reject) => {
        const audio = new Audio(`data:audio/mpeg;base64,${b64}`);
        audio.onended = resolve;
        audio.onerror = reject;
        audio.play().catch(reject);
    });
}

// --- UI ---

function setStatus(state, text) {
    statusEl.textContent = text || '';
    statusEl.className = `status ${state}`;
    
    talkBtn.classList.remove('active', 'thinking', 'speaking');
    if (state === 'thinking') talkBtn.classList.add('thinking');
    if (state === 'speaking') talkBtn.classList.add('speaking');
}

function addMessage(role, text, timing, usage) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    
    let html = text;
    if (timing) {
        const parts = [];
        if (timing.transcribe) parts.push(`stt: ${timing.transcribe}s`);
        if (timing.llm) parts.push(`llm: ${timing.llm}s`);
        if (timing.tts) parts.push(`tts: ${timing.tts}s`);
        if (timing.sonos) parts.push(`sonos: ${timing.sonos}s`);
        const total = Object.values(timing)
            .filter(v => typeof v === 'number')
            .reduce((a, b) => a + b, 0);
        parts.push(`total: ${total.toFixed(2)}s`);
        html += `<div class="timing">${parts.join(' · ')}</div>`;
    }
    if (usage) {
        const uParts = [];
        uParts.push(`in: ${usage.input.toLocaleString()}`);
        uParts.push(`out: ${usage.output.toLocaleString()}`);
        if (usage.cacheRead) uParts.push(`cache: ${usage.cacheRead.toLocaleString()}`);
        uParts.push(`total: ${usage.total.toLocaleString()}`);
        if (usage.cost) uParts.push(`$${usage.cost.toFixed(4)}`);
        if (usage.ttsChars) {
            uParts.push(`tts: ${usage.ttsChars} chars`);
            if (usage.ttsProvider === 'elevenlabs') {
                uParts.push(`~$${(usage.ttsChars * 0.0003).toFixed(4)} EL`);
            }
        }
        html += `<div class="timing">${uParts.join(' · ')}</div>`;
    }
    
    div.innerHTML = html;
    convoEl.appendChild(div);
    convoEl.scrollTop = convoEl.scrollHeight;
}

// --- Talk Button Handlers ---

async function handleTalkStart(e) {
    e.preventDefault();
    if (talkBtn.disabled) return;
    
    // Initialize audio components after first user gesture if needed
    if (wsClient && wsClient.isConnected && (!streamingAudioPlayer || !streamingAudioPlayer.audioContext)) {
        try {
            await initializeAudioComponents();
        } catch (error) {
            console.warn('Audio initialization after user gesture failed:', error);
        }
    }
    
    if (!mediaRecorder) {
        try {
            await initMediaRecorder();
        } catch (err) {
            setStatus('error', 'Mic access denied');
            return;
        }
    }
    
    startRecording();
}

async function handleTalkEnd(e) {
    e.preventDefault();
    if (!isRecording) return;
    
    const audioBlob = await stopRecording();
    if (!audioBlob || audioBlob.size < 1000) {
        setStatus('', 'Hold longer to record');
        return;
    }
    
    talkBtn.disabled = true;
    setStatus('thinking', 'Processing...');
    
    try {
        // Check if WebSocket streaming is available and enabled
        if (streamingMode && wsClient && wsClient.isConnected) {
            // Ensure audio is ready for streaming (may initialize after user gesture)
            await ensureAudioReady();
            
            // Process via WebSocket
            await processRecordingWebSocket(audioBlob);
            // WebSocket mode - UI updates handled by event callbacks
        } else {
            // HTTP fallback mode
            const reason = !streamingMode ? 'streaming disabled' : 
                          !wsClient ? 'WebSocket not initialized' :
                          !wsClient.isConnected ? 'WebSocket not connected' : 'unknown';
            console.log(`Using HTTP mode: ${reason}`);
            await processRecordingHTTP(audioBlob);
            setStatus('', 'Ready');
        }
    } catch (err) {
        console.error('Recording processing failed:', err);
        setStatus('error', err.message);
        addMessage('assistant', `⚠ Error: ${err.message}`);
        
        // Try fallback if WebSocket failed
        if (streamingMode && err.message.includes('WebSocket')) {
            console.log('Trying HTTP fallback...');
            try {
                await processRecordingHTTP(audioBlob);
                setStatus('', 'Ready');
                updateStatus('Fallback to HTTP mode successful');
            } catch (fallbackError) {
                console.error('Fallback also failed:', fallbackError);
                updateStatus(`Both streaming and HTTP failed: ${fallbackError.message}`);
                setTimeout(() => setStatus('', 'Ready'), 3000);
            }
        } else {
            setTimeout(() => setStatus('', 'Ready'), 3000);
        }
    } finally {
        talkBtn.disabled = false;
    }
}

// --- Sonos Discovery ---

async function discoverSpeakers() {
    try {
        const res = await fetch(`${API}/api/sonos/discover`, { method: 'POST' });
        const data = await res.json();
        
        // Clear and rebuild speaker list
        speakerSelect.innerHTML = '<option value="none">Phone speaker</option>';
        for (const speaker of data.speakers) {
            const opt = document.createElement('option');
            opt.value = `${speaker.name}|${speaker.location}`;
            opt.textContent = `${speaker.name} (${speaker.location})`;
            speakerSelect.appendChild(opt);
        }
    } catch (err) {
        console.error('Speaker discovery failed:', err);
    }
}

// --- Streaming UI Controls ---

function addStreamingControls() {
    const controlsDiv = document.querySelector('.controls') || document.body;
    
    // Connection status indicator
    const statusDiv = document.createElement('div');
    statusDiv.innerHTML = `
        <div class="connection-status">
            <span id="connectionIndicator" class="indicator disconnected">●</span>
            <span id="connectionText">Connecting...</span>
        </div>
        
        <div class="streaming-controls">
            <label>
                <input type="checkbox" id="streamingModeToggle" ${streamingMode ? 'checked' : ''}> 
                Streaming Mode
            </label>
            <button id="interruptButton" disabled>⏹️ Stop Audio</button>
        </div>
        
        <div id="status-text" class="status-text"></div>
    `;
    controlsDiv.appendChild(statusDiv);
    
    // Add CSS
    const style = document.createElement('style');
    style.textContent = `
        .connection-status {
            margin: 10px 0;
            padding: 5px;
            background: #f0f0f0;
            border-radius: 3px;
            font-size: 14px;
        }
        
        .indicator {
            font-size: 12px;
            margin-right: 5px;
        }
        
        .indicator.connected { color: #00ff00; }
        .indicator.connecting { color: #ffaa00; }
        .indicator.disconnected { color: #ff0000; }
        
        .streaming-controls {
            margin: 10px 0;
        }
        
        .streaming-controls label {
            margin-right: 10px;
        }
        
        .status-text {
            margin: 5px 0;
            font-style: italic;
            color: #666;
            min-height: 1.2em;
        }
        
        #interruptButton:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
    `;
    document.head.appendChild(style);
    
    // Event handlers
    document.getElementById('streamingModeToggle').onchange = (e) => {
        streamingMode = e.target.checked;
        updateStatus(streamingMode ? 'Streaming mode enabled' : 'HTTP mode enabled');
    };
    
    document.getElementById('interruptButton').onclick = async () => {
        if (wsClient && wsClient.isConnected) {
            try {
                await wsClient.cancelAudio();
            } catch (error) {
                console.error('Failed to cancel audio:', error);
            }
        }
        
        if (streamingAudioPlayer) {
            streamingAudioPlayer.stopAudio();
        }
    };
}

function updateConnectionIndicator(connected) {
    const indicator = document.getElementById('connectionIndicator');
    const text = document.getElementById('connectionText');
    
    if (connected) {
        indicator.className = 'indicator connected';
        text.textContent = 'Connected (Streaming)';
    } else {
        indicator.className = 'indicator disconnected';
        text.textContent = 'Disconnected (HTTP fallback)';
    }
}

function updateInterruptButton(enabled) {
    const button = document.getElementById('interruptButton');
    if (button) {
        button.disabled = !enabled;
        button.textContent = enabled ? '⏹️ Stop Audio' : '⏸️ No Audio';
    }
}

// --- Init ---

// Touch events for mobile push-to-talk
talkBtn.addEventListener('pointerdown', handleTalkStart);
talkBtn.addEventListener('pointerup', handleTalkEnd);
talkBtn.addEventListener('pointerleave', handleTalkEnd);
talkBtn.addEventListener('pointercancel', handleTalkEnd);

// Prevent context menu on long press
talkBtn.addEventListener('contextmenu', e => e.preventDefault());

// --- TTS Provider Discovery ---

async function discoverTTSProviders() {
    try {
        const res = await fetch(`${API}/api/tts/providers`);
        const data = await res.json();
        
        ttsSelect.innerHTML = '';
        for (const p of data.providers) {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name;
            ttsSelect.appendChild(opt);
        }
        
        // Restore saved preference
        const saved = localStorage.getItem('omni-vox-tts');
        if (saved && [...ttsSelect.options].some(o => o.value === saved)) {
            ttsSelect.value = saved;
        }
    } catch (err) {
        console.error('TTS provider discovery failed:', err);
    }
}

ttsSelect.addEventListener('change', () => {
    localStorage.setItem('omni-vox-tts', ttsSelect.value);
});

// --- LLM Model Discovery ---

async function discoverLLMModels() {
    try {
        const res = await fetch(`${API}/api/llm/models`);
        const data = await res.json();
        
        llmSelect.innerHTML = '';
        for (const m of data.models) {
            const opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = m.name;
            llmSelect.appendChild(opt);
        }
        
        // Restore saved preference
        const saved = localStorage.getItem('omni-vox-llm');
        if (saved && [...llmSelect.options].some(o => o.value === saved)) {
            llmSelect.value = saved;
        }
    } catch (err) {
        console.error('LLM model discovery failed:', err);
    }
}

llmSelect.addEventListener('change', () => {
    localStorage.setItem('omni-vox-llm', llmSelect.value);
});

// Initialize WebSocket streaming mode and UI
async function initializeApp() {
    addStreamingControls();
    await initializeWebSocketMode();
}

// Discover speakers, TTS providers, and LLM models on load
discoverSpeakers();
discoverTTSProviders();
discoverLLMModels();

// Initialize streaming mode when DOM is ready
window.addEventListener('DOMContentLoaded', initializeApp);

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
            document.getElementById('turn-count').textContent = '';
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

setStatus('', 'Ready — hold to talk');
