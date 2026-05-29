"""Dashboard endpoint — GET /dashboard/summary.

A single read-only snapshot for the owner's morning glance. All numbers are
computed from existing data via dashboard_service.
"""

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.services import dashboard_service
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/summary",
    response_model=DashboardSummary,
)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Today's order-flow snapshot plus reference counts.

    Returns headline numbers (pending/in-progress/cancelled/revenue), the
    order board grouped by status, and active customer/product counts.
    'Today' is determined by order_date.
    """
    summary = dashboard_service.get_summary(db)
    return DashboardSummary.model_validate(summary)
