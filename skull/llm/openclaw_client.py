"""LLM client — OpenClaw OpenResponses with SSE streaming."""

import json
import logging
import time
from collections.abc import AsyncIterator

import httpx

from skull.config import (
    OPENCLAW_MODEL,
    OPENCLAW_TIMEOUT,
    OPENCLAW_TOKEN,
    OPENCLAW_URL,
    OPENCLAW_USER,
    SENTENCE_DELIMITERS,
)

log = logging.getLogger(__name__)


async def stream_sentences(
    text: str,
    instructions: str = "",
) -> AsyncIterator[str]:
    """Stream LLM response, yielding complete sentences for TTS.

    Uses a fresh httpx client per call to avoid stale connection issues.

    Args:
        text: User's transcribed speech.
        instructions: Optional system instructions (e.g. SOUL.md).

    Yields:
        Sentence-sized text chunks suitable for TTS.
    """
    headers = {"Content-Type": "application/json"}
    if OPENCLAW_TOKEN:
        headers["Authorization"] = f"Bearer {OPENCLAW_TOKEN}"

    body: dict = {
        "model": OPENCLAW_MODEL,
        "input": text,
        "stream": True,
        "user": OPENCLAW_USER,
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
            log.info("LLM stream opened (status=%d)", response.status_code)

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                try:
                    event = json.loads(line[6:])
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
                        buffer = buffer[earliest + 1 :]
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


async def close():
    """No-op — client is created per call now."""
    pass
