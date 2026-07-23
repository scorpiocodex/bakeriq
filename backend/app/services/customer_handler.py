"""Returning-customer handler — bot logic for registered customers.

Entry point: handle_customer_message(db, customer, body) returns either
a list of Reply objects to send back, or None if no fast-path keyword
matched (caller routes to the LLM safety valve).

Fast-path keyword matching only — no LLM call from this layer.

Routing happens in two layers:

  1. State-aware: if conversation state is 'awaiting_confirmation',
     YES / NO / MODIFY / PLACE are matched first because they're
     contextual.

  2. Stateless keyword: greetings, menu queries, status queries — these
     work regardless of conversation state and are the most common
     inbound messages. Also matches the verbatim button labels delivered
     by the bakeriq_* Content Templates.

Most handlers return [text_reply, nav_reply] — a prose answer followed
by the bakeriq_nav template with three tappable buttons (Reorder last /
New order / Order status). Reorder/new-order link replies use the
bakeriq_cart_link template instead. Template-related Reply factories
live in app.services.template_replies so the LLM safety-valve path in
tasks/llm.py can produce the same UX.

the order-confirmation card now carries Invoice in place of Menu.
"""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.customer import Customer
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.services import conversation_state as conv_state
from app.services import token_service
from app.services.reply import Reply
from app.services.template_replies import cart_link_reply, invoice_link_reply, nav_reply

# === Keyword sets ===
# Keep these as frozenset for O(1) lookup. Lowercased on the way in;
# customer's message is also lowercased before matching.

GREETINGS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "hai",
        "namaskaram",
        "namaste",
        "vanakkam",
        "good morning",
        "good afternoon",
        "good evening",
    }
)

MENU_KEYWORDS = frozenset(
    {
        "menu",
        "items",
        "what's available",
        "whats available",
        "today's menu",
        "todays menu",
        "what do you have",
    }
)

STATUS_KEYWORDS = frozenset(
    {
        "status",
        "order status",
        "my order",
        "track order",
    }
)

# Button labels — these are the exact strings Twilio delivers as Body
# when a customer taps a quick-reply button on a bakeriq_* Content
# Template. Lowercased for matching. If you change a button title in
# scripts/bootstrap_content_templates.py you MUST change the matching
# constant here too — the dispatcher relies on string equality.
BUTTON_REORDER_LAST = "reorder last"
BUTTON_NEW_ORDER = "new order"
BUTTON_ORDER_STATUS = "order status"
BUTTON_MENU = "menu"  # used in the bakeriq_fallback template
BUTTON_INVOICE = "invoice"

CONFIRM_KEYWORDS = frozenset(
    {
        "yes",
        "y",
        "confirm",
        "ok",
        "okay",
        "sheri",
        "place order",
    }
)

CANCEL_KEYWORDS = frozenset(
    {
        "no",
        "n",
        "cancel",
        "venda",
        "stop",
    }
)

MODIFY_KEYWORDS = frozenset(
    {
        "modify",
        "edit",
        "change",
        "update",
    }
)

INVOICE_KEYWORDS = frozenset(
    {
        "invoice",
        "bill",
        "receipt",
        "my invoice",
        "my bill",
    }
)


# === Reply text fragments ===
# Static prose; template bodies live in Twilio and are referenced by
# CONTENT_SID_* settings.

MSG_ORDER_STATUS_TEMPLATE = (
    "*Order #{short_id}*\nPlaced: {placed}\n\n{status_emoji} {status_label}\n\n{footer}"
)

MSG_NO_ORDERS = "You don't have any orders with us yet."

MSG_REORDER_NO_HISTORY = "You don't have any previous orders yet."

MSG_NO_ITEMS_TODAY = "Sorry, no items are available today. Please check back tomorrow!"

MSG_NO_INVOICE = (
    "You don't have any invoices yet — place an order first and one "
    "will be waiting for you here."
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
    OrderStatus.cancelled: "Tap *New order* below if you'd like to place another.",
}


# === Main dispatch ===


