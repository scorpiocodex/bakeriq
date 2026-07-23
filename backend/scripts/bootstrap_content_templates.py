"""Bootstrap script — creates BakeriQ's WhatsApp Content Templates.

Idempotent: detects existing templates by friendly_name and reuses their
SIDs rather than creating duplicates. Writes/updates these lines in .env:

    CONTENT_SID_GREETING=HX...
    CONTENT_SID_NAV=HX...
    CONTENT_SID_CART_LINK=HX...
    CONTENT_SID_FALLBACK=HX...
    CONTENT_SID_ORDER_CONFIRMATION=HX...

After running this, restart api + worker so pydantic-settings re-reads
the new .env values, and confirm the five CONTENT_SID_* fields are
declared in backend/app/core/config.py.

Usage:
    docker compose exec api python scripts/bootstrap_content_templates.py

Safe to re-run: prints "exists" for templates that are already created
and only creates missing ones.

NOTE on the cart-link URL: the URL is baked into the template at
creation time. If PUBLIC_BASE_URL changes (e.g. ngrok free-tier
hostname rotates), the existing bakeriq_cart_link template will keep
pointing at the OLD host. Delete the stale template via the Content
API and re-run this script to recreate it with the new URL.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Make this script runnable directly via `python scripts/bootstrap_...`.
# When Python is invoked with a script path, it sets sys.path[0] to the
# script's directory (/app/scripts) and drops the CWD (/app), which
# means `from app.core.config import settings` below can't find the
# `app` package. Inserting /app fixes that without forcing callers to
# use `python -m scripts.bootstrap_content_templates`.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.core.config import settings  # noqa: E402  # path adjusted above
from app.services.twilio_content_service import (  # noqa: E402
    QuickReplyAction,
    TwilioContentClient,
    TwilioContentError,
    UrlAction,
    get_content_client,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"

# Cart link URL pattern. {{1}} is the session token, substituted by
# Twilio at send time. The "/web/new/" prefix is the customer web app's
# canonical entry route — the server-side route handler reads the
# token's `kind` field from the DB to figure out whether this is a new
# order, reorder, or edit flow. So one URL pattern, three scenarios.
CART_LINK_PATH = "/web/new/{{1}}"
INVOICE_LINK_PATH = "/web/invoice/{{1}}"

# Button titles MUST stay verbatim — when the customer taps a button,
# Twilio delivers Body=<title> on the inbound webhook, and the existing
# dispatcher in customer_handler matches against BUTTON_REORDER_LAST /
# BUTTON_NEW_ORDER / BUTTON_ORDER_STATUS constants (lowercased). If you
# change a label here you must change the matching constant too.
BTN_REORDER = "Reorder last"
BTN_NEW = "New order"
BTN_STATUS = "Order status"
BTN_MENU = "Menu"
BTN_INVOICE = "Invoice"


@dataclass(frozen=True)
class TemplateSpec:
    friendly_name: str
    env_var: str
    creator: Callable[[TwilioContentClient], str]


def _create_greeting(client: TwilioContentClient) -> str:
    return client.create_quick_reply(
        friendly_name="bakeriq_greeting",
        body="Hi {{1}}! How can we help today?",
        actions=[
            QuickReplyAction(title=BTN_REORDER, id="btn_reorder_last"),
            QuickReplyAction(title=BTN_NEW, id="btn_new_order"),
            QuickReplyAction(title=BTN_STATUS, id="btn_order_status"),
        ],
        variables={"1": "name"},
    )


def _create_nav(client: TwilioContentClient) -> str:
    """Mid-conversation navigation template.

    Same three action buttons as bakeriq_greeting but with a neutral,
    non-personalised body — used after the bot has just replied to a
    request (menu listing, order status, etc) and wants to prompt the
    customer for their next action. Replaces the legacy "Reply *new
    order* to start ordering." text prompts.
    """
    return client.create_quick_reply(
        friendly_name="bakeriq_nav",
        body="What would you like to do next?",
        actions=[
            QuickReplyAction(title=BTN_REORDER, id="btn_reorder_last"),
            QuickReplyAction(title=BTN_NEW, id="btn_new_order"),
            QuickReplyAction(title=BTN_STATUS, id="btn_order_status"),
        ],
    )


def _create_cart_link(client: TwilioContentClient) -> str:
    cart_url = settings.PUBLIC_BASE_URL.rstrip("/") + CART_LINK_PATH
    return client.create_call_to_action(
        friendly_name="bakeriq_cart_link",
        body="Tap to review and confirm your order:",
        actions=[UrlAction(title="Open cart", url=cart_url)],
        variables={"1": "token"},
    )


def _create_fallback(client: TwilioContentClient) -> str:
    return client.create_quick_reply(
        friendly_name="bakeriq_fallback",
        body="Sorry, I couldn't process that. Pick an option below:",
        actions=[
            QuickReplyAction(title=BTN_MENU, id="btn_menu"),
            QuickReplyAction(title=BTN_NEW, id="btn_new_order"),
            QuickReplyAction(title=BTN_STATUS, id="btn_order_status"),
        ],
    )


def _create_order_confirmation(client: TwilioContentClient) -> str:
    """Post-order-placement confirmation template.

    Sent when the customer finalizes a cart via the web app.
    Preserves the same information as the old free-text confirmation
    (order id, itemized list, total, status update note) but adds
    tappable buttons matching the rest of the bot's UX.

    Variables:
      {{1}} = short order id (first 8 chars of the UUID)
      {{2}} = itemized list, one line per item, newline-separated
              (e.g. "• 2 × Veg Puff — ₹36\\n• 1 × Ladoo — ₹15")
      {{3}} = order total (e.g. "₹51")

    On the itemized list ({{2}}): Twilio has per-variable length limits
    (~1024 chars practical max for template variables). Orders with
    many items risk truncation; template_replies.order_confirmation_reply
    truncates with a "... and N more" tail if the list is too long.
    """
    return client.create_quick_reply(
        friendly_name="bakeriq_order_confirmation",
        body=(
            "Order #{{1}} confirmed!\n\n"
            "{{2}}\n\n"
            "Total: {{3}}\n\n"
            "We'll send updates as your order progresses."
        ),
        actions=[
            QuickReplyAction(title=BTN_STATUS, id="btn_order_status"),
            QuickReplyAction(title=BTN_INVOICE, id="btn_invoice"),
            QuickReplyAction(title=BTN_NEW, id="btn_new_order"),
        ],
        variables={"1": "order_id", "2": "items", "3": "total"},
    )


def _create_registration_link(client: TwilioContentClient) -> str:
    reg_url = settings.PUBLIC_BASE_URL.rstrip("/") + "/web/register/{{1}}"
    return client.create_call_to_action(
        friendly_name="bakeriq_registration_link",
        body="Welcome to BakeriQ! Tap the button to register.",
        actions=[UrlAction(title="Register now", url=reg_url)],
        variables={"1": "token"},
    )


def _create_owner_notification(client: TwilioContentClient) -> str:
    """Owner notification when a new registration lands."""
    dashboard_url = settings.PUBLIC_BASE_URL.rstrip("/") + "/app/approvals"
    return client.create_call_to_action(
        friendly_name="bakeriq_owner_notification",
        body="New registration:\n{{1}} — {{2}}\n\nTap to review on the dashboard.",
        actions=[UrlAction(title="Open dashboard", url=dashboard_url)],
        variables={"1": "name", "2": "phone"},
    )


def _create_invoice_link(client: TwilioContentClient) -> str:
    """
    CTA card carrying a link to the customer's latest invoice.
    Sent in response to the Invoice quick-reply. A separate message
    because Twilio templates can't mix quick-reply and URL buttons —
    same reason the cart link is its own card.
    """
    invoice_url = settings.PUBLIC_BASE_URL.rstrip("/") + INVOICE_LINK_PATH
    return client.create_call_to_action(
        friendly_name="bakeriq_invoice_link",
        body="Here's your latest invoice:",
        actions=[UrlAction(title="View invoice", url=invoice_url)],
        variables={"1": "token"},
    )


TEMPLATES: list[TemplateSpec] = [
    TemplateSpec(
        friendly_name="bakeriq_greeting",
        env_var="CONTENT_SID_GREETING",
        creator=_create_greeting,
    ),
    TemplateSpec(
        friendly_name="bakeriq_nav",
        env_var="CONTENT_SID_NAV",
        creator=_create_nav,
    ),
    TemplateSpec(
        friendly_name="bakeriq_cart_link",
        env_var="CONTENT_SID_CART_LINK",
        creator=_create_cart_link,
    ),
    TemplateSpec(
        friendly_name="bakeriq_fallback",
        env_var="CONTENT_SID_FALLBACK",
        creator=_create_fallback,
    ),
    TemplateSpec(
        friendly_name="bakeriq_order_confirmation",
        env_var="CONTENT_SID_ORDER_CONFIRMATION",
        creator=_create_order_confirmation,
    ),
    TemplateSpec(
        friendly_name="bakeriq_registration_link",
        env_var="CONTENT_SID_REGISTRATION_LINK",
        creator=_create_registration_link,
    ),
    TemplateSpec(
        friendly_name="bakeriq_owner_notification",
        env_var="CONTENT_SID_OWNER_NOTIFICATION",
        creator=_create_owner_notification,
    ),
    TemplateSpec(
        friendly_name="bakeriq_invoice_link",
        env_var="CONTENT_SID_INVOICE_LINK",
        creator=_create_invoice_link,
    ),
]


def upsert_env_var(env_path: Path, key: str, value: str) -> None:
    """Idempotently set `KEY=VALUE` in the .env file.

    Updates the existing line in-place if the key exists; otherwise
    appends. Preserves all other lines (comments and ordering).
    """
    text = env_path.read_text() if env_path.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    new_line = f"{key}={value}"
    if pattern.search(text):
        text = pattern.sub(new_line, text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += new_line + "\n"
    env_path.write_text(text)


def _validate_public_base_url() -> bool:
    url = settings.PUBLIC_BASE_URL
    if not url.startswith(("http://", "https://")):
        print(f"[error] PUBLIC_BASE_URL looks invalid: {url!r}", file=sys.stderr)
        return False
    if "localhost" in url or "127.0.0.1" in url:
        print(
            f"[error] PUBLIC_BASE_URL is {url} — WhatsApp clients cannot "
            "open localhost. Set PUBLIC_BASE_URL in .env to the ngrok "
            "hostname before running this script.",
            file=sys.stderr,
        )
        return False
    return True


def main() -> int:
    if not _validate_public_base_url():
        return 1

    print(f"Using PUBLIC_BASE_URL = {settings.PUBLIC_BASE_URL}")
    print(
        f"Cart link URL         = {settings.PUBLIC_BASE_URL.rstrip('/')}{CART_LINK_PATH}"
    )
    print(f"Env file              = {ENV_FILE}")
    print()

    client = get_content_client()
    sids_to_write: dict[str, str] = {}
    try:
        # One list call → local dict; avoids N round-trips for N templates.
        try:
            existing_by_name: dict[str, str] = {
                t["friendly_name"]: t["sid"]
                for t in client.list_templates()
                if t.get("friendly_name") and t.get("sid")
            }
        except TwilioContentError as e:
            print(f"[error] listing existing templates: {e}", file=sys.stderr)
            return 1

        for spec in TEMPLATES:
            if spec.friendly_name in existing_by_name:
                sid = existing_by_name[spec.friendly_name]
                print(f"  exists  {spec.friendly_name:30s} -> {sid}")
            else:
                try:
                    sid = spec.creator(client)
                except TwilioContentError as e:
                    print(
                        f"[error] creating {spec.friendly_name}: {e}", file=sys.stderr
                    )
                    return 1
                print(f"  created {spec.friendly_name:30s} -> {sid}")
            sids_to_write[spec.env_var] = sid
    finally:
        client.close()

    print()
    print("Generated SIDs:")
    for key, value in sids_to_write.items():
        print(f"  {key}={value}")
    print()

    try:
        for key, value in sids_to_write.items():
            upsert_env_var(ENV_FILE, key, value)
        print(f"Updated {ENV_FILE}")
    except OSError as e:
        print(f"[warn] couldn't write {ENV_FILE}: {e}", file=sys.stderr)
        print("Copy the lines above into .env manually.", file=sys.stderr)

    print()
    print("Next:")
    print("  1. Restart api + worker so pydantic-settings re-reads .env:")
    print("       docker compose restart api worker")
    print("  2. Confirm the five CONTENT_SID_* fields are declared in")
    print("     backend/app/core/config.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
