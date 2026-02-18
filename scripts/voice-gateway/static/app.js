// Omni Vox — Push-to-talk voice client
const API = '';  // Same origin

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let audioContext = null;

// DOM elements
const talkBtn = document.getElementById('talk-btn');
const statusEl = document.getElementById('status');
const convoEl = document.getElementById('conversation');
const speakerSelect = document.getElementById('speaker-select');
const volumeInput = document.getElementById('volume');
const ttsSelect = document.getElementById('tts-select');
const llmSelect = document.getElementById('llm-select');

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
        const result = await sendVoice(audioBlob);
        
        // Show transcript
        addMessage('user', `"${result.transcript}"`);
        
        // Show response
        addMessage('assistant', result.response, result.timing, result.usage);
        
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
        
        setStatus('', 'Ready');
    } catch (err) {
        setStatus('error', err.message);
        addMessage('assistant', `⚠ Error: ${err.message}`);
        setTimeout(() => setStatus('', 'Ready'), 3000);
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

// Discover speakers, TTS providers, and LLM models on load
discoverSpeakers();
discoverTTSProviders();
discoverLLMModels();

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

setStatus('', 'Ready — hold to talk');