def handle_customer_message(
    db: Session,
    customer: Customer,
    body: str,
) -> list[Reply] | None:
    """Handle an inbound message from a registered customer.

    Returns a non-empty list of Reply objects to send back, OR None if
    the message didn't match any fast-path keyword (caller should route
    to LLM safety valve).
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

    # === Stateless keyword + button matches ===

    if text in GREETINGS or _matches_phrase(text, GREETINGS):
        return _build_greeting(customer)

    if (
        text in MENU_KEYWORDS
        or _matches_phrase(text, MENU_KEYWORDS)
        or text == BUTTON_MENU
    ):
        return _build_menu(db)

    if text in STATUS_KEYWORDS or text == BUTTON_ORDER_STATUS:
        return _build_order_status(db, customer)

    if text == BUTTON_REORDER_LAST:
        return _build_reorder_link(db, customer)

    if text == BUTTON_NEW_ORDER:
        return _build_new_order_link(db, customer)

    if text in INVOICE_KEYWORDS or text == BUTTON_INVOICE:
        return _build_invoice_link(db, customer)

    # No fast-path match — caller will route to LLM
    return None


# === Helpers ===


def _matches_phrase(text: str, keywords: frozenset[str]) -> bool:
    """Loose match: 'hi anita how are you' matches the 'hi' keyword.

    Cheaper than full NLP — just checks if the message starts with any
    keyword.
    """
    first_word = text.split(maxsplit=1)[0] if text else ""
    return first_word in keywords


def _build_greeting(customer: Customer) -> list[Reply]:
    """Personalized greeting with three nav buttons.

    Uses the bakeriq_greeting Content Template — body is "Hi {{1}}! How
    can we help today?" with three quick-reply buttons. Falls back to
    plain text + a separate nav template if the greeting SID isn't
    bootstrapped.

    Note: the previous text-only version varied "Good morning / afternoon
    / evening" by time of day. Content Templates are static at the body
    level, so we lose that variation — could be restored later with
    three time-variant templates if it becomes a requirement.
    """
    first_name = customer.name.split()[0] if customer.name else "there"
    sid = settings.CONTENT_SID_GREETING
    if sid is None:
        return [
            Reply.text(f"Hi {first_name}! How can we help today?"),
            nav_reply(),
        ]
    return [
        Reply.template(
            sid,
            variables={"1": first_name},
            log_body=f"Hi {first_name}! How can we help today?",
        ),
    ]


def _build_menu(db: Session) -> list[Reply]:
    """Today's available products, grouped by category, plus nav buttons.

    Returns one Reply with the menu prose and a second Reply with the
    bakeriq_nav template. If no items are available today, returns only
    the apology — offering nav buttons in that case would lead the
    customer into a flow that can't be completed.
    """
    products = db.scalars(
        select(Product)
        .where(Product.is_active.is_(True))
        .where(Product.is_available_today.is_(True))
        .order_by(Product.name)
    ).all()

    if not products:
        return [Reply.text(MSG_NO_ITEMS_TODAY)]

    # Group by category for readability
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

    # Drop trailing blank line so the message ends cleanly
    while lines and lines[-1] == "":
        lines.pop()

    return [Reply.text("\n".join(lines)), nav_reply()]


def _build_order_status(db: Session, customer: Customer) -> list[Reply]:
    """Most recent non-draft order's status, plus nav buttons.

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
        return [Reply.text(MSG_NO_ORDERS), nav_reply()]

    emoji, label = STATUS_DISPLAY[latest.status]
    text = MSG_ORDER_STATUS_TEMPLATE.format(
        short_id=str(latest.id)[:8],
        placed=latest.created_at.strftime("%I:%M %p, %d %b"),
        status_emoji=emoji,
        status_label=label,
        footer=STATUS_FOOTER[latest.status],
    )
    return [Reply.text(text), nav_reply()]


def _build_reorder_link(db: Session, customer: Customer) -> list[Reply]:
    """Issue a 'reorder' token and return a cart-link template message.

    If the customer has no prior orders, returns a "no history" text
    reply plus nav buttons rather than issuing a link to an empty cart.
    """
    last = db.scalar(
        select(Order)
        .where(Order.customer_id == customer.id)
        .where(Order.is_draft.is_(False))
        .where(Order.status != OrderStatus.cancelled)
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    if last is None:
        return [Reply.text(MSG_REORDER_NO_HISTORY), nav_reply()]

    from app.services import web_link_service

    link, _ = web_link_service.issue_link(db, customer=customer, kind="reorder")
    token = link.rsplit("/", 1)[-1]
    return [cart_link_reply(token, link)]


def _build_new_order_link(db: Session, customer: Customer) -> list[Reply]:
    """Issue a 'new' token and return a cart-link template message."""
    from app.services import web_link_service

    link, _ = web_link_service.issue_link(db, customer=customer, kind="new")
    token = link.rsplit("/", 1)[-1]
    return [cart_link_reply(token, link)]


def _build_invoice_link(db: Session, customer: Customer) -> list[Reply]:
    """
    Issue an invoice token and return a CTA card linking to it.
    Twilio templates can't mix quick-reply and URL buttons, so Invoice
    is a quick-reply on the confirmation card and the link arrives as
    this separate CTA card. Same shape as the cart-link flow.

    The token is minted here rather than baked into the confirmation
    card, so it's fresh whenever the customer asks — and it points at
    "latest invoice" rather than a fixed date, so tapping it after a
    second order the same day shows both.

    Cancelled and draft orders don't count as having an invoice: a
    document listing only a voided order isn't one the customer wants.
    """
    latest = db.scalar(
        select(Order)
        .where(Order.customer_id == customer.id)
        .where(Order.is_draft.is_(False))
        .where(Order.status != OrderStatus.cancelled)
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    if latest is None:
        return [Reply.text(MSG_NO_INVOICE), nav_reply()]

    row = token_service.issue_token(db, customer=customer, kind="invoice")

    # Built from PUBLIC_BASE_URL, not web_link_service — that helper
    # uses CUSTOMER_WEB_BASE_URL, which in dev points at the Vite port
    # directly and isn't reachable from a customer's phone. This link is
    # only the text fallback (the template carries the real URL), but a
    # fallback nobody can open isn't a fallback.
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    link = f"{base}/web/invoice/{row.token}"

    return [invoice_link_reply(row.token, link)]
