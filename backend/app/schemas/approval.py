"""Pydantic schemas for the /approvals endpoints.

Response shapes for owner-side interactions with pending registrations:
listing awaiting rows, approving (creates Customer), rejecting (optional
reason).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PendingRegistrationOut(BaseModel):
    """One row on the approvals page.

    Everything the owner needs to make a decision: identity + address
    + when the registration came in (so old ones can be prioritized).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    phone: str
    name: str
    address_line_1: str | None
    address_line_2: str | None
    city: str | None
    state: str | None
    pincode: str | None
    status: str
    created_at: datetime


class ApprovalsListResponse(BaseModel):
    """GET /api/v1/approvals response.

    Wrapped in an object (not a raw array) so we can add pagination or
    other metadata later without a breaking change.
    """

    items: list[PendingRegistrationOut]
    total: int


class ApprovalsCountResponse(BaseModel):
    """GET /api/v1/approvals/count response — sidebar badge polling.

    Standalone endpoint so the dashboard can poll this every 30s without
    dragging back the full list on every tick. Cheap COUNT(*) query on
    the server side."""

    count: int


class ApproveResponse(BaseModel):
    """POST /api/v1/approvals/{id}/approve response.

    Returns the newly-created Customer's id so the frontend can navigate
    to that customer's detail page if desired.
    """

    message: str
    customer_id: UUID


class RejectRequest(BaseModel):
    """POST /api/v1/approvals/{id}/reject body.

    Reason is optional — some rejections are obvious garbage where a
    reason isn't useful. Frontend prompts for a reason but doesn't
    require one.
    """

    reason: str | None = Field(default=None, max_length=500)


class RejectResponse(BaseModel):
    """POST /api/v1/approvals/{id}/reject response."""

    message: str
    registration_id: UUID
