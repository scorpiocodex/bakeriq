"""Cart API — used by the customer web app to load, save, and place orders.

All endpoints are token-authenticated (no JWT, no session — just the
token from the URL path). The token IS the auth, which is why it must
be unguessable (32 chars URL-safe random) and short-lived (30 min).

Endpoints:
  GET    /api/v1/cart/<token>        — Load the cart payload + menu
  POST   /api/v1/cart/<token>        — Save in-progress cart contents
  POST   /api/v1/cart/<token>/place  — Finalize: create the real Order

The 'cart' response shape includes:
  - kind: 'reorder' | 'new' | 'edit' (drives the web app's title/UX)
  - customer: { id, name }
  - items: list of cart line items with product_id, product_name,
    unit_price, unit_label, quantity, subtotal
  - menu: today's available products (used by 'new order' and edit-add
    flows; included on every response for simplicity)
  - total: pre-computed sum (the web app does its own sum on edit,
    but the server's authoritative total is included on load)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.schemas.order import OrderCreate, OrderItemWrite
from app.services import (
    cart_cache,
    inventory_service,
    order_service,
    template_replies,
    token_service,
    whatsapp_sender,
)
from app.services.conversation_log import get_or_create_conversation

router = APIRouter(prefix="/cart", tags=["cart"])


# === Schemas ===


class CartItemPayload(BaseModel):
    """One line in the cart as sent to/from the web app."""

    product_id: UUID
    quantity: int = Field(ge=0, le=10000)


class CartSavePayload(BaseModel):
    """What the web app POSTs on save — just items, no notes/total
    (server recomputes total; notes editable later via dashboard)."""

    items: list[CartItemPayload]


class CartPlacePayload(BaseModel):
    """What the web app POSTs to finalize. Allows an optional final
    item edit if the customer adjusts on the confirmation screen."""

    items: list[CartItemPayload]


# === Helpers ===


def _resolve_token_or_404(db: Session, token: str):
    """Validate the token; raise 404 if invalid/expired/consumed.

    404 (not 401/403) deliberately — we don't want to leak whether a
    token ever existed. A consumed token, an expired token, and a
    typo'd token all look identical to the caller.
    """
    row = token_service.validate_token(db, token)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This link has expired or is no longer valid. "
            "Please request a new link from the bot.",
        )
    return row


def _build_menu(db: Session) -> list[dict]:
    """Today's available products as JSON-serializable dicts."""
    products = db.scalars(
        select(Product)
        .where(Product.is_active.is_(True))
        .where(Product.is_available_today.is_(True))
        .order_by(Product.name)
    ).all()

    return [
        {
            "id": str(p.id),
            "name": p.name,
            "unit_price": float(p.unit_price),
            "unit_label": p.unit_label,
            "category_id": str(p.category_id),
            "category_name": p.category.name if p.category else None,
            # Advisory only. The exact count isn't exposed — it drifts
            # (someone sells a packet over the counter without touching
            # the dashboard), so promising "2 left" invites complaints
            # when a customer orders 3 and the bakery has 1. Ordering is
            # never blocked on this; the owner decides.
            "is_low_stock": inventory_service.is_low_stock(p),
        }
        for p in products
    ]


def _items_from_last_order(db: Session, customer_id: UUID) -> list[dict]:
    """Pre-fill items from the customer's most recent non-draft order.
    Used for the 'reorder' kind. Empty list if no prior orders.

    Quantities and product names are copied from the order's snapshotted
    fields, but CURRENT prices are used (not the snapshotted unit_price
    from the past order — prices may have changed).
    """
    last = db.scalar(
        select(Order)
        .where(Order.customer_id == customer_id)
        .where(Order.is_draft.is_(False))
        .where(Order.status != OrderStatus.cancelled)
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    if last is None:
        return []

    result = []
    for item in last.items:
        # Reuse the product if it still exists + is available; otherwise
        # skip silently (the snapshot survives in history but we can't
        # add an unavailable product to a new order).
        product = db.get(Product, item.product_id)
        if product is None or not product.is_active or not product.is_available_today:
            continue
        result.append(
            {
                "product_id": str(product.id),
                "product_name": product.name,
                "unit_price": float(product.unit_price),
                "unit_label": product.unit_label,
                "quantity": item.quantity,
                "subtotal": float(product.unit_price) * item.quantity,
            }
        )
    return result


def _items_from_cart_cache(db: Session, token: str) -> list[dict] | None:
    """Pull in-progress cart items from Redis if they exist.

    Returns the items list (possibly empty) if a cart exists, or None
    if no cart has been saved for this token yet.
    """
    raw = cart_cache.get_cart(token)
    if raw is None:
        return None
    return raw.get("items", [])


def _build_items_with_pricing(
    db: Session,
    raw_items: list[dict],
) -> list[dict]:
    """Given raw items (from cart cache OR client POST), enrich with
    current product name/price/unit_label/subtotal.

    Drops any item whose product_id no longer matches an active,
    available product."""
    result = []
    for entry in raw_items:
        product_id = entry.get("product_id")
        quantity = entry.get("quantity", 0)
        if not product_id or quantity <= 0:
            continue

        product = db.get(Product, UUID(str(product_id)))
        if product is None or not product.is_active or not product.is_available_today:
            continue

        unit_price = float(product.unit_price)
        result.append(
            {
                "product_id": str(product.id),
                "product_name": product.name,
                "unit_price": unit_price,
                "unit_label": product.unit_label,
                "quantity": int(quantity),
                "subtotal": unit_price * int(quantity),
            }
        )
    return result


# === Endpoints ===


@router.get("/{token}")
def load_cart(token: str, db: Session = Depends(get_db)) -> dict:
    """Load the cart payload for this token.

    Logic by kind:
      - 'reorder': prefer cached cart; else fetch last order; else empty
      - 'new':     prefer cached cart; else empty
      - 'edit':    require cached cart (else 404)
    """
    row = _resolve_token_or_404(db, token)
    customer = row.customer

    cached = _items_from_cart_cache(db, token)

    if row.kind == "edit":
        if cached is None:
            # 'edit' implies there's a cart in progress — if none, the
            # link is stale (customer abandoned and came back too late).
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No cart in progress for this link. "
                "Please start a new order from the bot.",
            )
        items = _build_items_with_pricing(db, cached)
    elif cached is not None:
        items = _build_items_with_pricing(db, cached)
    elif row.kind == "reorder":
        items = _items_from_last_order(db, customer.id)
    else:  # 'new'
        items = []

    total = sum(item["subtotal"] for item in items)

    return {
        "token": token,
        "kind": row.kind,
        "customer": {
            "id": str(customer.id),
            "name": customer.name,
        },
        "items": items,
        "total": total,
        "menu": _build_menu(db),
    }


