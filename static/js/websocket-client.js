/**
 * WebSocket client for OmniVox with binary audio streaming
 */
class OmniVoxWebSocketClient {
    constructor(streamingAudioPlayer) {
        this.ws = null;
        this.audioPlayer = streamingAudioPlayer;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000; // Start with 1 second
        this.currentState = 'disconnected';
        this.lastAudioEndTime = 0; // Track when audio sessions end for race condition handling
        
        // Bind audio player events
        this.setupAudioPlayerEvents();
    }
    
    setupAudioPlayerEvents() {
        if (!this.audioPlayer) return;
        
        this.audioPlayer.onError = (error) => {
            this.onAudioError?.(error);
        };
    }
    
    async connect() {
        if (this.isConnected || this.currentState === 'connecting') {
            return;
        }
        
        this.currentState = 'connecting';
        this.onStateChange?.('connecting');
        
        try {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            
            this.ws = new WebSocket(wsUrl);
            this.setupWebSocketEvents();
            
            // Wait for connection or timeout
            await this.waitForConnection(5000);
            
        } catch (error) {
            console.error('WebSocket connection failed:', error);
            this.handleDisconnect();
        }
    }
    
    setupWebSocketEvents() {
        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.isConnected = true;
            this.currentState = 'connected';
            this.reconnectAttempts = 0;
            this.reconnectDelay = 1000;
            
            this.onStateChange?.('connected');
            this.onConnect?.();
        };
        
        this.ws.onmessage = async (event) => {
            if (event.data instanceof ArrayBuffer) {
                // Binary audio data (ArrayBuffer)
                console.log(`[WebSocket] Received ArrayBuffer: ${event.data.byteLength} bytes`);
                this.handleAudioChunk(event.data);
            } else if (event.data instanceof Blob) {
                // Binary audio data (Blob) - convert to ArrayBuffer
                console.log(`[WebSocket] Received Blob: ${event.data.size} bytes, converting...`);
                try {
                    const arrayBuffer = await event.data.arrayBuffer();
                    this.handleAudioChunk(arrayBuffer);
                } catch (error) {
                    console.error('Failed to convert Blob to ArrayBuffer:', error);
                }
            } else if (typeof event.data === 'string') {
                // JSON control message
                try {
                    const message = JSON.parse(event.data);
                    this.handleControlMessage(message);
                } catch (error) {
                    console.error('Invalid JSON message:', error);
                }
            } else {
                console.warn('Unknown WebSocket data type:', typeof event.data, event.data);
            }
        };
        
