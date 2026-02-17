#!/usr/bin/env python3
"""
Sonos Bridge Server
Lightweight HTTP server that receives audio files and plays them on local Sonos speakers.
Designed to run on a machine on the same LAN as Sonos speakers.

Usage:
    pip install soco flask
    python server.py

API:
    GET  /speakers              - List discovered Sonos speakers
    POST /play/<speaker_name>   - Play audio file on speaker (non-blocking)
         Body: multipart file upload (field: "audio")
         Optional query params: ?volume=30&block=true
    POST /stop/<speaker_name>   - Stop playback and restore previous state
    POST /stop                  - Stop all speakers
    GET  /health                - Health check
"""

import os
import sys
import time
import tempfile
import threading
import soco
from flask import Flask, request, jsonify

app = Flask(__name__)

# Cache discovered speakers (refresh periodically)
_speakers_cache = {}
_cache_time = 0
CACHE_TTL = 300  # 5 minutes

# Track active playback sessions for cleanup and stop functionality
_active_sessions = {}  # speaker_name -> { httpd, thread, original_volume, was_playing, tmp_path, speaker }
_sessions_lock = threading.Lock()


def discover_speakers(force=False):
    """Discover Sonos speakers on the local network."""
    global _speakers_cache, _cache_time

    if not force and _speakers_cache and (time.time() - _cache_time) < CACHE_TTL:
        return _speakers_cache

    speakers = {}
    try:
        discovered = soco.discover(timeout=5)
        if discovered:
            for speaker in discovered:
                speakers[speaker.player_name.lower()] = {
                    "name": speaker.player_name,
                    "ip": speaker.ip_address,
                    "volume": speaker.volume,
                    "is_coordinator": speaker.is_coordinator,
                }
    except Exception as e:
        print(f"Discovery error: {e}", file=sys.stderr)
        if _speakers_cache:
            return _speakers_cache

    _speakers_cache = speakers
    _cache_time = time.time()
    return speakers


def get_speaker(name):
    """Get a SoCo speaker object by room name."""
    speakers = discover_speakers()
    key = name.lower()
    if key not in speakers:
        speakers = discover_speakers(force=True)
        if key not in speakers:
            return None

    return soco.SoCo(speakers[key]["ip"])


