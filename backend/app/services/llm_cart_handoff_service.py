"""LLM cart handoff — turn the matcher's output into a customer-ready
web link + WhatsApp reply text.

This is the glue between the LLM safety-valve pipeline and the
existing customer web app. After Substep 4 we have a list of
MatchedItem (UUID + name + quantity). This module:

  1. Writes those items to the Redis cart cache, keyed by a freshly
     issued web_session_token (kind='new').
  2. Builds the public web URL the customer will tap.
  3. Composes the WhatsApp reply text — itemised summary, total,
     explicit list of dropped items, the link.

What this module does NOT do:
  - Actually send the WhatsApp message. The dispatcher in Substep 6
    takes the built text and hands it to the Twilio outbound service.
    Keeping the send separate means this whole pipeline is testable
    without mocking Twilio.
  - Decide what to do when there's nothing matched AND nothing
    dropped. That's the dispatcher's call — it'll fall back to the
    "Sorry, I didn't catch that" generic message.

Why we re-fetch products in here rather than relying on the matcher
having attached prices to MatchedItem:
  - Prices change. Between LLM parse and cart write (maybe 5s) the
    owner could update a price via the admin UI. We use the freshest
    value at cart-write time.
  - Matcher's MatchedItem only carries UUID + name + qty by design,
    matching what the Redis cart needs (UUID + qty). Pricing is the
    web app's concern when it later builds the cart view.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.product import Product
from app.services import cart_cache
from app.services.product_matcher_service import MatchedItem
from app.services.web_link_service import issue_link

logger = logging.getLogger(__name__)


@dataclass
class HandoffResult:
    """What this service returns to the dispatcher."""

    token: str
    link: str
    message_text: str  # ready to send via Twilio
    matched_count: int  # 0 means nothing matched — dispatcher may
    # choose to send the fallback instead
    dropped_names: list[str]


def _format_price(amount: Decimal) -> str:
    """Render a Decimal as an INR price string with no rupee symbol —
    Twilio messages render the rupee symbol inconsistently across
    phones, and '120.00' is unambiguous. Keep two decimal places
    for consistency with the web app."""
    return f"₹{amount:.2f}"


def _build_message_text(
    items_with_price: list[tuple[MatchedItem, Decimal]],
    dropped_names: list[str],
    link: str,
) -> str:
    """Compose the WhatsApp reply.

    Format:
      I understood your order:
      • Veg Puff × 2 — ₹50.00
      • Ladoo × 1 — ₹20.00

      Total: ₹70.00

      Sorry, I couldn't find: samosa     (omitted if no drops)

      Tap to review and confirm:
      <link>

    Why itemise with prices in the message rather than just linking:
      - Reassures the customer the bot understood them
      - Gives them total upfront before they tap (no bait-and-switch)
      - Surfaces dropped items so they're not surprised something's
        missing when they open the web app
    """
    lines = ["I understood your order:"]
    total = Decimal("0.00")
    for item, unit_price in items_with_price:
        line_total = unit_price * item.quantity
        total += line_total
        lines.append(
            f"• {item.product_name} × {item.quantity} — {_format_price(line_total)}"
        )

    lines.append("")
    lines.append(f"Total: {_format_price(total)}")

    if dropped_names:
        lines.append("")
        # Deduplicate (rare but possible if LLM repeats a hallucination)
        unique_dropped = sorted(set(dropped_names))
        lines.append(f"Sorry, I couldn't find: {', '.join(unique_dropped)}")

    lines.append("")
    lines.append("Tap to review and confirm:")
    lines.append(link)

    return "\n".join(lines)


def handoff_to_web(
    db: Session,
    *,
    customer: Customer,
    matched: list[MatchedItem],
    dropped_names: list[str],
) -> HandoffResult:
    """Write a pre-populated cart, issue a token, build the reply text.

    Args:
        db: active SQLAlchemy session (caller manages lifecycle).
        customer: the customer to issue the link for.
        matched: items successfully resolved to products by the matcher.
        dropped_names: LLM-extracted names that didn't match anything,
            shown to the customer so they know what's missing.

    Returns:
        HandoffResult with the token, link, ready-to-send message text,
        and counts. If matched is empty, message_text will still be
        valid (just no items + only the dropped list), but the caller
        should usually replace it with a friendlier fallback in that
        case — we still return the structure so the caller can decide.
    """
    # Issue a 'new'-kind token. The customer lands on the same web
    # page they'd see if they'd tapped "New order" — only difference
    # is the cart is already populated.
    link, token = issue_link(db, customer=customer, kind="new")

    # Fetch current prices for the matched products in one query.
    # We need this for the message body even though the Redis cart
    # only stores product_id + quantity (the web app re-fetches prices
    # itself on load).
    product_ids = [m.product_id for m in matched]
    products_by_id: dict = {}
    if product_ids:
        rows = db.scalars(select(Product).where(Product.id.in_(product_ids))).all()
        products_by_id = {p.id: p for p in rows}

    # Pair MatchedItem with current unit price. If a product vanished
    # between match and now (extremely unlikely in a 5-second window),
    # we skip it silently.
    items_with_price: list[tuple[MatchedItem, Decimal]] = []
    for m in matched:
        product = products_by_id.get(m.product_id)
        if product is None:
            logger.warning(
                f"Matched product {m.product_id} disappeared before cart write"
            )
            continue
        items_with_price.append((m, product.unit_price))

    # Write the pre-populated cart to Redis. Mirrors the shape that
    # api/v1/cart.py's save_cart endpoint writes — same keys, same
    # types — so the customer web app reads it without any branching.
    cart_cache.save_cart(
        token,
        {
            "customer_id": str(customer.id),
            "kind": "new",
            "items": [
                {"product_id": str(m.product_id), "quantity": m.quantity}
                for m, _price in items_with_price
            ],
        },
    )

    message_text = _build_message_text(items_with_price, dropped_names, link)

    logger.info(
        f"LLM cart handoff for customer {customer.id}: "
        f"{len(items_with_price)} matched, {len(dropped_names)} dropped, "
        f"token={token[:8]}..."
    )

    return HandoffResult(
        token=token,
        link=link,
        message_text=message_text,
        matched_count=len(items_with_price),
        dropped_names=dropped_names,
    )
