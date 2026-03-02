# Changelog

All notable changes to Omni Vox will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Clean GitHub repository structure
- Comprehensive README with API documentation
- Docker deployment configuration
- Environment variable configuration
- MIT License

### Changed
- Separated project from OpenClaw workspace
- Improved project organization
- Updated documentation

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