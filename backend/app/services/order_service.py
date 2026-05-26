"""Order business logic — the most logic-heavy service in the project.

Three responsibilities beyond plain CRUD:
  1. SNAPSHOT: when building order items, copy product name/price/unit from
     the live product and compute each subtotal. The order becomes a frozen
     historical record.
  2. TOTAL: sum the item subtotals into order.total_amount at write time.
  3. STATUS TRANSITIONS: validate moves through the lifecycle.

Plus a helper to PRE-FILL order items from a customer's default order
template (the convenience wired to the "Load default order" button).
"""

from datetime import date
from uuid import UUID

from app.models.customer import Customer
from app.models.default_order import DefaultOrder
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product
from app.schemas.order import OrderCreate, OrderItemWrite, OrderUpdate
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# === Allowed status transitions =============================================
# Forward flow plus cancel-from-anywhere. A cancelled order is terminal.
# We allow moving backward one notch too (e.g. ready -> preparing) because
# real bakeries fix mistakes; what we forbid is resurrecting a cancelled
# order or jumping to a nonsensical state.
_FORWARD = [
    OrderStatus.received,
    OrderStatus.preparing,
    OrderStatus.ready,
    OrderStatus.delivering,
]


def _validate_transition(current: OrderStatus, target: OrderStatus) -> None:
    """Raise 422 if a status move isn't allowed.

    Rules:
      - Same status -> no-op, allowed (idempotent).
      - Anything -> cancelled: allowed.
      - cancelled -> anything: forbidden (terminal).
      - Within the forward chain: allow moving to any adjacent step in
        either direction (forward to progress, back one to correct a
        mistake). We keep it permissive but block cancelled resurrection
        and unknown jumps.
    """
    if current == target:
        return
    if target == OrderStatus.cancelled:
        return
    if current == OrderStatus.cancelled:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A cancelled order cannot be reactivated. Create a new order.",
        )
    # Both are in the forward chain — allow any move within it. (We chose
    # not to over-constrain to strictly-adjacent steps; the owner knows
    # their workflow and may skip, e.g., received -> ready directly.)
    return


def _validate_customer(db: Session, customer_id: UUID) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    return customer


def _build_items(
    db: Session, item_writes: list[OrderItemWrite]
) -> tuple[list[OrderItem], float]:
    """Turn [{product_id, quantity}] into snapshotted OrderItems + total.

    Validates every product exists and is active (one batched query).
    Snapshots name/price/unit and computes subtotal per line. Returns the
    list of OrderItem objects (not yet attached to an order) and the summed
    total.
    """
    if not item_writes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="An order must have at least one item",
        )

    requested_ids = {iw.product_id for iw in item_writes}
    found = db.scalars(select(Product).where(Product.id.in_(requested_ids))).all()
    by_id = {p.id: p for p in found}

    items: list[OrderItem] = []
    total = 0.0
    for iw in item_writes:
        product = by_id.get(iw.product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Product with id {iw.product_id} does not exist",
            )
        if not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Product '{product.name}' is inactive and can't be ordered",
            )
        # Snapshot
        unit_price = float(product.unit_price)
        subtotal = round(unit_price * iw.quantity, 2)
        items.append(
            OrderItem(
                product_id=product.id,
                product_name=product.name,
                unit_price=unit_price,
                unit_label=product.unit_label,
                quantity=iw.quantity,
                subtotal=subtotal,
            )
        )
        total += subtotal

    return items, round(total, 2)


# === CRUD ===================================================================


def create_order(db: Session, payload: OrderCreate) -> Order:
    _validate_customer(db, payload.customer_id)
    items, total = _build_items(db, payload.items)

    order = Order(
        customer_id=payload.customer_id,
        status=payload.status,
        order_date=payload.order_date or date.today(),
        notes=payload.notes,
        total_amount=total,
        items=items,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def get_order(db: Session, order_id: UUID) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    return order


def list_orders(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
    status_filter: OrderStatus | None = None,
    customer_id: UUID | None = None,
    order_date: date | None = None,
) -> tuple[list[Order], int]:
    """List orders newest-first, with optional filters. Returns (orders, total).

    The endpoint maps each Order to the compact OrderListItem (with item_count).
    """
    query = select(Order)
    count_query = select(func.count()).select_from(Order)

    conditions = []
    if status_filter is not None:
        conditions.append(Order.status == status_filter)
    if customer_id is not None:
        conditions.append(Order.customer_id == customer_id)
    if order_date is not None:
        conditions.append(Order.order_date == order_date)

    for c in conditions:
        query = query.where(c)
        count_query = count_query.where(c)

    total = db.scalar(count_query) or 0
    query = query.order_by(Order.created_at.desc()).offset(skip).limit(limit)
    orders = db.scalars(query).all()
    return list(orders), total


def update_order(db: Session, order_id: UUID, payload: OrderUpdate) -> Order:
    """Edit an order's date/notes and optionally replace its items.

    Status is NOT changed here — that goes through change_status. If items
    are provided, they're rebuilt (re-snapshotted) and the total recomputed.
    """
    order = get_order(db, order_id)

    if payload.order_date is not None:
        order.order_date = payload.order_date
    if payload.notes is not None:
        order.notes = payload.notes

    if payload.items is not None:
        items, total = _build_items(db, payload.items)
        order.items = items  # replace-all via delete-orphan cascade
        order.total_amount = total

    db.commit()
    db.refresh(order)
    return order


def change_status(db: Session, order_id: UUID, target: OrderStatus) -> Order:
    order = get_order(db, order_id)
    _validate_transition(order.status, target)
    order.status = target
    db.commit()
    db.refresh(order)
    return order


def delete_order(db: Session, order_id: UUID) -> None:
    """Hard-delete an order (and its items via cascade).

    Note: we generally prefer cancelling over deleting (cancel keeps the
    record). Delete is here for genuine mistakes — a test order, a duplicate.
    """
    order = get_order(db, order_id)
    db.delete(order)
    db.commit()


# === Pre-fill from default order ============================================


def build_prefill_items_from_default(db: Session, customer_id: UUID) -> list[dict]:
    """Read a customer's default order template and return suggested order
    lines as [{product_id, product_name, unit_price, unit_label, quantity}].

    Used by the "Load default order" convenience. Inactive products in the
    template are SKIPPED (with the caller able to see what was dropped by
    comparing counts). Prices are the CURRENT product prices (fresh), not
    stored on the template.

    Returns an empty list if the customer has no template. Raises 404 only
    if the customer themselves doesn't exist.
    """
    _validate_customer(db, customer_id)

    default_order = db.scalars(
        select(DefaultOrder).where(DefaultOrder.customer_id == customer_id)
    ).first()
    if default_order is None:
        return []

    suggestions: list[dict] = []
    for item in default_order.items:
        product = item.product
        if product is None or not product.is_active:
            continue  # skip unavailable products
        suggestions.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "unit_price": float(product.unit_price),
                "unit_label": product.unit_label,
                "quantity": item.quantity,
            }
        )
    return suggestions
