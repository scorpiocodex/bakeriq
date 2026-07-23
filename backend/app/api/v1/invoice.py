"""Customer-facing invoice endpoint.

Distinct from /billing, which is the owner's JWT-authed view. Here the
token in the path is the credential — same pattern as /cart and
/register. See ADR-19.

    GET /api/v1/invoice/{token}   the customer's latest invoice

"Latest" means the invoice for the day of their most recent order.
Tapping Invoice right after placing an order therefore shows today's,
including that order.

Because the invoice is resolved at view time rather than baked into the
token, a token opened a day later shows the newer invoice. That's why
invoice tokens expire in 24 hours — it bounds how stale the link's
implied meaning can get.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.billing import InvoiceOut
from app.services import billing_service, token_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/invoice", tags=["invoice"])


@router.get("/{token}", response_model=InvoiceOut)
def get_customer_invoice(
    token: str,
    db: Session = Depends(get_db),
) -> InvoiceOut:
    """The latest invoice for whoever holds this token.

    404 covers every failure mode — bad token, expired token, wrong
    kind, no orders. Distinguishing them would tell an attacker whether
    a token ever existed, and tells a legitimate customer nothing they
    can act on beyond "ask the bot again".
    """
    row = token_service.validate_token(db, token)
    if row is None or row.kind != "invoice":
        raise HTTPException(
            status_code=404,
            detail="This invoice link has expired or is no longer valid. "
            "Message BakeriQ on WhatsApp for a fresh one.",
        )

    invoice = billing_service.get_latest_invoice(db, customer_id=row.customer_id)
    if invoice is None:
        raise HTTPException(
            status_code=404,
            detail="No invoice found — you haven't placed any orders yet.",
        )

    return InvoiceOut.model_validate(invoice)
