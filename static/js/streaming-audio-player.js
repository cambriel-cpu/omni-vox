/**
 * True streaming audio player using Web Audio API scheduled playback
 * No buffering - plays chunks as they arrive
 */
class StreamingAudioPlayer {
    constructor() {
        this.audioContext = null;
        this.nextStartTime = 0;
        this.isPlaying = false;
        this.currentSessionId = null;
        this.scheduledSources = [];
        
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
        /**Initialize Web Audio API context with mobile-friendly handling*/
        try {
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
                    // Continue anyway - sometimes it works despite the error
                }
            }
            
            // Give it a moment to stabilize on mobile
            if (this.audioContext.state !== 'running') {
                console.log('[Audio] Waiting for AudioContext to stabilize...');
                await new Promise(resolve => setTimeout(resolve, 100));
            }
            
            console.log(`[Audio] AudioContext final state: ${this.audioContext.state}`);
            
            // Consider it successful if context exists, even if not running
            // Sometimes mobile browsers lie about the state
            const isReady = this.audioContext && this.audioContext.state !== 'closed';
            console.log(`[Audio] Initialization ${isReady ? 'successful' : 'failed'}`);
            return isReady;
            
        } catch (error) {
            console.error('[Audio] AudioContext initialization failed:', error);
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
        /**Add audio chunk for immediate playback - no buffering*/
        console.log(`[DEBUG-1] Received chunk: ${arrayBuffer.byteLength} bytes, isPlaying: ${this.isPlaying}, sessionId: ${this.currentSessionId}, lastSession: ${this.lastSessionId}`);
        console.log(`[DEBUG-2] AudioContext state: ${this.audioContext?.state}, currentTime: ${this.audioContext?.currentTime}`);
        
        // Accept chunks if actively playing OR if we recently ended a session (race condition handling)
        const recentlyEnded = this.lastSessionId && this.sessionEndTime && 
                              (performance.now() - this.sessionEndTime) < 2000; // 2 second grace period
        
        if (!this.isPlaying && !recentlyEnded) {
            console.warn('[DEBUG-WARN] Received audio chunk but not in streaming session and no recent session');
            return;
        }
        
        // If we're processing a chunk after session end, temporarily restore session for playback
        if (!this.isPlaying && recentlyEnded) {
            console.log('[DEBUG-3] Accepting chunk from recently ended session');
            this.currentSessionId = this.lastSessionId;
            this.isPlaying = true;
        }
        
        try {
            this.metrics.chunksReceived++;
            console.log(`[DEBUG-4] Starting chunk processing... chunks received: ${this.metrics.chunksReceived}`);
            
            // Layer 4: Web Audio API decodes
            console.log(`[DEBUG-5] Attempting decodeAudioData on ${arrayBuffer.byteLength} bytes...`);
            const decodeStartTime = performance.now();
            const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer.slice());
            const decodeTime = performance.now() - decodeStartTime;
            
            console.log(`[DEBUG-6] ✅ Decode successful: ${audioBuffer.duration.toFixed(3)}s, ${audioBuffer.sampleRate}Hz, ${audioBuffer.numberOfChannels} channels`);
            console.log(`[DEBUG-7] Decode took ${decodeTime.toFixed(1)}ms`);
            
            // Layer 5: Schedule for playback
            console.log(`[DEBUG-8] Scheduling audio buffer for playback...`);
            this.scheduleAudioBuffer(audioBuffer);
            console.log(`[DEBUG-9] ✅ Audio buffer scheduled successfully`);
            
        } catch (error) {
            console.error('[DEBUG-ERROR] Error processing audio chunk:', error);
            console.error(`[DEBUG-ERROR] Error name: ${error.name}, message: ${error.message}`);
            console.error(`[DEBUG-ERROR] Stack:`, error.stack);
            
            if (error.name === 'EncodingError') {
                console.error('[DEBUG-ERROR] Audio format not supported by browser');
            } else if (error.name === 'NotSupportedError') {
                console.error('[DEBUG-ERROR] Audio format or sample rate not supported');
            }
            
            this.onError?.(`Audio decode error: ${error.message}`);
        }
    }
    
    scheduleAudioBuffer(audioBuffer) {
        /**Schedule audio buffer for seamless playback*/
        console.log(`[DEBUG-10] Creating BufferSource...`);
        const source = this.audioContext.createBufferSource();
        
        console.log(`[DEBUG-11] Setting buffer (duration: ${audioBuffer.duration.toFixed(3)}s)...`);
        source.buffer = audioBuffer;
        
        console.log(`[DEBUG-12] Connecting to destination...`);
        source.connect(this.audioContext.destination);
        
        // Calculate when to start this chunk
        const startTime = Math.max(this.nextStartTime, this.audioContext.currentTime);
        console.log(`[DEBUG-13] Calculated start time: ${startTime.toFixed(3)}s (next: ${this.nextStartTime.toFixed(3)}s, current: ${this.audioContext.currentTime.toFixed(3)}s)`);
        
        try {
            console.log(`[DEBUG-14] Starting audio source at ${startTime.toFixed(3)}s...`);
            source.start(startTime);
            console.log(`[DEBUG-15] ✅ Audio source started successfully`);
            
            // Track the source for debugging
            this.scheduledSources.push(source);
            
            // Add ended handler for debugging
            source.onended = () => {
                console.log(`[DEBUG-16] ✅ Audio source finished playing at ${this.audioContext.currentTime.toFixed(3)}s`);
                this.metrics.chunksPlayed++;
                const index = this.scheduledSources.indexOf(source);
                if (index > -1) {
                    this.scheduledSources.splice(index, 1);
                }
                source.disconnect();
            };
            
        } catch (startError) {
            console.error('[DEBUG-ERROR] Failed to start audio source:', startError);
            console.error(`[DEBUG-ERROR] Start error name: ${startError.name}, message: ${startError.message}`);
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
        // Keep session info for a brief period to handle race conditions
        this.isPlaying = false;
        this.lastSessionId = this.currentSessionId;
        this.sessionEndTime = performance.now();
        this.currentSessionId = null;
        
        // Report metrics
        const totalTime = performance.now() - this.metrics.startTime;
        console.log(`Audio session complete: ${this.metrics.chunksReceived} chunks received, ${this.metrics.chunksPlayed} played, ${totalTime.toFixed(0)}ms total`);
        
        this.onAudioEnd?.(sessionId);
    }
    
    getPlaybackInfo() {
        /**Get current playback status*/
        return {
            isPlaying: this.isPlaying,
            sessionId: this.currentSessionId,
            scheduledChunks: this.scheduledSources.length,
            metrics: { ...this.metrics }
        };
    }
    
    // Event callbacks - set these from outside
    onAudioStart = null;
    onAudioEnd = null;
    onAudioStop = null;
    onError = null;
}

// Make available globally
window.StreamingAudioPlayer = StreamingAudioPlayer;