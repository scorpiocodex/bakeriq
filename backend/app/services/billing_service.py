"""Billing service — aggregate queries over orders.

No billing tables. Everything here reads `orders` and `order_items`,
which already snapshot product name, price, and unit at creation time.

Two filters apply to every query and both matter:

  is_draft = False      A draft order is a cart the customer hasn't
                        placed yet. It has a total but it isn't revenue.

  status != cancelled   Cancelled orders don't count toward revenue.
                        They're still *shown* on an invoice, greyed out,
                        so the owner can see what was voided — but they
                        contribute nothing to the total.

Dates use `order_date` (the business date the order is for), not
`created_at`. An order placed at 11pm for tomorrow belongs on tomorrow's
invoice. This matches dashboard_service.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.customer import Customer
from app.models.order import Order, OrderStatus


def _billable(stmt: Select) -> Select:
    """Restrict a statement to orders that count as revenue."""
    return stmt.where(
        Order.is_draft.is_(False),
        Order.status != OrderStatus.cancelled,
    )


def _in_range(start: date, end: date):
    """Date-range predicate, inclusive at both ends."""
    return and_(Order.order_date >= start, Order.order_date <= end)


def build_invoice_number(customer_id: UUID, invoice_date: date) -> str:
    """Derive an invoice reference from customer + date.

    INV-20260722-8294dceb

    Deterministic rather than stored: the same customer and date always
    produce the same reference, so there's no sequence table to keep and
    no gap problem when an order is cancelled. Unique because a customer
    gets at most one invoice per day.

    Not GST-compliant — see the note on InvoiceOut.
    """
    return f"INV-{invoice_date:%Y%m%d}-{str(customer_id)[:8]}"


# === Summary ================================================================


def get_summary(db: Session, *, start: date, end: date) -> dict:
    """Headline numbers for a date range."""
    revenue = db.scalar(
        _billable(
            select(func.coalesce(func.sum(Order.total_amount), 0)).where(
                _in_range(start, end)
            )
        )
    )

    order_count = (
        db.scalar(
            _billable(
                select(func.count()).select_from(Order).where(_in_range(start, end))
            )
        )
        or 0
    )

    customer_count = (
        db.scalar(
            _billable(
                select(func.count(func.distinct(Order.customer_id)))
                .select_from(Order)
                .where(_in_range(start, end))
            )
        )
        or 0
    )

    # Cancelled is reported separately, so it doesn't go through _billable.
    cancelled_count = (
        db.scalar(
            select(func.count())
            .select_from(Order)
            .where(
                _in_range(start, end),
                Order.is_draft.is_(False),
                Order.status == OrderStatus.cancelled,
            )
        )
        or 0
    )

    return {
        "start_date": start,
        "end_date": end,
        "revenue": float(revenue or 0),
        "order_count": order_count,
        "customer_count": customer_count,
        "cancelled_count": cancelled_count,
    }


# === Customer level =========================================================


def list_customers(db: Session, *, start: date, end: date) -> list[dict]:
    """Customers with billable orders in the range, highest total first.

    One grouped query rather than a query per customer. `invoice_count`
    counts distinct order_dates — that's how many invoices the drill-down
    will show for this customer.
    """
    rows = db.execute(
        _billable(
            select(
                Customer.id,
                Customer.name,
                Customer.primary_phone,
                func.count(Order.id).label("order_count"),
                func.count(func.distinct(Order.order_date)).label("invoice_count"),
                func.coalesce(func.sum(Order.total_amount), 0).label("total"),
                func.min(Order.order_date).label("first_order_date"),
                func.max(Order.order_date).label("last_order_date"),
            )
            .join(Customer, Customer.id == Order.customer_id)
            .where(_in_range(start, end))
        )
        .group_by(Customer.id, Customer.name, Customer.primary_phone)
        .order_by(func.coalesce(func.sum(Order.total_amount), 0).desc())
    ).all()

    return [
        {
            "customer_id": r.id,
            "customer_name": r.name,
            "primary_phone": r.primary_phone,
            "order_count": r.order_count,
            "invoice_count": r.invoice_count,
            "total": float(r.total or 0),
            "first_order_date": r.first_order_date,
            "last_order_date": r.last_order_date,
        }
        for r in rows
    ]


# === Date level =============================================================


def list_customer_dates(
    db: Session, *, customer_id: UUID, start: date, end: date
) -> list[dict]:
    """One customer's invoiceable days in the range, most recent first."""
    rows = db.execute(
        _billable(
            select(
                Order.order_date,
                func.count(Order.id).label("order_count"),
                func.coalesce(func.sum(Order.total_amount), 0).label("total"),
            ).where(
                Order.customer_id == customer_id,
                _in_range(start, end),
            )
        )
        .group_by(Order.order_date)
        .order_by(Order.order_date.desc())
    ).all()

    return [
        {
            "order_date": r.order_date,
            "order_count": r.order_count,
            "total": float(r.total or 0),
            "invoice_number": build_invoice_number(customer_id, r.order_date),
        }
        for r in rows
    ]


