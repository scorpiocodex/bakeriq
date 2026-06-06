"""Returning-customer handler — bot logic for registered customers.

Entry point: handle_customer_message(db, customer, body) returns a reply.
Caller is the webhook dispatcher.

Fast-path keyword matching only — no LLM call from this layer. Anything
that doesn't match falls through to the LLM safety valve (Task 6).

Routing happens in two layers:

  1. State-aware: if conversation state is 'awaiting_confirmation',
     YES / NO / MODIFY / PLACE are matched first because they're
     contextual.

  2. Stateless keyword: greetings, menu queries, status queries — these
     work regardless of conversation state and are the most common
     inbound messages.

A non-match returns None — the caller routes that to the LLM safety
valve. Returning None vs an empty string is intentional: empty string
would still get sent as a (blank) reply.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.services import conversation_state as conv_state


# === Keyword sets ===
# Keep these as frozenset for O(1) lookup. Lowercased on the way in;
# customer's message is also lowercased before matching.

GREETINGS = frozenset({
    "hi", "hello", "hey", "hai", "namaskaram", "namaste", "vanakkam",
    "good morning", "good afternoon", "good evening",
})

MENU_KEYWORDS = frozenset({
    "menu", "items", "what's available", "whats available",
    "today's menu", "todays menu", "what do you have",
})

STATUS_KEYWORDS = frozenset({
    "status", "order status", "my order", "track order",
})

# Three buttons in the returning-customer menu. The button LABELS sent
# from Twilio are what come back as message body when tapped — match
# exactly.
BUTTON_REORDER_LAST = "reorder last"
BUTTON_NEW_ORDER = "new order"
BUTTON_ORDER_STATUS = "order status"

CONFIRM_KEYWORDS = frozenset({
    "yes", "y", "confirm", "ok", "okay", "sheri", "place order",
})

CANCEL_KEYWORDS = frozenset({
    "no", "n", "cancel", "venda", "stop",
})

MODIFY_KEYWORDS = frozenset({
    "modify", "edit", "change", "update",
})


# === Reply templates ===

GREETING_PERIOD_TIMES = {
    "morning": "Good morning",
    "afternoon": "Good afternoon",
    "evening": "Good evening",
}


def _time_of_day_greeting() -> str:
    """Return time-appropriate greeting ('Good morning' etc) based on the
    bakery's local time."""
    from datetime import datetime
    h = datetime.now().hour
    if h < 12:
        return GREETING_PERIOD_TIMES["morning"]
    if h < 17:
        return GREETING_PERIOD_TIMES["afternoon"]
    return GREETING_PERIOD_TIMES["evening"]


MSG_GREETING_REGISTERED = (
    "{greeting} {name}!\n"
    "\n"
    "The bakery is open today. What would you like to do?\n"
    "\n"
    "Reply with:\n"
    "• *Reorder last* — your previous order, ready to confirm\n"
    "• *New order* — pick fresh items\n"
    "• *Order status* — check your latest order"
)

MSG_ORDER_STATUS_TEMPLATE = (
    "*Order #{short_id}*\n"
    "Placed: {placed}\n"
    "\n"
    "{status_emoji} {status_label}\n"
    "\n"
    "{footer}"
)

MSG_NO_ORDERS = (
    "You don't have any orders with us yet.\n"
    "\n"
    "Reply *new order* to place your first one!"
)

STATUS_DISPLAY = {
    OrderStatus.received: ("📥", "Received — we're getting started"),
    OrderStatus.preparing: ("🍳", "Preparing — being made now"),
    OrderStatus.ready: ("📦", "Ready — waiting for delivery"),
    OrderStatus.delivering: ("🚴", "Delivering — on its way"),
    OrderStatus.cancelled: ("❌", "Cancelled"),
}

STATUS_FOOTER = {
    OrderStatus.received: "We'll start preparing it shortly.",
    OrderStatus.preparing: "You'll get a message when it's ready.",
    OrderStatus.ready: "Out for delivery very soon.",
    OrderStatus.delivering: "Should arrive any moment.",
    OrderStatus.cancelled: "Send *new order* if you'd like to place another.",
}


# === Main dispatch ===

