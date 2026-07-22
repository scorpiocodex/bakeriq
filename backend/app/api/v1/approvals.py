"""Approvals API — owner-side endpoints for pending registrations.

Four endpoints:
  GET  /api/v1/approvals            — list awaiting registrations
  GET  /api/v1/approvals/count      — count only (for sidebar badge polling)
  POST /api/v1/approvals/{id}/approve — approve, create Customer
  POST /api/v1/approvals/{id}/reject  — reject, keep row for audit

All require JWT auth via get_current_user. Only "awaiting_approval"
rows can be approved or rejected; other statuses return 409.

No pagination — the awaiting queue is naturally tiny (0-5 rows in
normal operation). If it grows past 100, we'll paginate.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.models.pending_registration import PendingRegistration
from app.schemas.approval import (
    ApprovalsCountResponse,
    ApprovalsListResponse,
    ApproveResponse,
    PendingRegistrationOut,
    RejectRequest,
    RejectResponse,
)
from app.services import pending_registration_service as pr_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approvals", tags=["approvals"])


def _get_or_404(db: Session, registration_id: UUID) -> PendingRegistration:
    """Fetch a PendingRegistration by id, or raise 404."""
    row = db.get(PendingRegistration, registration_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Registration not found.")
    return row


@router.get("", response_model=ApprovalsListResponse)
def list_approvals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalsListResponse:
    """List awaiting registrations, oldest first.

    FIFO order — the customer waiting 6 hours shouldn't be behind one
    that arrived 10 minutes ago.
    """
    rows, total = pr_svc.list_awaiting(db)
    return ApprovalsListResponse(
        items=[PendingRegistrationOut.model_validate(r) for r in rows],
        total=total,
    )


@router.get("/count", response_model=ApprovalsCountResponse)
def get_approvals_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalsCountResponse:
    """Count of awaiting registrations — polled by the sidebar badge.

    Standalone endpoint so the dashboard's 30-second poll doesn't drag
    back full row data on every tick.
    """
    count = pr_svc.count_awaiting(db)
    return ApprovalsCountResponse(count=count)


@router.post("/{registration_id}/approve", response_model=ApproveResponse)
def approve_registration(
    registration_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApproveResponse:
    """Approve a pending registration — creates a Customer row.

    Delegates to pending_registration_service.approve() which does the
    heavy lifting (validate status, copy fields, mark approved, link
    customer_id, commit).
    """
    reg = _get_or_404(db, registration_id)

    if reg.status != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail=(
                f"This registration is already {reg.status}, cannot approve again."
            ),
        )

    try:
        customer = pr_svc.approve(db, reg)
        db.commit()
    except ValueError as e:
        # Defensive — service raises ValueError for incomplete rows.
        # Shouldn't happen because webform requires name; log if it does.
        db.rollback()
        logger.exception(
            f"approve_registration: unexpected ValueError for {registration_id}"
        )
        raise HTTPException(status_code=422, detail=str(e))

    logger.info(
        f"approve_registration: {current_user.email} approved "
        f"pending_registration={registration_id} → customer={customer.id}"
    )

    return ApproveResponse(
        message=f"Approved {customer.name}.",
        customer_id=customer.id,
    )


@router.post("/{registration_id}/reject", response_model=RejectResponse)
def reject_registration(
    registration_id: UUID,
    payload: RejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RejectResponse:
    """Reject a pending registration.

    Row is kept in the DB for audit. If the customer messages the bot
    again, the webhook sees the rejected row and politely declines
    (see webhooks._dispatch).

    Reason is optional; if given, stored for admin reference. Not
    currently sent to the customer — could be exposed via a follow-up
    'appeal' flow later.
    """
    reg = _get_or_404(db, registration_id)

    if reg.status != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail=(f"This registration is already {reg.status}, cannot reject again."),
        )

    try:
        pr_svc.reject(db, reg)
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    logger.info(
        f"reject_registration: {current_user.email} rejected "
        f"pending_registration={registration_id} "
        f"reason={payload.reason!r}"
    )

    return RejectResponse(
        message=f"Rejected {reg.name}.",
        registration_id=reg.id,
    )
