"""Omni Vox Skull — Configuration constants."""

import os

# ── Wake Word ──────────────────────────────────────────────────
WAKE_WORD_MODEL = os.getenv("WAKE_WORD_MODEL", "hey_jarvis")
WAKE_WORD_THRESHOLD = float(os.getenv("WAKE_WORD_THRESHOLD", "0.5"))

# ── STT (Whisper) ──────────────────────────────────────────────
WHISPER_URL = os.getenv(
    "WHISPER_URL",
    "http://100.109.78.64:8000/v1/audio/transcriptions",
)
WHISPER_MODEL = os.getenv(
    "WHISPER_MODEL",
    "deepdml/faster-whisper-large-v3-turbo-ct2",
)
WHISPER_TIMEOUT = float(os.getenv("WHISPER_TIMEOUT", "10"))

# ── LLM (OpenClaw OpenResponses) ──────────────────────────────
OPENCLAW_URL = os.getenv(
    "OPENCLAW_URL",
    "http://100.109.78.64:18789/v1/responses",
)
OPENCLAW_TOKEN = os.getenv("OPENCLAW_TOKEN", "")
if not OPENCLAW_TOKEN:
    _token_path = os.path.expanduser("~/.openclaw-token")
    if os.path.exists(_token_path):
        OPENCLAW_TOKEN = open(_token_path).read().strip()
OPENCLAW_MODEL = os.getenv("OPENCLAW_MODEL", "openclaw:main")
OPENCLAW_USER = os.getenv("OPENCLAW_USER", "skull-vox4")
OPENCLAW_TIMEOUT = float(os.getenv("OPENCLAW_TIMEOUT", "30"))

# ── TTS (Kokoro) ──────────────────────────────────────────────
KOKORO_URL = os.getenv(
    "KOKORO_URL",
    "http://100.109.78.64:8880/v1/audio/speech",
)
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "bm_drogan")
KOKORO_MODEL = os.getenv("KOKORO_MODEL", "kokoro")
KOKORO_FORMAT = os.getenv("KOKORO_FORMAT", "mp3")
KOKORO_TIMEOUT = float(os.getenv("KOKORO_TIMEOUT", "10"))

# ── Audio (dmix/dsnoop for simultaneous capture + playback) ───
ALSA_PLAYBACK_DEVICE = os.getenv("ALSA_PLAYBACK_DEVICE", "default")
ALSA_CAPTURE_DEVICE = os.getenv("ALSA_CAPTURE_DEVICE", "default")
# Legacy single device (kept for backward compat)
ALSA_DEVICE = os.getenv("ALSA_DEVICE", "default")
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
CHANNELS = 1

# ── VAD ────────────────────────────────────────────────────────
VAD_SILENCE_TIMEOUT = float(os.getenv("VAD_SILENCE_TIMEOUT", "1.5"))
VAD_MAX_DURATION = float(os.getenv("VAD_MAX_DURATION", "30"))
VAD_SPEECH_THRESHOLD = float(os.getenv("VAD_SPEECH_THRESHOLD", "0.5"))
VAD_BARGE_IN_THRESHOLD = float(os.getenv("VAD_BARGE_IN_THRESHOLD", "0.85"))
VAD_MIN_SPEECH_DURATION = float(os.getenv("VAD_MIN_SPEECH_DURATION", "0.5"))

# ── Session ────────────────────────────────────────────────────
SESSION_OPEN_TIMEOUT = float(os.getenv("SESSION_OPEN_TIMEOUT", "5.0"))
SESSION_FOLLOWUP_TIMEOUT = float(os.getenv("SESSION_FOLLOWUP_TIMEOUT", "5.0"))
SESSION_FOLLOWUP_EXTENDED = float(os.getenv("SESSION_FOLLOWUP_EXTENDED", "10.0"))
SESSION_FOLLOWUP_EXTEND_AFTER = int(os.getenv("SESSION_FOLLOWUP_EXTEND_AFTER", "2"))
SESSION_MAX_DURATION = float(os.getenv("SESSION_MAX_DURATION", "120.0"))
FILLER_TIMEOUT = float(os.getenv("FILLER_TIMEOUT", "3.0"))

# ── Vox-Caster Filter ─────────────────────────────────────────
VOX_FILTER = (
    "highpass=f=300,lowpass=f=3500,"
    "acompressor=threshold=-15dB:ratio=4:attack=5:release=50,"
    "volume=1.35,"
    "tremolo=f=45:d=0.04,"
    "equalizer=f=1000:t=q:w=2:g=2"
)

# ── Paths ──────────────────────────────────────────────────────
CUES_DIR = os.path.join(os.path.dirname(__file__), "audio", "cues")
TRANSCRIPT_DIR = os.path.join(os.path.dirname(__file__), "transcript")
SOUL_PATH = os.getenv("SOUL_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "SOUL.md"))

# ── Sentence delimiters for streaming TTS ──────────────────────
SENTENCE_DELIMITERS = frozenset(".!?;:")

# Seconds of no LLM text before playing a longer tool-call acknowledgment
TOOL_CALL_FILLER_TIMEOUT = float(os.getenv("TOOL_CALL_FILLER_TIMEOUT", "8.0"))
