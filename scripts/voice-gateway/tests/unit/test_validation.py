import pytest
from validation import MessageValidator, ValidationError

def test_validate_message_size_limit():
    validator = MessageValidator()
    large_message = {"text": "x" * 10250}  # Over 10KB limit (10240 bytes)
    
    with pytest.raises(ValidationError, match="Message too large"):
        validator.validate_message(large_message, "session123")

def test_validate_audio_size_limit():
    validator = MessageValidator()
    large_audio = {"type": "voice_request", "audio_data": "x" * (5 * 1024 * 1024 + 1)}
    
    with pytest.raises(ValidationError, match="Audio data too large"):
        validator.validate_message(large_audio, "session123")

def test_rate_limiting():
    validator = MessageValidator(max_requests=2, rate_window=60)
    message = {"type": "ping"}
    
    # First two requests should pass
    validator.validate_message(message, "session123")
    validator.validate_message(message, "session123")
    
    # Third should fail
    with pytest.raises(ValidationError, match="Rate limit exceeded"):
        validator.validate_message(message, "session123")

def test_malformed_json_handling():
    validator = MessageValidator()
    
    with pytest.raises(ValidationError, match="Invalid message format"):
        validator.validate_raw_message("invalid json", "session123")