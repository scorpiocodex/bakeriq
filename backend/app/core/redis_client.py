"""Redis client — singleton + connection management.

Phase 3 uses Redis for two things:
  - Per-customer-phone conversation state (which step the bot is in, TTL 30 min)
  - Cart cache for the customer web app (keyed by web session token, TTL 30 min)

We use the sync redis client because the rest of the FastAPI app is sync
SQLAlchemy. Async Redis would require an async backend swap across the
codebase, which is out of scope for Phase 3.

Connection pooling is automatic — the redis-py client maintains a pool
under the hood, so we hand out the same singleton everywhere.
"""

from redis import Redis

from app.core.config import settings


_redis: Redis | None = None


def get_redis() -> Redis:
    """Return the redis client"""
    global _redis
    if _redis is None:
        _redis = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            decode_responses=True
        )

    return _redis
