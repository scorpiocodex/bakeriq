"""LLM parser service — converts free-text WhatsApp messages into
structured order intent.

Architecture:
  - The Celery task calls parse_message() with the customer's raw text.
  - This module loads today's product catalog from the database, builds
    a system prompt that includes product names + aliases, and asks
    Ollama (llama3.2:3b by default) to extract {product_name, quantity}
    pairs.
  - The LLM is constrained to a JSON schema via Ollama's `format`
    parameter, so the response is guaranteed-parseable JSON (no
    markdown fences, no chatty preamble).
  - Product matching to actual Product rows happens DOWNSTREAM in
    product_matcher_service (Substep 4). This module just gets the
    LLM's interpretation of names + quantities; the matcher decides
    which real product each name refers to.

Why this split (LLM vs matcher):
  - LLM is good at language understanding ("2 veg puff" → name='veg puff',
    qty=2) but stochastic on exact string output.
  - Matcher is deterministic — given the LLM's noisy product name, it
    consults the real Product table + aliases and picks the best match
    or returns None for ambiguous cases.
  - Splitting them keeps each module testable in isolation.

Error cases:
  - LLM returns valid JSON but nothing useful → empty parsed_items list,
    customer gets a polite "Sorry, I didn't catch that" message.
  - LLM call times out / connection fails → exception bubbles up to
    Celery for retry. After max retries, Celery's failure hook sends
    the customer a fallback message.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.ollama_client import get_client
from app.models.product import Product

# JSON schema constraining the LLM output. Ollama's `format` parameter
# enforces this at the token-sampling level, so we get guaranteed
# valid JSON matching this shape (no markdown fences, no chatty
# preamble, no missing fields).
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string"},
                    "quantity": {"type": "integer", "minimum": 1},
                },
                "required": ["product_name", "quantity"],
            },
        },
    },
    "required": ["items"],
}


def _build_system_prompt(products: list[Product]) -> str:
    """Construct the system prompt with today's available products.

    The product catalog goes in the SYSTEM prompt rather than the user
    message because:
      - It's stable across messages — clean separation of system
        instructions vs the user's data.
      - Keeps the user message clean for the actual customer text,
        which makes debugging easier.

    Aliases matter: 'veg puff' is what customers say, but the product
    in the DB might be 'Veg Puff' or have aliases like ['vegetable puff',
    'veg patty']. The LLM should pick the canonical name we list here
    so the downstream matcher's job is easy.

    Few-shot examples in the prompt cover the failure modes we saw in
    early testing: Llama 3.2 3B mishandles Manglish quantity words
    ('oru' = 1) and hallucinates off-menu items unless explicitly
    shown otherwise.
    """
    product_lines = []
    for p in products:
        aliases = p.aliases or []
        alias_str = f" (also: {', '.join(aliases)})" if aliases else ""
        product_lines.append(f"  - {p.name}{alias_str}")
    catalog = (
        "\n".join(product_lines) if product_lines else "  (no products available today)"
    )

    return f"""You are an order-parsing assistant for a small Indian bakery called BakeriQ.

Your job: read a customer's free-text WhatsApp message and extract what they want to order. The message may be in English, Malayalam, Manglish (Malayalam written in English letters), or a mix. Customers are casual — they write things like "2 veg puff and a ladoo please" or "3 chicken puff venam".

Today's available products:
{catalog}

Quantity word reference (Malayalam/Manglish → number):
  - oru, onnu, ondu = 1
  - randu, rendu = 2
  - moonu, moonnu = 3
  - naalu, naal = 4
  - anju, ainju = 5

Rules:
1. Use the EXACT product names from the catalog above. If a customer says "veg puff" and the catalog has "Veg Puff", output "Veg Puff".
2. Quantity must be a positive integer. Words like "a", "one", "oru" mean 1. Numerals override words ("2 puff" is 2, not whatever "puff" might imply).
3. If the customer asks for something NOT in the catalog above, OMIT it entirely. Do NOT include it in your output. Do NOT substitute it for something similar. Just drop it.
4. If the message contains no clear order intent (greeting, question, complaint, chitchat), return an empty items list.

Examples:

Customer: "2 veg puff and 1 ladoo"
Output: {{"items": [{{"product_name": "Veg Puff", "quantity": 2}}, {{"product_name": "Ladoo", "quantity": 1}}]}}

Customer: "oru chicken puff venam"
Output: {{"items": [{{"product_name": "Chicken Puff", "quantity": 1}}]}}

Customer: "2 samosa and 1 ladoo"  (samosa is NOT in the catalog)
Output: {{"items": [{{"product_name": "Ladoo", "quantity": 1}}]}}

Customer: "hi how are you"
Output: {{"items": []}}

Customer: "do you have brownies?"  (no order intent, just a question)
Output: {{"items": []}}

Return only the JSON object matching the schema."""


def _load_todays_catalog(db: Session) -> list[Product]:
    """Load products that are active AND available today.

    Same query the menu rendering and cart endpoints use — we keep the
    LLM's view of the world consistent with what the customer can
    actually order via the web app."""
    return list(
        db.scalars(
            select(Product)
            .where(Product.is_active.is_(True))
            .where(Product.is_available_today.is_(True))
            .order_by(Product.name)
        )
    )


def parse_message(db: Session, text: str) -> dict[str, Any]:
    """Run the LLM on a customer message and return the parsed structure.

    Returns:
        {"items": [{"product_name": str, "quantity": int}, ...]}

    Raises:
        ollama.ResponseError — for transient network/server issues.
            Celery will catch + retry with backoff.
        json.JSONDecodeError — defensive; shouldn't happen because
            Ollama enforces the schema, but we don't rely on that
            invariant in case the SDK behaviour changes.
    """
    products = _load_todays_catalog(db)
    system_prompt = _build_system_prompt(products)

    client = get_client()
    response = client.chat(
        model=settings.OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        # Ollama's structured-output mode. Output is guaranteed to be
        # valid JSON matching this schema. No need to strip markdown
        # fences or repair chatty preambles like we'd need with a
        # cloud LLM in plain-text mode.
        format=RESPONSE_SCHEMA,
        # Low temperature for extraction — we want consistent,
        # deterministic parsing, not creative interpretation.
        options={"temperature": 0.0},
    )

    raw_text = response["message"]["content"]
    parsed = json.loads(raw_text)

    # Defensive normalisation. Even with schema enforcement, we want a
    # stable contract for the caller in case the SDK ever returns
    # something unexpected.
    if not isinstance(parsed, dict):
        return {"items": []}
    items = parsed.get("items", [])
    if not isinstance(items, list):
        return {"items": []}

    cleaned_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("product_name")
        qty = item.get("quantity")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(qty, int) or qty <= 0:
            continue
        cleaned_items.append({"product_name": name.strip(), "quantity": qty})

    return {"items": cleaned_items}
