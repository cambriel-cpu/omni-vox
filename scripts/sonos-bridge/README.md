# Sonos Bridge

Lightweight HTTP server that receives audio files and plays them on local Sonos speakers. Designed to run on a machine on the same LAN as Sonos speakers, controlled remotely via HTTP API.

## Setup

```bash
pip install soco flask
python server.py
```

The bridge will discover Sonos speakers on your network and listen on port 5111.

## API

### List speakers
```
GET http://localhost:5111/speakers
```

### Play audio on a speaker
```
POST http://localhost:5111/play/<speaker_name>
Content-Type: multipart/form-data
Field: audio (file)
Optional query param: ?volume=30
```

### Health check
```
GET http://localhost:5111/health
```

## Windows Quick Start

1. Install Python 3.10+ from https://www.python.org/downloads/
2. Run `install.bat` to install dependencies
3. Run `start.bat` to start the bridge

## Environment Variables

- `SONOS_BRIDGE_PORT` — Server port (default: 5111)

## How It Works

1. Receives an audio file via HTTP POST
2. Saves it temporarily
3. Spins up a local HTTP server to serve the file
4. Tells the Sonos speaker to stream from that server
5. Waits for playback to complete
6. Cleans up and restores previous playback state (resumes music if it was playing)
