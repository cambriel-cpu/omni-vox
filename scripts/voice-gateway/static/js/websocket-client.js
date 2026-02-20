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
        
        this.ws.onmessage = (event) => {
            if (event.data instanceof ArrayBuffer) {
                // Binary audio data
                this.handleAudioChunk(event.data);
            } else {
                // JSON control message
                try {
                    const message = JSON.parse(event.data);
                    this.handleControlMessage(message);
                } catch (error) {
                    console.error('Invalid JSON message:', error);
                }
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
        if (this.audioPlayer && this.audioPlayer.isPlaying) {
            this.audioPlayer.addAudioChunk(arrayBuffer);
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
    
    async sendVoiceRequest(audioData) {
        await this.sendMessage({
            type: 'voice_request',
            audio_data: audioData
        });
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