def handle_customer_message(
    db: Session,
    customer: Customer,
    body: str,
) -> str | None:
    """Handle an inbound message from a registered customer.

    Returns the bot's reply text, OR None if the message didn't match
    any fast-path keyword (caller should route to LLM safety valve).
    """
    text = body.strip().lower()

    # === State-aware matches: only meaningful in specific states ===
    state = conv_state.get_state(customer.primary_phone)
    if state and state.get("state") == "awaiting_confirmation":
        if text in CONFIRM_KEYWORDS:
            return None  # Confirmation logic isn't built yet — Task 5 handles this
        if text in CANCEL_KEYWORDS:
            return None  # Same
        if text in MODIFY_KEYWORDS:
            return None  # Same

    # === Stateless keyword matches ===

    if text in GREETINGS or _matches_phrase(text, GREETINGS):
        return _build_greeting(customer)

    if text in MENU_KEYWORDS or _matches_phrase(text, MENU_KEYWORDS):
        return _build_menu(db)

    if text in STATUS_KEYWORDS or text == BUTTON_ORDER_STATUS:
        return _build_order_status(db, customer)

    if text == BUTTON_REORDER_LAST:
        return None  # Web-app link issuance — comes in Task 5

    if text == BUTTON_NEW_ORDER:
        return None  # Web-app link issuance — comes in Task 5

    # No fast-path match — caller will route to LLM
    return None


# === Helpers ===

def _matches_phrase(text: str, keywords: frozenset[str]) -> bool:
    """Loose match: 'hi anita how are you' matches the 'hi' keyword.

    Cheaper than full NLP — just checks if the message starts with any
    keyword, or is short enough that the keyword is the meaningful part.
    """
    # Single-word check: if text is one word, exact match against the set.
    # If multi-word, check the first word matches.
    first_word = text.split(maxsplit=1)[0] if text else ""
    return first_word in keywords


def _build_greeting(customer: Customer) -> str:
    """Greeting reply with menu prompt — used for first contact of a
    session with a registered customer."""
    # Use first name only for the greeting (more natural).
    first_name = customer.name.split()[0] if customer.name else "there"
    return MSG_GREETING_REGISTERED.format(
        greeting=_time_of_day_greeting(),
        name=first_name,
    )


def _build_menu(db: Session) -> str:
    """Today's available products, grouped by category."""
    products = db.scalars(
        select(Product)
        .where(Product.is_active.is_(True))
        .where(Product.is_available_today.is_(True))
        .order_by(Product.name)
    ).all()

    if not products:
        return (
            "Sorry, no items are available today. "
            "Please check back tomorrow!"
        )

    # Group by category for readability
    from collections import defaultdict
    by_category: dict[str, list[Product]] = defaultdict(list)
    for p in products:
        cat_name = p.category.name.capitalize() if p.category else "Other"
        by_category[cat_name].append(p)

    lines = ["*Today's menu*", ""]
    for category in sorted(by_category.keys()):
        lines.append(f"*{category}*")
        for p in by_category[category]:
            lines.append(f"• {p.name} — ₹{p.unit_price:.0f} / {p.unit_label}")
        lines.append("")

    lines.append("Reply *new order* to start ordering.")
    return "\n".join(lines)


def _build_order_status(db: Session, customer: Customer) -> str:
    """Most recent non-draft order's status, or 'no orders' if none.

    'Non-draft' filter is important — bot-created in-flight orders that
    haven't been confirmed yet shouldn't be reported back to the customer
    as if they existed.
    """
    latest = db.scalar(
        select(Order)
        .where(Order.customer_id == customer.id)
        .where(Order.is_draft.is_(False))
        .order_by(Order.created_at.desc())
        .limit(1)
    )

    if latest is None:
        return MSG_NO_ORDERS

    emoji, label = STATUS_DISPLAY[latest.status]
    return MSG_ORDER_STATUS_TEMPLATE.format(
        short_id=str(latest.id)[:8],
        placed=latest.created_at.strftime("%I:%M %p, %d %b"),
        status_emoji=emoji,
        status_label=label,
        footer=STATUS_FOOTER[latest.status],
    )
