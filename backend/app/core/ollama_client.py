"""Ollama API client — thin wrapper around the SDK.

Why a wrapper rather than instantiating ollama.Client() directly:
  - One place to thread the base URL from settings, so tests can mock
    a single import path.
  - Sets sensible defaults (timeout) that we don't want repeated at
    every call site.
  - Lazy initialisation — the client doesn't connect until first use,
    so a misconfigured host surfaces as a clear runtime error rather
    than crashing the worker on boot.

The actual Messages API calls live in llm_parser_service.py (Substep 3).
This module just hands out a configured client.

Ollama vs cloud LLMs — what's different:
  - No API key; auth is "you can reach the port".
  - Models are pulled to disk separately via `ollama pull`. The SDK
    can also pull on demand but we avoid that — silent multi-GB
    downloads at task time would be a bad surprise.
  - Latency is dominated by CPU/GPU, not network. Timeout is set
    generously to absorb cold-start latency on the first call after
    boot (when the model gets loaded into RAM).
"""

from __future__ import annotations

from functools import lru_cache

from ollama import Client

from app.core.config import settings


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Return the singleton Ollama client.

    @lru_cache(maxsize=1) makes this effectively a process-wide
    singleton — first call constructs, subsequent calls return the
    same instance. Avoids creating a new HTTP connection pool per
    LLM call.
    """
    return Client(
        host=settings.OLLAMA_BASE_URL,
        # 60s timeout. First call after Ollama boots loads the model
        # into RAM which can take 10-20s on CPU. Subsequent calls are
        # 3-5s. We pick 60 for safe headroom — failing fast on a
        # genuinely hung connection still works (Celery's own retry
        # layer will catch it).
        timeout=60,
    )
