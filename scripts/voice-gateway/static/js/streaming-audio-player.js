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
        
        // Performance monitoring
        this.metrics = {
            chunksReceived: 0,
            chunksPlayed: 0,
            totalLatency: 0,
            startTime: null
        };
    }
    
    async initialize() {
        /**Initialize Web Audio API context*/
        if (!this.audioContext) {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        
        // Resume if suspended (required for mobile)
        if (this.audioContext.state === 'suspended') {
            await this.audioContext.resume();
        }
        
        return this.audioContext.state === 'running';
    }
    
    startAudioSession(sessionId) {
        /**Start new audio streaming session*/
        this.currentSessionId = sessionId;
        this.isPlaying = true;
        this.nextStartTime = this.audioContext.currentTime;
        this.scheduledSources = [];
        
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
        if (!this.isPlaying || !this.currentSessionId) {
            console.warn('Received audio chunk but not in streaming session');
            return;
        }
        
        try {
            this.metrics.chunksReceived++;
            
            // Decode audio chunk
            const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer.slice());
            
            // Schedule for immediate playback
            this.scheduleAudioBuffer(audioBuffer);
            
        } catch (error) {
            console.error('Error processing audio chunk:', error);
            this.onError?.(`Audio decode error: ${error.message}`);
        }
    }
    
    scheduleAudioBuffer(audioBuffer) {
        /**Schedule audio buffer for seamless playback*/
        const source = this.audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(this.audioContext.destination);
        
        // Calculate when to start this chunk
        const startTime = Math.max(this.nextStartTime, this.audioContext.currentTime);
        source.start(startTime);
        
        // Update next start time for seamless playback
        this.nextStartTime = startTime + audioBuffer.duration;
        
        // Track scheduled source for cleanup
        this.scheduledSources.push(source);
        
        // Cleanup when finished
        source.onended = () => {
            this.metrics.chunksPlayed++;
            const index = this.scheduledSources.indexOf(source);
            if (index > -1) {
                this.scheduledSources.splice(index, 1);
            }
            source.disconnect();
        };
        
        console.log(`Scheduled audio chunk: duration=${audioBuffer.duration.toFixed(3)}s, startTime=${startTime.toFixed(3)}s`);
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
        this.isPlaying = false;
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