def _get_local_ip(target_ip):
    """Get the local IP address that can reach the target (Sonos speaker)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target_ip, 1400))
        return s.getsockname()[0]
    finally:
        s.close()


def _cleanup_session(speaker_name):
    """Clean up an active playback session — stop server, restore state, delete temp file."""
    with _sessions_lock:
        session = _active_sessions.pop(speaker_name.lower(), None)

    if not session:
        return

    try:
        session["httpd"].shutdown()
    except Exception:
        pass

    try:
        speaker = session["speaker"]
        if session.get("original_volume") is not None:
            speaker.volume = session["original_volume"]
        if session.get("was_playing"):
            try:
                speaker.play()
            except Exception:
                pass
    except Exception:
        pass

    try:
        os.unlink(session["tmp_path"])
    except Exception:
        pass


def _playback_monitor(speaker_name, speaker_obj):
    """Background thread that waits for playback to finish, then cleans up."""
    time.sleep(1)  # Give Sonos a moment to start
    max_wait = 300  # 5 minutes max
    waited = 0
    while waited < max_wait:
        # Check if session was already cleaned up (e.g. by /stop)
        with _sessions_lock:
            if speaker_name.lower() not in _active_sessions:
                return
        try:
            info = speaker_obj.get_current_transport_info()
            if info["current_transport_state"] != "PLAYING":
                break
        except Exception:
            break
        time.sleep(0.5)
        waited += 0.5

    _cleanup_session(speaker_name)


@app.route("/health", methods=["GET"])
def health():
    with _sessions_lock:
        active = list(_active_sessions.keys())
    return jsonify({"status": "ok", "speakers": len(discover_speakers()), "active_playback": active})


@app.route("/speakers", methods=["GET"])
def list_speakers():
    speakers = discover_speakers(force="refresh" in request.args)
    return jsonify(speakers)


@app.route("/stop", methods=["POST"], defaults={"speaker_name": None})
@app.route("/stop/<speaker_name>", methods=["POST"])
def stop_playback(speaker_name):
    """Stop playback on a specific speaker or all speakers."""
    if speaker_name:
        # Stop specific speaker
        speaker = get_speaker(speaker_name)
        if speaker:
            try:
                speaker.stop()
            except Exception:
                pass
        _cleanup_session(speaker_name)
        return jsonify({"status": "stopped", "speaker": speaker_name})
    else:
        # Stop all active sessions
        with _sessions_lock:
            names = list(_active_sessions.keys())
        for name in names:
            speaker = get_speaker(name)
            if speaker:
                try:
                    speaker.stop()
                except Exception:
                    pass
            _cleanup_session(name)
        return jsonify({"status": "stopped", "speakers": names})


@app.route("/play/<speaker_name>", methods=["POST"])
def play_audio(speaker_name):
    """
    Play an uploaded audio file on the specified Sonos speaker.

    Non-blocking by default — returns immediately after playback starts.
    Add ?block=true to wait for playback to complete.
    """
    speaker = get_speaker(speaker_name)
    if not speaker:
        available = list(discover_speakers().keys())
        return jsonify({
            "error": f"Speaker '{speaker_name}' not found",
            "available": available
        }), 404

    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided. Use multipart field 'audio'"}), 400

    audio_file = request.files["audio"]
    if not audio_file.filename:
        return jsonify({"error": "Empty filename"}), 400

    blocking = request.args.get("block", "").lower() in ("true", "1", "yes")
    volume = request.args.get("volume", type=int)

    # If there's already an active session on this speaker, clean it up first
    _cleanup_session(speaker_name)

    # Save to temp file
    suffix = os.path.splitext(audio_file.filename)[1] or ".mp3"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=tempfile.gettempdir())
    try:
        audio_file.save(tmp.name)
        tmp.close()

        # Store current state
        original_volume = speaker.volume if volume is not None else None
        was_playing = speaker.get_current_transport_info()["current_transport_state"] == "PLAYING"

        # Duck or pause current playback
        if was_playing:
            speaker.pause()

        # Set announcement volume if specified
        if volume is not None:
            speaker.volume = volume

        # Set up local HTTP server to serve the audio file
        from http.server import HTTPServer, SimpleHTTPRequestHandler
        import urllib.parse
        import socket

        file_dir = os.path.dirname(tmp.name)
        file_name = os.path.basename(tmp.name)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('', 0))
        serve_port = sock.getsockname()[1]
        sock.close()

        local_ip = _get_local_ip(speaker.ip_address)

        class QuietHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=file_dir, **kwargs)
            def log_message(self, format, *args):
                pass

        httpd = HTTPServer(('0.0.0.0', serve_port), QuietHandler)
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()

        uri = f"http://{local_ip}:{serve_port}/{urllib.parse.quote(file_name)}"

        # Register the active session
        with _sessions_lock:
            _active_sessions[speaker_name.lower()] = {
                "httpd": httpd,
                "thread": server_thread,
                "original_volume": original_volume,
                "was_playing": was_playing,
                "tmp_path": tmp.name,
                "speaker": speaker,
                "started": time.time(),
            }

        # Start playback
        speaker.play_uri(uri)

        if blocking:
            # Wait for playback to finish
            _playback_monitor(speaker_name, speaker)
            return jsonify({
                "status": "played",
                "speaker": speaker.player_name,
                "file": audio_file.filename,
            })
        else:
            # Start background monitor for cleanup, return immediately
            monitor = threading.Thread(
                target=_playback_monitor,
                args=(speaker_name, speaker),
                daemon=True
            )
            monitor.start()
            return jsonify({
                "status": "playing",
                "speaker": speaker.player_name,
                "file": audio_file.filename,
            })

    except Exception as e:
        _cleanup_session(speaker_name)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("Discovering Sonos speakers...")
    speakers = discover_speakers()
    if speakers:
        print(f"Found {len(speakers)} speaker(s):")
        for name, info in speakers.items():
            print(f"  - {info['name']} ({info['ip']})")
    else:
        print("No speakers found yet (will retry on requests)")

    port = int(os.environ.get("SONOS_BRIDGE_PORT", 5111))
    print(f"\nSonos Bridge running on port {port}")
    app.run(host="0.0.0.0", port=port)
