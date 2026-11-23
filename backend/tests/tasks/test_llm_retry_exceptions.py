"""RETRY_EXCEPTIONS must match what the Ollama SDK really raises.

The SDK talks HTTP through httpx. The rest of the app uses httpx2, so an `httpx2.ConnectError`
in the retry tuple would look right and never match anything, and failed LLM calls would stop
being retried without a single test failing. This test provokes a real refused connection
through the SDK instead of trusting the class names.
"""

import httpx
import ollama
import pytest
from app.tasks.llm import RETRY_EXCEPTIONS


def test_a_refused_connection_from_the_ollama_sdk_is_retryable():
    client = ollama.Client(host="http://127.0.0.1:1", timeout=2)  # nothing listens on port 1
    with pytest.raises(Exception) as raised:
        client.list()
    assert isinstance(raised.value, RETRY_EXCEPTIONS), (
        f"{type(raised.value).__module__}.{type(raised.value).__name__} is not retried"
    )


def test_the_tuple_uses_the_httpx_the_sdk_depends_on():
    assert httpx.ConnectError in RETRY_EXCEPTIONS
    assert all(exc.__module__.split(".")[0] != "httpx2" for exc in RETRY_EXCEPTIONS)
