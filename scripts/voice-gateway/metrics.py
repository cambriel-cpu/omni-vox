from prometheus_client import Counter, Histogram, Gauge, start_http_server
import time
import logging

logger = logging.getLogger(__name__)

# WebSocket metrics
websocket_connections_total = Counter('websocket_connections_total', 'Total WebSocket connections')
websocket_connections_active = Gauge('websocket_connections_active', 'Active WebSocket connections')
websocket_disconnections_total = Counter('websocket_disconnections_total', 'Total WebSocket disconnections', ['reason'])

# Message metrics
messages_received_total = Counter('messages_received_total', 'Total messages received', ['message_type'])
messages_sent_total = Counter('messages_sent_total', 'Total messages sent', ['message_type'])
message_validation_failures_total = Counter('message_validation_failures_total', 'Message validation failures', ['error_type'])

# Audio streaming metrics  
audio_streams_started_total = Counter('audio_streams_started_total', 'Total audio streams started')
audio_streams_completed_total = Counter('audio_streams_completed_total', 'Total audio streams completed')
audio_streams_cancelled_total = Counter('audio_streams_cancelled_total', 'Total audio streams cancelled')
audio_chunk_latency_seconds = Histogram('audio_chunk_latency_seconds', 'Time to send audio chunk')
audio_stream_duration_seconds = Histogram('audio_stream_duration_seconds', 'Audio stream duration')

# TTS metrics
tts_requests_total = Counter('tts_requests_total', 'Total TTS requests')
tts_request_duration_seconds = Histogram('tts_request_duration_seconds', 'TTS request duration')
tts_failures_total = Counter('tts_failures_total', 'TTS request failures', ['error_type'])

class MetricsCollector:
    """Centralized metrics collection for OmniVox"""
    
    def __init__(self):
        self.audio_stream_start_times = {}
    
    def websocket_connected(self):
        websocket_connections_total.inc()
        websocket_connections_active.inc()
    
    def websocket_disconnected(self, reason="normal"):
        websocket_connections_active.dec()
        websocket_disconnections_total.labels(reason=reason).inc()
    
    def message_received(self, message_type):
        messages_received_total.labels(message_type=message_type).inc()
    
    def message_sent(self, message_type):
        messages_sent_total.labels(message_type=message_type).inc()
    
    def validation_failed(self, error_type):
        message_validation_failures_total.labels(error_type=error_type).inc()
    
    def audio_stream_started(self, session_id):
        audio_streams_started_total.inc()
        self.audio_stream_start_times[session_id] = time.time()
    
    def audio_stream_completed(self, session_id):
        audio_streams_completed_total.inc()
        start_time = self.audio_stream_start_times.pop(session_id, None)
        if start_time:
            duration = time.time() - start_time
            audio_stream_duration_seconds.observe(duration)
    
    def audio_stream_cancelled(self, session_id):
        audio_streams_cancelled_total.inc()
        self.audio_stream_start_times.pop(session_id, None)
    
    def audio_chunk_sent(self, latency_seconds):
        audio_chunk_latency_seconds.observe(latency_seconds)
    
    def tts_request_started(self):
        tts_requests_total.inc()
        return time.time()  # Return start time for duration tracking
    
    def tts_request_completed(self, start_time):
        duration = time.time() - start_time
        tts_request_duration_seconds.observe(duration)
    
    def tts_request_failed(self, error_type):
        tts_failures_total.labels(error_type=error_type).inc()

# Global metrics collector
metrics = MetricsCollector()

def start_metrics_server(port=9090):
    """Start Prometheus metrics HTTP server"""
    try:
        start_http_server(port)
        logger.info(f"Metrics server started on port {port}")
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")