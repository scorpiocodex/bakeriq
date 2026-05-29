"""Dashboard summary service — aggregate queries over existing data.

All numbers are computed from orders/customers/products. No new tables.
Designed to run in a handful of efficient queries rather than loading rows
into Python and counting.
"""

from datetime import date

from app.models.customer import Customer
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# Statuses that count as "in progress" (being worked, not yet done/cancelled)
_IN_PROGRESS = [OrderStatus.preparing, OrderStatus.ready, OrderStatus.delivering]
# Board columns — the active lifecycle stages (cancelled excluded from board)
_BOARD_STATUSES = [
    OrderStatus.received,
    OrderStatus.preparing,
    OrderStatus.ready,
    OrderStatus.delivering,
]


def _item_summary(order: Order) -> str:
    """Build a short glanceable string like '10 puffs · 5 ladoo' from an
    order's line items. Uses snapshotted product names. Truncates long
    orders to keep cards tidy."""
    parts = [f"{it.quantity} {it.product_name}" for it in order.items]
    if len(parts) > 3:
        shown = parts[:3]
        return " · ".join(shown) + f" +{len(parts) - 3} more"
    return " · ".join(parts) if parts else "no items"


def get_summary(db: Session, today: date | None = None) -> dict:
    """Compute the dashboard summary for `today` (defaults to date.today())."""
    if today is None:
        today = date.today()

    # --- Today's order counts by status (one grouped query) ---
    rows = db.execute(
        select(Order.status, func.count())
        .where(Order.order_date == today)
        .group_by(Order.status)
    ).all()
    counts = {status: n for status, n in rows}

    pending = counts.get(OrderStatus.received, 0)
    in_progress = sum(counts.get(s, 0) for s in _IN_PROGRESS)
    cancelled_today = counts.get(OrderStatus.cancelled, 0)
    today_orders = sum(counts.values())

    # --- Today's revenue (non-cancelled), one scalar query ---
    revenue = db.scalar(
        select(func.coalesce(func.sum(Order.total_amount), 0)).where(
            Order.order_date == today,
            Order.status != OrderStatus.cancelled,
        )
    )
    revenue_today = float(revenue or 0)

    # --- The board: today's active (non-cancelled) orders grouped by status ---
    board_orders = db.scalars(
        select(Order)
        .where(
            Order.order_date == today,
            Order.status != OrderStatus.cancelled,
        )
        .order_by(Order.created_at.desc())
    ).all()

    board: dict[str, list[dict]] = {s.value: [] for s in _BOARD_STATUSES}
    for o in board_orders:
        board[o.status.value].append(
            {
                "id": o.id,
                "customer_name": o.customer.name,
                "item_summary": _item_summary(o),
                "status": o.status.value,
            }
        )

    # --- Reference counts ---
    active_customers = (
        db.scalar(
            select(func.count())
            .select_from(Customer)
            .where(Customer.is_active.is_(True))
        )
        or 0
    )
    active_products = (
        db.scalar(
            select(func.count()).select_from(Product).where(Product.is_active.is_(True))
        )
        or 0
    )
    unavailable_products = (
        db.scalar(
            select(func.count())
            .select_from(Product)
            .where(Product.is_active.is_(True), Product.is_available_today.is_(False))
        )
        or 0
    )

    return {
        "today_orders": today_orders,
        "pending": pending,
        "in_progress": in_progress,
        "cancelled_today": cancelled_today,
        "revenue_today": revenue_today,
        "board": board,
        "active_customers": active_customers,
        "active_products": active_products,
        "unavailable_products": unavailable_products,
        "summary_date": today,
    }
