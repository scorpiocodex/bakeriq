"""Registration webform API — endpoints backing the /web/register/{token} page.

Two endpoints:
  GET  /api/v1/register/{token}  — validate token, return phone for pre-fill
  POST /api/v1/register/{token}  — submit form, create PendingRegistration

Both share the same token validation flow:
  1. Look up token → 404 if not found
  2. Check consumed_at → 410 if already used
  3. Check expires_at → 410 if expired
  4. Check for existing Customer with this phone → 409 if already registered

The frontend calls GET first on page load to decide whether to render
the form, an "already used" message, or an "already registered" message.
Only if GET returns 200 does the frontend show the form and POST on
submit.

Consumption semantics: token is consumed on both success (200) AND
already-registered (409). Reasoning: if the phone is already a Customer
we don't need the token again; if it's a stolen token, denying reuse
is the safe default.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.customer import Customer
from app.services import pending_registration_service, registration_token_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/register", tags=["register"])


# ============================================================
# Schemas
# ============================================================


class TokenDetailsResponse(BaseModel):
    """GET response — everything the frontend needs to render the form."""

    phone: str = Field(
        ...,
        description="Phone number bound to the token; pre-filled read-only on the form.",
    )
    already_registered: bool = Field(
        ...,
        description=(
            "True if a Customer already exists for this phone. Frontend "
            "should render an 'already registered' state, not the form."
        ),
    )


class RegistrationSubmission(BaseModel):
    """POST request body — the form fields the customer filled out."""

    name: str = Field(..., min_length=1, max_length=100)
    address_line_1: str | None = Field(default=None, max_length=200)
    address_line_2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=10)


class RegistrationSubmissionResponse(BaseModel):
    """POST response — confirmation + the new PendingRegistration id."""

    message: str
    registration_id: str


# ============================================================
# Helpers
# ============================================================


def _check_already_registered(db: Session, phone: str) -> bool:
    """True if a Customer already exists for this phone (any status)."""
    existing = db.scalar(
        select(Customer).where(Customer.primary_phone == phone).limit(1)
    )
    return existing is not None


def _resolve_token_or_raise(db: Session, token: str):
    """Look up token, translate common errors to HTTP responses.

    Returns the RegistrationToken row on success. Raises the right
    HTTPException for the caller to propagate.
    """
    _, status = registration_token_service.get_token_details(db, token)

    if status == "not_found":
        raise HTTPException(
            status_code=404,
            detail="Registration link not found.",
        )
    if status == "consumed":
        raise HTTPException(
            status_code=410,
            detail="This registration link has already been used.",
        )
    if status == "expired":
        raise HTTPException(
            status_code=410,
            detail=(
                "This registration link has expired. "
                "Please message BakeriQ to get a fresh one."
            ),
        )
    # status == "ok"; look up the row (get_valid_token includes the
    # not-consumed and not-expired checks, so it'll succeed)
    row = registration_token_service.get_valid_token(db, token)
    if row is None:
        # Shouldn't happen after the status check but defensive
        raise HTTPException(status_code=404, detail="Registration link not found.")
    return row


# ============================================================
# GET — token validation + pre-fill
# ============================================================


@router.get("/{token}", response_model=TokenDetailsResponse)
def get_registration_token(
    token: str,
    db: Session = Depends(get_db),
) -> TokenDetailsResponse:
    """Look up the token, return phone for the form to pre-fill.

    Also flags if the phone is already a Customer — frontend uses this
    to switch from form to "already registered" view.
    """
    row = _resolve_token_or_raise(db, token)
    already_registered = _check_already_registered(db, row.phone)
    return TokenDetailsResponse(
        phone=row.phone,
        already_registered=already_registered,
    )


# ============================================================
# POST — form submission
# ============================================================


@router.post("/{token}", response_model=RegistrationSubmissionResponse)
def submit_registration(
    token: str,
    payload: RegistrationSubmission,
    db: Session = Depends(get_db),
) -> RegistrationSubmissionResponse:
    """Accept the form submission, create PendingRegistration, consume token.

    On success:
      - Token is marked consumed
      - PendingRegistration row is created with status='awaiting_approval'
      - Owner will be notified (Change 2 — TODO)

    On "already registered" (a Customer exists for this phone):
      - Token is STILL consumed (safe default)
      - Returns 409 telling the frontend to render success anyway

    Data flow:
      Token phone (source of truth) → PendingRegistration.phone
      Form fields                   → PendingRegistration.name + address
      Token                         → consumed_at set to now
    """
    row = _resolve_token_or_raise(db, token)

    # Already-registered check — same as GET but consumes the token to
    # prevent replay. We commit before raising so the token stays consumed.
    if _check_already_registered(db, row.phone):
        registration_token_service.consume_token(db, row)
        db.commit()
        raise HTTPException(
            status_code=409,
            detail="You're already registered with BakeriQ!",
        )

    # Also guard against double-submission at the phone level: if there's
    # already an awaiting-approval registration for this phone (e.g. the
    # customer submitted, got distracted, came back and filled the form
    # again with a fresh token), don't create a duplicate.
    existing_pending = pending_registration_service.get_awaiting_by_phone(db, row.phone)
    if existing_pending is not None:
        registration_token_service.consume_token(db, row)
        db.commit()
        return RegistrationSubmissionResponse(
            message=(
                "Your previous registration is still under review. "
                "You'll get a WhatsApp message once the owner approves you."
            ),
            registration_id=str(existing_pending.id),
        )

    # Create the pending registration
    reg = pending_registration_service.create_from_webform(
        db,
        phone=row.phone,
        name=payload.name,
        address_line_1=payload.address_line_1,
        address_line_2=payload.address_line_2,
        city=payload.city,
        state=payload.state,
        pincode=payload.pincode,
    )

    # Consume the token
    registration_token_service.consume_token(db, row)

    # Commit both operations atomically
    db.commit()

    logger.info(
        f"submit_registration: created PendingRegistration id={reg.id} "
        f"phone={row.phone}"
    )

    return RegistrationSubmissionResponse(
        message=(
            "Registration submitted! You'll get a WhatsApp message once "
            "the bakery owner approves you."
        ),
        registration_id=str(reg.id),
    )
