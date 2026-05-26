"""Pydantic schemas for Orders.

The defining pattern is SNAPSHOTTING on read-back. When the client creates
an order, it sends only product_id + quantity per line (what it knows). The
service snapshots name/price/unit and computes subtotals + total. The
response then carries those snapshotted values so the frontend renders the
order exactly as it was sold.

Request (OrderCreate / OrderUpdate):
  {
    "customer_id": "uuid",
    "order_date": "2026-05-26",   # optional, defaults to today
    "status": "received",          # optional on create, defaults received
    "notes": "no onions",
    "items": [
      {"product_id": "uuid", "quantity": 5},
      {"product_id": "uuid", "quantity": 2}
    ]
  }

Response (OrderOut):
  Full order with snapshotted line items (product_name, unit_price,
  unit_label, subtotal) + computed total_amount + embedded customer summary.
"""

from datetime import date, datetime
from uuid import UUID

from app.models.order import OrderStatus
from pydantic import BaseModel, ConfigDict, Field

# === Item schemas ===========================================================


class OrderItemWrite(BaseModel):
    """One line as sent by the client — just product + quantity. The service
    snapshots the rest from the current product."""

    model_config = ConfigDict(str_strip_whitespace=True)

    product_id: UUID
    quantity: int = Field(gt=0, le=100000)


class OrderItemOut(BaseModel):
    """One line as returned — carries the snapshotted values."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    product_name: str
    unit_price: float
    unit_label: str
    quantity: int
    subtotal: float
    created_at: datetime
    updated_at: datetime


# === Embedded customer summary ==============================================


class OrderCustomerSummary(BaseModel):
    """A trimmed customer view embedded in order responses — enough to
    display who the order is for without pulling the full customer object."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    primary_phone: str


# === Parent schemas =========================================================


class OrderCreate(BaseModel):
    """New order as sent by the client."""

    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: UUID
    order_date: date | None = None  # defaults to today in the service
    status: OrderStatus = OrderStatus.received
    notes: str | None = Field(default=None, max_length=2000)
    items: list[OrderItemWrite] = Field(min_length=1)


class OrderUpdate(BaseModel):
    """Edit an existing order. All fields optional — only what's sent is
    changed. items, if provided, replaces all lines (replace-all, same as
    default orders). Status changes go through the dedicated status endpoint,
    not here, so status is intentionally absent.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    order_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    items: list[OrderItemWrite] | None = None


class OrderStatusUpdate(BaseModel):
    """Body for the status-transition endpoint."""

    status: OrderStatus


class OrderOut(BaseModel):
    """Full order as returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    customer: OrderCustomerSummary
    status: OrderStatus
    order_date: date
    notes: str | None
    total_amount: float
    items: list[OrderItemOut]
    created_at: datetime
    updated_at: datetime


# === List response ==========================================================


class OrderListItem(BaseModel):
    """Compact row for the orders list view — no line items, just headline
    info. The list endpoint returns these; the detail endpoint returns the
    full OrderOut with items.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer: OrderCustomerSummary
    status: OrderStatus
    order_date: date
    total_amount: float
    item_count: int
    created_at: datetime