        this.ws.onclose = (event) => {
            console.log('WebSocket closed:', event.code, event.reason);
            this.handleDisconnect();
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.onError?.(`WebSocket error: ${error.message || 'Connection failed'}`);
        };
    }
    
    handleAudioChunk(arrayBuffer) {
        console.log(`[DEBUG-WS-1] Received binary audio chunk: ${arrayBuffer.byteLength} bytes`);
        console.log(`[DEBUG-WS-2] Audio player exists: ${!!this.audioPlayer}, isPlaying: ${this.audioPlayer?.isPlaying}, currentSession: ${this.audioPlayer?.currentSessionId}`);
        
        // Accept chunks if we have an audio player and either:
        // 1. Session is actively playing, OR  
        // 2. We recently received audio_end (handles race condition where audio_end arrives before binary chunk)
        const recentlyEnded = this.lastAudioEndTime > 0 && 
                              (Date.now() - this.lastAudioEndTime) < 2000; // 2 second grace period
        
        console.log(`[DEBUG-WS-3] RecentlyEnded: ${recentlyEnded} (lastEndTime: ${this.lastAudioEndTime}, timeSince: ${Date.now() - this.lastAudioEndTime}ms)`);
        
        if (this.audioPlayer && (this.audioPlayer.isPlaying || recentlyEnded)) {
            console.log('[DEBUG-WS-4] ✅ Processing audio chunk - forwarding to audio player');
            try {
                this.audioPlayer.addAudioChunk(arrayBuffer);
                console.log('[DEBUG-WS-5] ✅ Audio chunk forwarded to player successfully');
            } catch (error) {
                console.error('[DEBUG-WS-ERROR] Error forwarding chunk to audio player:', error);
            }
        } else {
            console.warn('[DEBUG-WS-WARN] Dropping audio chunk - player not ready or session too old');
            console.warn(`[DEBUG-WS-STATE] audioPlayer: ${!!this.audioPlayer}, isPlaying: ${this.audioPlayer?.isPlaying}, recentlyEnded: ${recentlyEnded}`);
        }
    }
    
    handleControlMessage(message) {
        console.log('Received control message:', message);
        
        switch (message.type) {
            case 'audio_start':
                if (this.audioPlayer) {
                    this.audioPlayer.startAudioSession(message.session_id);
                }
                this.onAudioStart?.(message);
                break;
                
            case 'audio_end':
                this.lastAudioEndTime = Date.now(); // Track when session ended for race condition handling
                if (this.audioPlayer) {
                    this.audioPlayer.endAudioSession(message.session_id);
                }
                this.onAudioEnd?.(message);
                break;
                
            case 'audio_cancelled':
                if (this.audioPlayer) {
                    this.audioPlayer.stopAudio();
                }
                this.onAudioCancelled?.(message);
                break;
                
            case 'transcript':
                this.onTranscript?.(message.text);
                break;
                
            case 'response_text':
                this.onResponseText?.(message.text);
                break;
                
            case 'sonos_played':
                this.onSonosPlayed?.(message);
                break;
                
            case 'error':
                this.onError?.(message.message);
                break;
                
            case 'ping':
                // Send pong response for keepalive
                this.sendMessage({ type: 'pong' }).catch(err => 
                    console.error('Failed to send pong:', err)
                );
                break;
                
            case 'pong':
                // Keepalive response
                break;
                
            default:
                console.warn('Unknown message type:', message.type);
        }
    }
    
    async sendMessage(message) {
        if (!this.isConnected) {
            throw new Error('WebSocket not connected');
        }
        
        try {
            this.ws.send(JSON.stringify(message));
        } catch (error) {
            console.error('Failed to send message:', error);
            throw error;
        }
    }
    
    async sendVoiceRequest(audioData, ttsProvider = 'kokoro', llmModel = null, speaker = null, volume = null) {
        const message = {
            type: 'voice_request',
            audio_data: audioData,
            tts_provider: ttsProvider,
            llm_model: llmModel
        };
        
        // Add Sonos speaker selection if specified
        if (speaker && speaker !== 'none') {
            const [speakerName, location] = speaker.split('|');
            message.sonos_speaker = speakerName;
            message.sonos_location = location || 'local';
            message.sonos_volume = volume;
        }
        
        await this.sendMessage(message);
    }
    
    async sendTTSRequest(text) {
        await this.sendMessage({
            type: 'stream_tts',
            text: text
        });
    }
    
    async cancelAudio() {
        await this.sendMessage({
            type: 'cancel'
        });
    }
    
    handleDisconnect() {
        this.isConnected = false;
        this.currentState = 'disconnected';
        
        if (this.audioPlayer && this.audioPlayer.isPlaying) {
            this.audioPlayer.stopAudio();
        }
        
        this.onStateChange?.('disconnected');
        this.onDisconnect?.();
        
        // Attempt reconnection
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.scheduleReconnect();
        } else {
            console.error('Max reconnection attempts reached');
            this.onError?.('Connection lost - max reconnection attempts reached');
        }
    }
    
    scheduleReconnect() {
        this.reconnectAttempts++;
        const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 30000);
        
        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        
        setTimeout(() => {
            if (!this.isConnected) {
                this.connect();
            }
        }, delay);
    }
    
    waitForConnection(timeoutMs) {
        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                reject(new Error('Connection timeout'));
            }, timeoutMs);
            
            const checkConnection = () => {
                if (this.isConnected) {
                    clearTimeout(timeout);
                    resolve();
                } else if (this.ws.readyState === WebSocket.CLOSED) {
                    clearTimeout(timeout);
                    reject(new Error('Connection closed'));
                } else {
                    setTimeout(checkConnection, 100);
                }
            };
            
            checkConnection();
        });
    }
    
    disconnect() {
        if (this.ws) {
            this.reconnectAttempts = this.maxReconnectAttempts; // Prevent reconnection
            this.ws.close(1000, 'Client disconnect');
        }
    }
    
    getState() {
        return {
            connected: this.isConnected,
            state: this.currentState,
            reconnectAttempts: this.reconnectAttempts
        };
    }
    
    // Event callbacks - set these from outside
    onConnect = null;
    onDisconnect = null;
    onError = null;
    onStateChange = null;
    onTranscript = null;
    onResponseText = null;
    onAudioStart = null;
    onAudioEnd = null;
    onAudioCancelled = null;
    onAudioError = null;
}

// Make available globally
window.OmniVoxWebSocketClient = OmniVoxWebSocketClient;