# === Invoice ================================================================


def _business_details() -> dict:
    """The bakery's own details, from config.

    Lives in .env because there's no settings table yet. When Settings
    grows a 'Bakery info' section, this function reads from that table
    and nothing else changes.
    """
    return {
        "name": settings.BUSINESS_NAME,
        "address_line_1": settings.BUSINESS_ADDRESS_LINE_1,
        "address_line_2": settings.BUSINESS_ADDRESS_LINE_2,
        "city": settings.BUSINESS_CITY,
        "state": settings.BUSINESS_STATE,
        "pincode": settings.BUSINESS_PINCODE,
        "phone": settings.BUSINESS_PHONE,
        "email": settings.BUSINESS_EMAIL,
    }


def get_invoice(db: Session, *, customer_id: UUID, invoice_date: date) -> dict | None:
    """One customer's invoice for one day, or None if they didn't order.

    Cancelled orders are included in `orders` but flagged and excluded
    from `total` — the owner should be able to see what was voided.
    Drafts are excluded entirely; they were never placed.
    """
    customer = db.get(Customer, customer_id)
    if customer is None:
        return None

    orders = db.scalars(
        select(Order)
        .where(
            Order.customer_id == customer_id,
            Order.order_date == invoice_date,
            Order.is_draft.is_(False),
        )
        .order_by(Order.created_at.asc())
    ).all()

    if not orders:
        return None

    order_payloads = []
    total = 0.0
    cancelled_count = 0
    billable_count = 0

    for o in orders:
        is_cancelled = o.status == OrderStatus.cancelled
        if is_cancelled:
            cancelled_count += 1
        else:
            billable_count += 1
            total += float(o.total_amount or 0)

        order_payloads.append(
            {
                "id": o.id,
                "short_id": str(o.id)[:8],
                "status": o.status,
                "is_cancelled": is_cancelled,
                "notes": o.notes,
                "total_amount": float(o.total_amount or 0),
                "items": [
                    {
                        "product_name": it.product_name,
                        "unit_price": float(it.unit_price),
                        "unit_label": it.unit_label,
                        "quantity": it.quantity,
                        "subtotal": float(it.subtotal),
                    }
                    for it in o.items
                ],
            }
        )

    return {
        "invoice_number": build_invoice_number(customer_id, invoice_date),
        "invoice_date": invoice_date,
        "business": _business_details(),
        "customer": customer,
        "orders": order_payloads,
        "order_count": billable_count,
        "cancelled_count": cancelled_count,
        "total": total,
    }


def get_latest_invoice(db: Session, *, customer_id: UUID) -> dict | None:
    """The customer's most recent invoice, or None if they've never ordered.

    "Most recent" is the latest order_date with at least one billable
    order — drafts and cancelled orders don't count, since an invoice
    consisting only of a cancelled order isn't one the customer wants to
    see.

    Backs the customer-facing /invoice/{token} endpoint. The owner's
    /billing views address invoices by explicit date instead.
    """
    latest_date = db.scalar(
        _billable(
            select(func.max(Order.order_date)).where(Order.customer_id == customer_id)
        )
    )
    if latest_date is None:
        return None

    return get_invoice(db, customer_id=customer_id, invoice_date=latest_date)
