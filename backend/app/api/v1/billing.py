"""Billing API — read-only views over orders.

Four endpoints forming a drill-down:

    GET /billing/summary                              headline numbers
    GET /billing/customers                            who ordered, and how much
    GET /billing/customers/{id}/dates                 their invoiceable days
    GET /billing/customers/{id}/invoice/{date}        the invoice itself

All JWT-authed. Nothing here writes.

Date ranges are inclusive at both ends and default to the current
calendar month, which is the range the owner wants most often.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.customer import Customer
from app.models.user import User
from app.schemas.billing import (
    BillingCustomersResponse,
    BillingCustomerSummary,
    BillingDatesResponse,
    BillingSummary,
    InvoiceOut,
)
from app.services import billing_service

router = APIRouter(prefix="/billing", tags=["billing"])


def _default_range(start: date | None, end: date | None) -> tuple[date, date]:
    """Fill in a missing range with the current calendar month.

    Also guards start <= end. Without the check, an inverted range
    silently returns zero rows, which reads as "no orders" rather than
    "you typed the dates backwards".
    """
    today = date.today()
    if start is None:
        start = today.replace(day=1)
    if end is None:
        end = today
    if start > end:
        raise HTTPException(
            status_code=422,
            detail="start date must be on or before end date.",
        )
    return start, end


@router.get("/summary", response_model=BillingSummary)
def get_billing_summary(
    start: date | None = Query(
        None, description="Inclusive. Defaults to the 1st of this month."
    ),
    end: date | None = Query(None, description="Inclusive. Defaults to today."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BillingSummary:
    """Revenue, order count, and distinct customers for a date range."""
    start, end = _default_range(start, end)
    return BillingSummary.model_validate(
        billing_service.get_summary(db, start=start, end=end)
    )


@router.get("/customers", response_model=BillingCustomersResponse)
def list_billing_customers(
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BillingCustomersResponse:
    """Customers with billable orders in the range, highest total first.

    No pagination — a single bakery's customer list is small, and the
    range filter already bounds it.
    """
    start, end = _default_range(start, end)
    rows = billing_service.list_customers(db, start=start, end=end)
    return BillingCustomersResponse(items=rows, total=len(rows))


@router.get("/customers/{customer_id}/dates", response_model=BillingDatesResponse)
def list_billing_customer_dates(
    customer_id: UUID,
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BillingDatesResponse:
    """One customer's invoiceable days, most recent first."""
    start, end = _default_range(start, end)

    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found.")

    rows = billing_service.list_customer_dates(
        db, customer_id=customer_id, start=start, end=end
    )
    return BillingDatesResponse(
        customer=BillingCustomerSummary.model_validate(customer),
        items=rows,
        total=len(rows),
    )


@router.get(
    "/customers/{customer_id}/invoice/{invoice_date}",
    response_model=InvoiceOut,
)
def get_invoice(
    customer_id: UUID,
    invoice_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InvoiceOut:
    """A customer's invoice for one day.

    404 covers both "no such customer" and "that customer didn't order
    that day" — from the caller's perspective there's no invoice either
    way, and distinguishing them tells them nothing useful.
    """
    invoice = billing_service.get_invoice(
        db, customer_id=customer_id, invoice_date=invoice_date
    )
    if invoice is None:
        raise HTTPException(
            status_code=404,
            detail="No invoice for that customer on that date.",
        )
    return InvoiceOut.model_validate(invoice)
