"""Pipeline transcript logger — JSON-lines per-day logging."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from skull.config import TRANSCRIPT_DIR

log = logging.getLogger(__name__)


def ensure_dir():
    Path(TRANSCRIPT_DIR).mkdir(parents=True, exist_ok=True)


def log_run(
    *,
    wake_confidence: float,
    recording_duration_ms: float,
    stt_text: str,
    stt_ms: float,
    llm_first_token_ms: float,
    llm_total_ms: float,
    llm_response: str,
    tts_chunks: list[dict],
    total_pipeline_ms: float,
    time_to_first_audio_ms: float,
    error: str | None = None,
) -> None:
    """Write a single pipeline run record to today's transcript file."""
    ensure_dir()

    now = datetime.now()
    filepath = Path(TRANSCRIPT_DIR) / f"{now.strftime('%Y-%m-%d')}.jsonl"

    record = {
        "timestamp": now.isoformat(),
        "wake_confidence": round(wake_confidence, 3),
        "recording_duration_ms": round(recording_duration_ms, 1),
        "stt_text": stt_text,
        "stt_ms": round(stt_ms, 1),
        "llm_first_token_ms": round(llm_first_token_ms, 1),
        "llm_total_ms": round(llm_total_ms, 1),
        "llm_response": llm_response,
        "tts_chunks": tts_chunks,
        "total_pipeline_ms": round(total_pipeline_ms, 1),
        "time_to_first_audio_ms": round(time_to_first_audio_ms, 1),
    }
    if error:
        record["error"] = error

    with open(filepath, "a") as f:
        f.write(json.dumps(record, default=lambda x: float(x)) + "\n")

    log.debug("Transcript logged to %s", filepath)
