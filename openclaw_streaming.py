"""
OpenClaw LLM client — OpenResponses API with SSE streaming.

Replaces the slow hooks/agent + file-polling path with direct streaming,
yielding complete sentences for incremental TTS.

Modeled on the servo-skull's proven openclaw_client.py implementation.
"""
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Optional

import httpx

log = logging.getLogger(__name__)

# Configuration
OPENCLAW_URL = os.environ.get(
    "OPENCLAW_RESPONSES_URL",
    "http://127.0.0.1:18789/v1/responses",
)
OPENCLAW_TOKEN = os.environ.get("OPENCLAW_TOKEN", "")
if not OPENCLAW_TOKEN:
    # Try loading from file (same approach as servo-skull)
    _token_path = os.environ.get("OPENCLAW_TOKEN_FILE", "/root/.openclaw/hooks-token")
    if os.path.exists(_token_path):
        OPENCLAW_TOKEN = open(_token_path).read().strip()

OPENCLAW_DEFAULT_MODEL = os.environ.get(
    "OPENCLAW_MODEL", "anthropic/claude-opus-4-6"
)
OPENCLAW_TIMEOUT = float(os.environ.get("OPENCLAW_TIMEOUT", "45"))

# Sentence delimiters for chunking LLM output into TTS-ready pieces
SENTENCE_DELIMITERS = frozenset(".!?;")


async def stream_response(
    message: str,
    *,
    instructions: str = "",
    model: Optional[str] = None,
    user: str = "omni-vox-pwa",
) -> AsyncIterator[str]:
    """Stream LLM response via OpenResponses SSE, yielding sentence chunks.

    Args:
        message: The user's message (transcribed speech or text).
        instructions: System instructions (SOUL.md, conversation context, etc.)
        model: LLM model to use (defaults to OPENCLAW_DEFAULT_MODEL).
        user: User identifier for session tracking.

    Yields:
        Complete sentence strings, suitable for TTS synthesis.
    """
    headers = {"Content-Type": "application/json"}
    if OPENCLAW_TOKEN:
        headers["Authorization"] = f"Bearer {OPENCLAW_TOKEN}"

    body: dict = {
        "model": model or OPENCLAW_DEFAULT_MODEL,
        "input": message,
        "stream": True,
        "user": user,
    }
    if instructions:
        body["instructions"] = instructions

    t0 = time.monotonic()
    first_token_ms: float | None = None
    buffer = ""
    total_text = ""

    timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST", OPENCLAW_URL, json=body, headers=headers
        ) as response:
            response.raise_for_status()
            log.info("LLM stream opened (status=%d, model=%s)", response.status_code, model or OPENCLAW_DEFAULT_MODEL)

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                raw = line[6:]
                if raw == "[DONE]":
                    break

                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")

                if etype == "response.output_text.delta":
                    delta = event.get("delta", "")
                    if not delta:
                        continue

                    if first_token_ms is None:
                        first_token_ms = (time.monotonic() - t0) * 1000
                        log.info("LLM first token: %.0fms", first_token_ms)

                    buffer += delta
                    total_text += delta

                    # Yield complete sentences
                    while buffer:
                        earliest = -1
                        for delim in SENTENCE_DELIMITERS:
                            pos = buffer.find(delim)
                            if pos != -1 and (earliest == -1 or pos < earliest):
                                earliest = pos

                        if earliest == -1:
                            break

                        sentence = buffer[: earliest + 1].strip()
                        buffer = buffer[earliest + 1:]
                        if sentence:
                            yield sentence

                elif etype == "response.completed":
                    log.info("LLM response.completed event received")
                    break

    # Flush remainder
    remainder = buffer.strip()
    if remainder:
        log.info("LLM flushing remainder: %r", remainder[:60])
        yield remainder

    elapsed_ms = (time.monotonic() - t0) * 1000
    log.info(
        "LLM complete: %.0fms total, first_token=%.0fms, %d chars",
        elapsed_ms,
        first_token_ms or 0,
        len(total_text),
    )


async def call_sync(
    message: str,
    *,
    instructions: str = "",
    model: Optional[str] = None,
    user: str = "omni-vox-pwa",
) -> tuple[str, dict]:
    """Non-streaming LLM call. Returns (response_text, usage_dict).

    Used for the REST /api/voice endpoint where full response is needed before TTS.
    """
    headers = {"Content-Type": "application/json"}
    if OPENCLAW_TOKEN:
        headers["Authorization"] = f"Bearer {OPENCLAW_TOKEN}"

    body: dict = {
        "model": model or OPENCLAW_DEFAULT_MODEL,
        "input": message,
        "stream": False,
        "user": user,
    }
    if instructions:
        body["instructions"] = instructions

    timeout = httpx.Timeout(connect=10.0, read=OPENCLAW_TIMEOUT, write=10.0, pool=10.0)

    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(OPENCLAW_URL, json=body, headers=headers)
        response.raise_for_status()
        result = response.json()

    elapsed_ms = (time.monotonic() - t0) * 1000

    # Extract text from OpenResponses format
    text = ""
    output = result.get("output", [])
    if output:
        content = output[0].get("content", [])
        if content:
            text = content[0].get("text", "")

    usage = result.get("usage", {})
    log.info("LLM sync complete: %.0fms, %d chars", elapsed_ms, len(text))

    return text, usage
