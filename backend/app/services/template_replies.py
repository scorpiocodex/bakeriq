"""Content Template Reply factories shared by handlers and tasks.

These factories wrap CONTENT_SID_* template references in Reply objects,
with graceful text fallbacks when the SID isn't bootstrapped yet (fresh
checkout that hasn't run scripts/bootstrap_content_templates.py). Both
the fast-path customer_handler and the LLM safety-valve task in
tasks/llm.py import from here so the rendered UX matches across both
paths — when the team lead taps "New order" via the greeting card vs.
when an LLM-parsed message produces a cart-link card, they're literally
the same Twilio Content Template rendering.
"""

from __future__ import annotations

from app.core.config import settings
from app.services.reply import Reply


def cart_link_reply(token: str, link: str) -> Reply:
    """Cart-link Content Template Reply.

    The customer sees a card with body "Tap to review and confirm your
    order:" and an Open cart button that navigates to the issued link.
    Falls back to a plain-text URL message if CONTENT_SID_CART_LINK
    isn't set.

    Args:
        token: The web session token (last path segment of `link`).
            Substituted into the template's URL via {{1}}.
        link: The full cart link, used as both the audit-log body and
            the fallback message body.
    """
    sid = settings.CONTENT_SID_CART_LINK
    if sid is None:
        return Reply.text(
            f"Tap here to open your cart:\n\n{link}\n\n"
            "_The link expires in 30 minutes._"
        )
    return Reply.template(
        sid,
        variables={"1": token},
        log_body=f"Tap to review and confirm your order: {link}",
    )


def nav_reply() -> Reply:
    """Mid-conversation nav Reply — Reorder/New/Status buttons.

    Used after a substantive bot reply (menu listing, order status,
    LLM no-match apology, etc.) to offer the customer their next
    action. Falls back to a text prompt if CONTENT_SID_NAV isn't set.
    """
    sid = settings.CONTENT_SID_NAV
    if sid is None:
        return Reply.text("Reply *menu*, *new order*, or *order status* to continue.")
    return Reply.template(
        sid,
        log_body="What would you like to do next? "
        "[Reorder last / New order / Order status]",
    )


def fallback_reply() -> Reply:
    """Fallback Reply — Menu/New/Status buttons.

    Used when the bot received input it understood as an order intent
    but couldn't match any item to today's menu. Includes a Menu button
    (unlike nav_reply which only offers Reorder/New/Status) because
    customers in this branch typically need to see what IS available
    rather than reorder.

    Falls back to a text prompt if CONTENT_SID_FALLBACK isn't set.
    """
    sid = settings.CONTENT_SID_FALLBACK
    if sid is None:
        return Reply.text("Reply *menu*, *new order*, or *order status* to continue.")
    return Reply.template(
        sid,
        log_body="Sorry, I couldn't process that. [Menu / New order / Order status]",
    )
