"""Conversation state helpers — Redis-backed per-phone state machine.

The bot needs to remember "what step is this customer's conversation at?"
across webhooks. WhatsApp doesn't carry session state, so we use the
customer's phone number as the conversation key and store the state in
Redis.

State shape (JSON):
  {
    "state": "idle" | "building_order" | "awaiting_confirmation" |
             "registering_name" | "registering_area" |
             "awaiting_owner_approval",
    "customer_id": "<uuid>" | null,
    "draft_order_id": "<uuid>" | null,
    "current_token": "<string>" | null,
    "extra": { ... }                       # state-specific scratch
  }

TTL is 30 minutes — if a customer drops mid-conversation and comes back
4 hours later, that's a new conversation; previous state is stale.
Every read or write refreshes the TTL.
"""

import json
from typing import Any

from app.core.redis_client import get_redis


CONVERSATION_TTL_SECONDS = 1800     # 30 minutes

VALID_STATES = {
    "idle",
    "building_order",
    "awaiting_confirmation",
    "registering_name",
    "registering_area",
    "awaiting_owner_approval",
    "bot_offline",
}


def _key(phone: str) -> str:
    return f"conv:state:{phone}"


def get_state(phone: str) -> dict[str, Any] | None:
    """Return the current conversation state for a phone or None if no conversation"""
    r = get_redis()
    key = _key(phone)
    raw = r.get(key)
    if raw is None:
        return None

    # Refresh TTL on read
    r.expire(key, CONVERSATION_TTL_SECONDS)
    return json.loads(raw) # type: ignore


def set_state(phone: str, data: dict[str, Any]) -> None:
    """Write conversation state, replace existing"""
    if "state" not in data:
        raise ValueError("Conversation state must include a 'state' field")
    if data["state"] not in VALID_STATES:
        raise ValueError(
            f"Invalid conversation state {data['state']!r}; "
            f"valid: {sorted(VALID_STATES)}"
        )
    r = get_redis()
    r.set(_key(phone), json.dumps(data), ex=CONVERSATION_TTL_SECONDS)


def clear_state(phone: str) -> None:
    """Delete the conversation entirely"""
    r = get_redis()
    r.delete(_key(phone))


def update_state(phone: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Merge `patch` into the existing state, write back, return the new
    state."""
    current = get_state(phone)
    if current is None:
        raise ValueError(f"No conversation state to update for phone {phone}")
    current.update(patch)
    set_state(phone, current)
    return current