@router.post("/{token}")
def save_cart(
    token: str,
    payload: CartSavePayload,
    db: Session = Depends(get_db),
) -> dict:
    """Save in-progress cart edits to Redis. Does NOT create an order.

    The web app calls this on every Save action (and could call it on
    every quantity change for autosave, though we won't enable that
    initially — too chatty for slow connections).
    """
    row = _resolve_token_or_404(db, token)

    # Re-validate items against current product availability + price
    items = _build_items_with_pricing(
        db,
        [item.model_dump() for item in payload.items],
    )

    cart_cache.save_cart(
        token,
        {
            "customer_id": str(row.customer_id),
            "kind": row.kind,
            "items": [
                {"product_id": item["product_id"], "quantity": item["quantity"]}
                for item in items
            ],
        },
    )

    total = sum(item["subtotal"] for item in items)
    return {
        "ok": True,
        "items": items,
        "total": total,
    }


@router.post("/{token}/place")
def place_order(
    token: str,
    payload: CartPlacePayload,
    db: Session = Depends(get_db),
) -> dict:
    """Finalize the cart into a real Order, consume the token, and send
    the customer a WhatsApp confirmation.

    Steps:
      1. Validate items against current products (drop unavailable)
      2. Reject empty carts (would be a no-op order)
      3. Create the Order via the existing order_service (is_draft=False;
         this is a real order, manual-style)
      4. Consume the token
      5. Clear the Redis cart
      6. Send the WhatsApp confirmation (best-effort; doesn't block the
         response if Twilio fails)
    """
    row = _resolve_token_or_404(db, token)
    customer = row.customer

    items = _build_items_with_pricing(
        db,
        [item.model_dump() for item in payload.items],
    )
    if not items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cart is empty — add at least one item before placing.",
        )

    # Build OrderCreate payload via existing service
    order_payload = OrderCreate(
        customer_id=customer.id,
        items=[
            OrderItemWrite(
                product_id=UUID(item["product_id"]),
                quantity=item["quantity"],
            )
            for item in items
        ],
    )
    order = order_service.create_order(db, order_payload)

    # Lock the token
    token_service.consume_token(db, row)

    # Clear Redis
    cart_cache.delete_cart(token)

    db.commit()

    # Send confirmation. Best-effort — if Twilio is down, the order is
    # still real and the customer sees the success state in the web app.
    conversation = get_or_create_conversation(
        db,
        phone=customer.primary_phone,
        customer_id=customer.id,
    )

    # Build the itemized list for the template's {{2}} variable.
    # Structured as one line per item; the template body wraps this
    # in the "Order #X confirmed!" preamble and the total + status
    # tail. See services/template_replies.order_confirmation_reply.
    item_lines = [
        f"• {item['quantity']} × {item['product_name']} — ₹{item['subtotal']:.0f}"
        for item in items
    ]
    reply = template_replies.order_confirmation_reply(
        short_id=str(order.id)[:8],
        items_summary="\n".join(item_lines),
        total=f"₹{order.total_amount:.0f}",
    )
    whatsapp_sender.send_reply(
        db,
        conversation_id=conversation.id,
        to_phone=customer.primary_phone,
        reply=reply,
    )
    db.commit()

    return {
        "ok": True,
        "order_id": str(order.id),
        "total": float(order.total_amount),
        "items": items,
    }
