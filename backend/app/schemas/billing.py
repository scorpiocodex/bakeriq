"""Pydantic schemas for Billing.

Billing is a read-only view over orders — there are no billing tables.
Every number is aggregated from `orders` and `order_items`, which already
snapshot product name, price, and unit at creation time. That snapshot is
what makes historical invoices correct: a price change next month doesn't
rewrite last month's invoice.

The drill-down, and the schema at each level:

    /billing                 BillingSummary + BillingCustomersResponse
      -> customer            BillingDatesResponse
          -> date            InvoiceOut

Invoices are per customer per day, not per order. A hotel ordering in the
morning and again in the evening gets one invoice covering both.
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.order import OrderStatus

# === Summary ================================================================


class BillingSummary(BaseModel):
    """Headline numbers for a date range.

    `revenue` and `order_count` exclude cancelled orders and drafts.
    `cancelled_count` is reported separately so the owner can see it
    without it polluting the total.
    """

    start_date: date
    end_date: date
    revenue: float
    order_count: int
    customer_count: int
    cancelled_count: int


# === Customer level =========================================================


class BillingCustomerRow(BaseModel):
    """One customer's activity within the range.

    `invoice_count` is the number of distinct days they ordered on —
    i.e. how many invoices the drill-down will show.
    """

    customer_id: UUID
    customer_name: str
    primary_phone: str
    order_count: int
    invoice_count: int
    total: float
    first_order_date: date
    last_order_date: date


class BillingCustomersResponse(BaseModel):
    items: list[BillingCustomerRow]
    total: int


# === Date level =============================================================


class BillingCustomerSummary(BaseModel):
    """Trimmed customer, enough for a page header."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    primary_phone: str


class BillingDateRow(BaseModel):
    """One invoiceable day for a customer."""

    order_date: date
    order_count: int
    total: float
    invoice_number: str


class BillingDatesResponse(BaseModel):
    customer: BillingCustomerSummary
    items: list[BillingDateRow]
    total: int


# === Invoice ================================================================


class BusinessDetails(BaseModel):
    """The bakery's own details, for the invoice header.

    Read from .env via config. When Settings grows a 'Bakery info'
    section these come from a table instead and this schema doesn't
    change.
    """

    name: str
    address_line_1: str | None
    address_line_2: str | None
    city: str | None
    state: str | None
    pincode: str | None
    phone: str | None
    email: str | None


class InvoiceCustomer(BaseModel):
    """Bill-to block. Full address, unlike the trimmed summary."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    primary_phone: str
    address_line_1: str | None
    address_line_2: str | None
    city: str | None
    state: str | None
    pincode: str | None


class InvoiceLine(BaseModel):
    """One line item, read from the order's snapshot columns."""

    model_config = ConfigDict(from_attributes=True)

    product_name: str
    unit_price: float
    unit_label: str
    quantity: int
    subtotal: float


class InvoiceOrder(BaseModel):
    """One order on the invoice.

    Cancelled orders appear but are flagged, so the owner can see what
    was ordered and voided. They don't contribute to the total.
    """

    id: UUID
    short_id: str
    status: OrderStatus
    is_cancelled: bool
    notes: str | None
    total_amount: float
    items: list[InvoiceLine]


class InvoiceOut(BaseModel):
    """A customer's invoice for one day.

    `invoice_number` is derived, not stored: INV-{YYYYMMDD}-{first 8 of
    the customer id}. Deterministic, so the same customer and date always
    produce the same reference, and unique without a sequence table.

    This is not a GST-compliant invoice number — those must be an
    unbroken per-financial-year sequence. If the bakery registers for
    GST that needs designing properly rather than bolting a counter onto
    this.
    """

    invoice_number: str
    invoice_date: date
    business: BusinessDetails
    customer: InvoiceCustomer
    orders: list[InvoiceOrder]
    order_count: int
    cancelled_count: int
    total: float
