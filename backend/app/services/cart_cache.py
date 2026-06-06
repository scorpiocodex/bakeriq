"""Cart cache — Redis-backed shopping cart state for the customer web app.

The customer web app (Phase 3 Task 4-5) lets customers build orders in a
browser opened from a WhatsApp link. The cart contents are saved to
Redis (not Postgres) until the customer hits "Place order" — at which
point a real draft Order row is created.

Why Redis: the cart is in-flight, may be edited multiple times across
short intervals, and is fine to lose if the customer drops out. Persisting
every keystroke to Postgres would be wasteful.

Cart shape:
  {
    "customer_id": "<uuid>",
    "kind": "new" | "reorder" | "edit",
    "items": [
      {"product_id": "<uuid>", "quantity": 3}
    ],
    "notes": "<string>" | null,
    "updated_at": "<iso datetime>"
  }

The cart is keyed by the web_session_token (which the customer's URL
contains). Two tokens for the same customer mean two independent carts —
unusual but possible if the customer opens an old link and a new one.
TTL is 30 minutes, matching the token expiry.
"""

import json
from datetime import datetime, timezone
from typing import Any

from app.core.redis_client import get_redis

CART_TTL_SECONDS = 1800  # 30 minutes, matches web_session_token TTL


def _key(token: str) -> str:
    return f"cart:{token}"


def get_cart(token: str) -> dict[str, Any] | None:
    """Return the cart contents for a token, or None if not found / expired.

    Reads refresh the TTL — the customer is presumably looking at it, so
    we treat that as activity.
    """
    r = get_redis()
    key = _key(token)
    raw = r.get(key)
    if raw is None:
        return None
    r.expire(key, CART_TTL_SECONDS)
    return json.loads(raw) # type: ignore


def save_cart(token: str, data: dict[str, Any]) -> None:
    """Write the cart contents, replacing any existing data for this token.

    Stamps updated_at automatically so downstream code (the "cart saved"
    bot reply) can display when the customer last touched it.
    """
    data = {**data, "updated_at": datetime.now(timezone.utc).isoformat()}
    r = get_redis()
    r.set(_key(token), json.dumps(data), ex=CART_TTL_SECONDS)


def delete_cart(token: str) -> None:
    """Remove the cart. Called after the order is finalised."""
    r = get_redis()
    r.delete(_key(token))
