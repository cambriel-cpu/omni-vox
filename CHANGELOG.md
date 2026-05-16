# Changelog

All notable changes to Omni Vox will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.1.0-sentence-streaming] - 2026-05-16

### Added
- `openclaw_streaming.py` — Direct OpenResponses API client with SSE streaming
- Sentence-level streaming: LLM response is chunked into sentences and each sentence is TTS'd and sent to the client immediately (no waiting for full response)
- New WebSocket message types: `response_sentence` (per-sentence text), `audio_start.mode=sentence_stream`
- `call_sync()` function for non-streaming REST endpoint use

### Changed
- **WebSocket `voice_request` path**: Replaced hooks/agent + file-polling (5-15s latency) with direct OpenResponses SSE streaming (~1-2s time-to-first-audio)
- **REST `/api/voice` endpoint**: Uses `openclaw_streaming.call_sync()` instead of hooks+polling — eliminates polling overhead
- Instructions/context now passed via OpenResponses `instructions` field instead of being prepended to the message

### Removed
- Dependency on `hooks/agent` endpoint for WebSocket voice path (REST fallback still available via `call_openclaw()`)
- File-polling loop for response detection

## [2.0.0-websocket-streaming] - 2026-02-27

### Added
- WebSocket-based real-time voice interaction
- Audio streaming support
- Comprehensive health checks
- Prometheus metrics integration
- Session management
- Message validation
- Multi-turn conversation support

### Changed
- Complete rewrite from HTTP-only to WebSocket architecture
- Improved error handling and logging
- Better audio quality with streaming

### Fixed
- Audio latency issues
- Memory leaks in long-running sessions
- Connection stability

## [1.1.0] - 2026-02-19

### Added
- Sonos speaker integration
- Multiple TTS provider support (Kokoro, ElevenLabs)
- Obsidian vault logging
- Magnus bridge for remote speakers
- Conversation history tracking

### Changed
- Improved audio quality
- Better error messages
- Enhanced logging

### Fixed
- Audio playback reliability
- TTS generation stability

## [1.0.0] - 2026-02-17

### Added
- Initial release
- Basic voice interaction (STT → LLM → TTS)
- OpenClaw integration via hooks
- Whisper transcription support
- Kokoro TTS integration
- FastAPI web interface
- Docker containerization

### Features
- Audio file upload and processing
- Claude model integration
- Basic health checks
- Static file serving