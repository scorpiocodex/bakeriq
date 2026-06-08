"""Celery app factory + configuration.

Why Celery (and not FastAPI BackgroundTasks): Twilio webhooks have a
~15s response budget. Anything that involves an external API call
(Anthropic, Twilio outbound) needs to be moved off the request path:

  - Anthropic latency is 2-5s in the happy case, longer under
    contention. A single slow call doesn't break us, but a backlog
    would queue up against the uvicorn worker's HTTP threads.

  - Retries are first-class in Celery (autoretry_for, retry_backoff)
    and a pain to bolt onto background tasks.

  - The worker is a separate process — if it OOMs or crashes mid-task,
    the api process keeps serving webhooks unaffected.

Broker + result backend: Redis (already in our stack — same instance
that the conversation state machine and cart cache use, separate
logical keys so no collisions).

In dev we run one worker container with --concurrency=2 (plenty for
bakery-scale traffic). In production we'd scale concurrency based on
the Anthropic rate limit headers we observe.
"""

from celery import Celery

from app.core.config import settings


def make_celery() -> Celery:
    """Build the Celery app. Called once at module imports"""
    app = Celery(
        "bakeriq",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=["app.tasks.llm"],
    )

    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Kolkata",
        enable_utc=True,
        result_expires=300,
        task_acks_late=True,
        task_default_retry_delay=10,
        task_max_retries=3,
        broker_connection_retry_on_startup=True,
    )

    return app


celery_app = make_celery()
