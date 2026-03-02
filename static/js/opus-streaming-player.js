/**
 * Opus streaming audio player using opus-stream-decoder WebAssembly
 * Handles Ogg/Opus chunks that can't be decoded by Web Audio API decodeAudioData()
 */
class OpusStreamingPlayer {
    constructor() {
        this.audioContext = null;
        this.nextStartTime = 0;
        this.isPlaying = false;
        this.currentSessionId = null;
        this.scheduledSources = [];
        
        // Opus decoder
        this.opusDecoder = null;
        this.decoderReady = false;
        
        // Race condition handling
        this.lastSessionId = null;
        this.sessionEndTime = null;
        
        // Performance monitoring
        this.metrics = {
            chunksReceived: 0,
            chunksPlayed: 0,
            totalLatency: 0,
            startTime: null
        };
    }
    
    async initialize() {
        /**Initialize Web Audio API context and Opus decoder*/
        try {
            // Initialize AudioContext
            if (!this.audioContext) {
                console.log('[Audio] Creating AudioContext...');
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
            
            console.log(`[Audio] AudioContext state: ${this.audioContext.state}`);
            
            // Mobile Chrome often starts in suspended state
            if (this.audioContext.state === 'suspended') {
                console.log('[Audio] AudioContext suspended - attempting resume...');
                try {
                    await this.audioContext.resume();
                    console.log(`[Audio] AudioContext resumed successfully: ${this.audioContext.state}`);
                } catch (resumeError) {
                    console.warn('[Audio] Failed to resume AudioContext:', resumeError);
                }
            }
            
            // Initialize Opus decoder
            console.log('[Opus] Initializing WebAssembly decoder...');
            this.opusDecoder = new OpusStreamDecoder({
                onDecode: this.onOpusDecoded.bind(this)
            });
            
            // Wait for decoder to be ready
            await this.opusDecoder.ready;
            this.decoderReady = true;
            console.log('[Opus] WebAssembly decoder ready');
            
            const isReady = this.audioContext && this.decoderReady;
            console.log(`[Audio] Initialization ${isReady ? 'successful' : 'failed'}`);
            return isReady;
            
        } catch (error) {
            console.error('[Audio] Initialization failed:', error);
            return false;
        }
    }
    
    startAudioSession(sessionId) {
        /**Start new audio streaming session*/
        this.currentSessionId = sessionId;
        this.isPlaying = true;
        this.nextStartTime = this.audioContext.currentTime;
        this.scheduledSources = [];
        
        // Clear any previous session race condition state
        this.lastSessionId = null;
        this.sessionEndTime = null;
        
        // Reset metrics
        this.metrics = {
            chunksReceived: 0,
            chunksPlayed: 0,
            totalLatency: 0,
            startTime: performance.now()
        };
        
        this.onAudioStart?.(sessionId);
        console.log(`Started audio session: ${sessionId}`);
    }
    
    async addAudioChunk(arrayBuffer) {
        /**Add Opus audio chunk for decoding and playback*/
        console.log(`[DEBUG-1] Received Opus chunk: ${arrayBuffer.byteLength} bytes, isPlaying: ${this.isPlaying}, sessionId: ${this.currentSessionId}`);
        
        // Accept chunks if actively playing OR if we recently ended a session (race condition handling)
        const recentlyEnded = this.lastSessionId && this.sessionEndTime && 
                              (performance.now() - this.sessionEndTime) < 2000;
        
        if (!this.isPlaying && !recentlyEnded) {
            console.warn('[DEBUG-WARN] Received audio chunk but not in streaming session and no recent session');
            return;
        }
        
        // If we're processing a chunk after session end, temporarily restore session
        if (!this.isPlaying && recentlyEnded) {
            console.log('[DEBUG-3] Accepting chunk from recently ended session');
            this.currentSessionId = this.lastSessionId;
            this.isPlaying = true;
        }
        
        try {
            this.metrics.chunksReceived++;
            console.log(`[DEBUG-4] Starting Opus decode... chunks received: ${this.metrics.chunksReceived}`);
            
            if (!this.decoderReady) {
                console.error('[DEBUG-ERROR] Opus decoder not ready');
                return;
            }
            
            // Convert ArrayBuffer to Uint8Array for opus-stream-decoder
            const uint8Data = new Uint8Array(arrayBuffer);
            console.log(`[DEBUG-5] Feeding ${uint8Data.length} bytes to Opus decoder...`);
            
            // Decode the chunk - this will call onOpusDecoded callback
            try {
                await this.opusDecoder.ready;
                this.opusDecoder.decode(uint8Data);
                console.log(`[DEBUG-6] ✅ Opus chunk fed to decoder successfully`);
            } catch (decodeError) {
                console.error('[DEBUG-ERROR] Opus decode failed:', decodeError);
                console.error('[Opus] Decode error - resetting decoder and ending session');
                this.resetDecoder();
                if (this.currentSessionId) {
                    this.endAudioSession(this.currentSessionId);
                }
                return;
            }
            
        } catch (error) {
            console.error('[DEBUG-ERROR] Error processing Opus chunk:', error);
            console.error(`[DEBUG-ERROR] Error name: ${error.name}, message: ${error.message}`);
            this.onError?.(`Opus decode error: ${error.message}`);
        }
    }
    
    onOpusDecoded({left, right, samplesDecoded, sampleRate}) {
        /**Callback fired by opus-stream-decoder when PCM data is ready*/
        if (samplesDecoded === 0) return;
        
        // Check for Opus decoder errors (negative sample counts)
        if (samplesDecoded < 0) {
            console.error(`[Opus] Decoder error: ${samplesDecoded} samples (negative = error code)`);
            console.error('[Opus] Stream corruption detected - resetting decoder and ending session');
            this.resetDecoder();
            if (this.currentSessionId) {
                this.endAudioSession(this.currentSessionId);
            }
            return;
        }
        
        // Validate reasonable sample count (Web Audio API limits)
        if (samplesDecoded > 1000000) {  // ~20 seconds at 48kHz
            console.error(`[Opus] Invalid sample count: ${samplesDecoded} (too large)`);
            console.error('[Opus] Invalid sample count - resetting decoder and ending session');
            this.resetDecoder();
            if (this.currentSessionId) {
                this.endAudioSession(this.currentSessionId);
            }
            return;
        }
        
        console.log(`[DEBUG-7] Decoded ${samplesDecoded} samples at ${sampleRate}Hz`);
        
        try {
            // Create AudioBuffer from decoded PCM data
            const audioBuffer = this.audioContext.createBuffer(2, samplesDecoded, sampleRate);
            
            // Copy decoded PCM data to AudioBuffer
            audioBuffer.copyToChannel(left, 0);
            audioBuffer.copyToChannel(right, 1);
            
            console.log(`[DEBUG-8] Created AudioBuffer: ${audioBuffer.duration.toFixed(3)}s, ${audioBuffer.sampleRate}Hz, ${audioBuffer.numberOfChannels} channels`);
            
            // Schedule for playback
            this.scheduleAudioBuffer(audioBuffer);
            
        } catch (error) {
            console.error('[DEBUG-ERROR] Error creating AudioBuffer from PCM:', error);
            this.onError?.(`PCM buffer error: ${error.message}`);
        }
    }
    
    scheduleAudioBuffer(audioBuffer) {
        /**Schedule audio buffer for seamless playback (same logic as before)*/
        console.log(`[DEBUG-10] Creating BufferSource...`);
        const source = this.audioContext.createBufferSource();
        
        console.log(`[DEBUG-11] Setting buffer (duration: ${audioBuffer.duration.toFixed(3)}s)...`);
        source.buffer = audioBuffer;
        
        console.log(`[DEBUG-12] Connecting to destination...`);
        source.connect(this.audioContext.destination);
        
        // Calculate when to start this chunk
        const startTime = Math.max(this.nextStartTime, this.audioContext.currentTime);
        console.log(`[DEBUG-13] Calculated start time: ${startTime.toFixed(3)}s`);
        
        try {
            console.log(`[DEBUG-14] Starting audio source at ${startTime.toFixed(3)}s...`);
            source.start(startTime);
            console.log(`[DEBUG-15] ✅ Audio source started successfully`);
            
            // Track the source for debugging
            this.scheduledSources.push(source);
            
            // Add ended handler for debugging
            source.onended = () => {
                console.log(`[DEBUG-16] ✅ Audio source finished playing`);
                this.metrics.chunksPlayed++;
                const index = this.scheduledSources.indexOf(source);
                if (index > -1) {
                    this.scheduledSources.splice(index, 1);
                }
                source.disconnect();
            };
            
        } catch (startError) {
            console.error('[DEBUG-ERROR] Failed to start audio source:', startError);
        }
        
        // Update next start time for seamless playback
        this.nextStartTime = startTime + audioBuffer.duration;
        console.log(`[DEBUG-17] Next start time updated to: ${this.nextStartTime.toFixed(3)}s`);
    }
    
    stopAudio() {
        /**Stop all audio playback immediately*/
        if (!this.isPlaying) return;
        
        // Stop all scheduled sources
        this.scheduledSources.forEach(source => {
            try {
                source.stop();
                source.disconnect();
            } catch (e) {
                // Source may already be stopped
            }
        });
        
        this.scheduledSources = [];
        this.isPlaying = false;
        this.currentSessionId = null;
        
        // Reset Opus decoder for next session
        if (this.opusDecoder && this.decoderReady) {
            try {
                this.opusDecoder.ready.then(() => this.opusDecoder.free());
            } catch (e) {
                console.warn('Error freeing Opus decoder:', e);
            }
        }
        
        this.onAudioStop?.();
        console.log('Stopped audio playback');
    }
    
    endAudioSession(sessionId) {
        /**Clean end of audio session*/
        if (this.currentSessionId !== sessionId) {
            console.warn(`Session ID mismatch: expected ${this.currentSessionId}, got ${sessionId}`);
            return;
        }
        
        // Don't stop immediately - let scheduled audio finish naturally
        this.isPlaying = false;
        this.lastSessionId = this.currentSessionId;
        this.sessionEndTime = performance.now();
        this.currentSessionId = null;
        
        // Report metrics
        const totalTime = performance.now() - this.metrics.startTime;
        console.log(`Audio session complete: ${this.metrics.chunksReceived} chunks received, ${this.metrics.chunksPlayed} played, ${totalTime.toFixed(0)}ms total`);
        
        this.onAudioEnd?.(sessionId);
    }
    
    async resetDecoder() {
        /**Reset the Opus decoder to recover from stream corruption*/
        console.log('[Opus] Resetting decoder due to stream corruption...');
        
        try {
            // Mark decoder as not ready
            this.decoderReady = false;
            
            // Try to free the existing decoder
            if (this.opusDecoder) {
                try {
                    this.opusDecoder.free?.();
                } catch (e) {
                    console.warn('Error freeing corrupted decoder:', e);
                }
            }
            
            // Create new decoder instance
            this.opusDecoder = new OpusStreamDecoder({
                onDecode: this.onOpusDecoded.bind(this)
            });
            
            // Wait for new decoder to be ready
            await this.opusDecoder.ready;
            this.decoderReady = true;
            
            console.log('[Opus] Decoder reset successfully');
            
        } catch (error) {
            console.error('[Opus] Failed to reset decoder:', error);
            this.decoderReady = false;
        }
    }
    
    getPlaybackInfo() {
        /**Get current playback status*/
        return {
            isPlaying: this.isPlaying,
            sessionId: this.currentSessionId,
            scheduledChunks: this.scheduledSources.length,
            decoderReady: this.decoderReady,
            metrics: { ...this.metrics }
        };
    }
    
    // Event callbacks
    onAudioStart = null;
    onAudioEnd = null;  
    onAudioStop = null;
    onError = null;
}

// Make available globally
window.OpusStreamingPlayer = OpusStreamingPlayer;