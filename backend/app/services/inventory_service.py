"""Inventory service — stock for sealed goods, prep list for the rest.

The bakery sells two kinds of thing, and they need different treatment:

  Stockable      Sealed and packaged — ladoo packets, bread, biscuits,
                 some cakes. Carries over between days, has a countable
                 quantity on hand.

  Made-to-order  Puffs and similar. Baked and sold the same day, no
                 carry-over. "How many in stock" isn't a meaningful
                 question; is_available_today already answers whether
                 they're being made.

Stock is counted in each product's own selling unit. A packet of 25
ladoos is its own product row (see the Product model docstring), so
there's no pack-size conversion anywhere.

Made-to-order items never get stock rows. What the chef needs is a prep
list — how many to bake today — and that's derived from today's orders
at read time. See get_prep_list.

Adjustment timing: stock is deducted when an order is placed, not when
it's delivered. Placement is a reservation, and it's what makes the
low-stock warning mean anything — without it two customers could each
order the last packet in the morning and neither would be warned.
Cancelling an order restores what it held.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product

logger = logging.getLogger(__name__)

# Orders for a given day close at 5 AM that morning. Before then the day's
# demand is still moving, so a prep list would be a moving target; from 5 AM
# it's fixed and worth showing the chef.
ORDER_CUTOFF_HOUR = 5

# After this the day's baking is done and the prep list is noise.
PREP_LIST_END_HOUR = 21


# === Stock levels ===========================================================


def list_stock(db: Session, *, low_only: bool = False) -> list[Product]:
    """Stockable products with their counts, lowest stock first.

    Sorted by how close each is to running out rather than by name — the
    owner opens this page to find out what needs restocking, and that
    should be the first thing on screen.

    Inactive products are excluded; they're not being sold.
    """
    stmt = select(Product).where(
        Product.is_active.is_(True),
        Product.is_stockable.is_(True),
    )

    if low_only:
        stmt = stmt.where(
            Product.low_stock_threshold.is_not(None),
            Product.stock_quantity.is_not(None),
            Product.stock_quantity <= Product.low_stock_threshold,
        )

    # NULLS LAST so untracked products don't crowd the top of a list whose
    # whole purpose is surfacing low counts.
    stmt = stmt.order_by(Product.stock_quantity.asc().nullslast(), Product.name)
    return list(db.scalars(stmt).all())


def count_low_stock(db: Session) -> int:
    """How many stockable products are at or below their threshold.

    Backs the dashboard badge. Cheap enough to poll.
    """
    return (
        db.scalar(
            select(func.count())
            .select_from(Product)
            .where(
                Product.is_active.is_(True),
                Product.is_stockable.is_(True),
                Product.low_stock_threshold.is_not(None),
                Product.stock_quantity.is_not(None),
                Product.stock_quantity <= Product.low_stock_threshold,
            )
        )
        or 0
    )


def is_low_stock(product: Product) -> bool:
    """Whether this product should carry a low-stock warning.

    False for anything untracked or without a threshold — an absent
    threshold means the owner doesn't want to be warned about it.
    """
    if not product.is_stockable:
        return False
    if product.stock_quantity is None or product.low_stock_threshold is None:
        return False
    return product.stock_quantity <= product.low_stock_threshold


def set_stock(db: Session, *, product_id: UUID, quantity: int) -> Product:
    """Set a product's stock to an absolute figure.

    Absolute rather than a delta because this is what the owner does after
    physically counting a shelf. A delta would need them to work out the
    difference, which is exactly the arithmetic that introduces errors.

    Raises ValueError if the product isn't stockable — silently accepting
    a count on a made-to-order item would leave a number nothing maintains.
    """
    product = db.get(Product, product_id)
    if product is None:
        raise ValueError("Product not found.")
    if not product.is_stockable:
        raise ValueError(f"{product.name} isn't a stocked item — it's made to order.")
    if quantity < 0:
        raise ValueError("Stock can't be negative.")

    product.stock_quantity = quantity
    db.flush()
    return product


# === Order hooks ============================================================


def apply_order_items(db: Session, items: list[OrderItem], *, direction: int) -> None:
    """Move stock for a set of order items.

    direction is -1 to deduct (order placed) or +1 to restore (cancelled,
    or items replaced during an edit).

    Two deliberate choices here:

    Stock is allowed to go negative. The count drifts from reality anyway —
    someone sells a packet over the counter without touching the dashboard —
    so refusing an order because a possibly-stale number says zero would be
    worse than showing the owner a negative and letting them correct it. The
    customer sees a warning; the owner decides.

    Products that aren't stockable are skipped rather than erroring. An
    order mixes both kinds routinely.
    """
    if direction not in (-1, 1):
        raise ValueError("direction must be -1 or 1")

    for item in items:
        if item.product_id is None:
            continue  # product hard-deleted; snapshot survives, stock doesn't

        product = db.get(Product, item.product_id)
        if product is None or not product.is_stockable:
            continue
        if product.stock_quantity is None:
            # Stockable but never counted. Starting from an assumed zero
            # would invent a number the owner never entered.
            continue

        product.stock_quantity += direction * item.quantity

    db.flush()


def deduct_for_order(db: Session, order: Order) -> None:
    """Deduct stock for a newly placed order.

    Drafts don't deduct — a cart in progress hasn't reserved anything.
    Neither do cancelled orders, which shouldn't reach here anyway.
    """
    if order.is_draft or order.status == OrderStatus.cancelled:
        return
    apply_order_items(db, list(order.items), direction=-1)


def restore_for_order(db: Session, order: Order) -> None:
    """Put stock back — the order was cancelled, or its items are being
    replaced by an edit."""
    if order.is_draft:
        return
    apply_order_items(db, list(order.items), direction=1)


# === Prep list ==============================================================


def prep_list_is_visible(now: datetime | None = None) -> bool:
    """Whether the prep list should show right now.

    Orders for a day close at 5 AM that morning. Before then demand is
    still moving and a prep list would be a moving target; after the
    baking window it's history.
    """
    now = now or datetime.now()
    return ORDER_CUTOFF_HOUR <= now.hour < PREP_LIST_END_HOUR


def get_prep_list(db: Session, *, for_date: date | None = None) -> list[dict]:
    """How much of each made-to-order item to bake today.

    Derived from today's orders, never stored. Made-to-order items have no
    stock rows — writing them at 5 AM and clearing them later would need a
    scheduler, cleanup, and a story for when the job doesn't run, all to
    reproduce a number that's one query away.

    Cancelled orders and drafts are excluded: nobody's waiting on those.
    """
    for_date = for_date or date.today()

    rows = db.execute(
        select(
            Product.id,
            Product.name,
            Product.unit_label,
            func.sum(OrderItem.quantity).label("quantity"),
            func.count(func.distinct(Order.id)).label("order_count"),
        )
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            Order.order_date == for_date,
            Order.is_draft.is_(False),
            Order.status != OrderStatus.cancelled,
            Product.is_stockable.is_(False),
            Product.is_active.is_(True),
        )
        .group_by(Product.id, Product.name, Product.unit_label)
        .order_by(func.sum(OrderItem.quantity).desc())
    ).all()

    return [
        {
            "product_id": r.id,
            "product_name": r.name,
            "unit_label": r.unit_label,
            "quantity": int(r.quantity or 0),
            "order_count": r.order_count,
        }
        for r in rows
    ]
