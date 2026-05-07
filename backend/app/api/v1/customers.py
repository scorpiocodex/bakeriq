"""Customer CRUD endpoints."""

from uuid import UUID

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.customer import (
    CustomerCreate,
    CustomerListResponse,
    CustomerOut,
    CustomerUpdate,
)
from app.services import customer_service
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return customer_service.create_customer(db, payload)


@router.get("", response_model=CustomerListResponse)
def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, max_length=100),
    whatsapp_only: bool | None = None,
    status: str = Query("active", pattern="^(active|inactive|all)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List customers with pagination and filters.

    status query parameter:
      - 'active' (default): only active customers
      - 'inactive': only deactivated customers
      - 'all': both

    Pattern validation in Query() ensures FastAPI returns 422 for typos
    rather than silently falling through to the service-layer default.
    """
    items, total = customer_service.list_customers(
        db,
        skip=skip,
        limit=limit,
        search=search,
        whatsapp_only=whatsapp_only,
        status=status,
    )
    return CustomerListResponse(
        items=[CustomerOut.model_validate(c) for c in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return customer_service.get_customer(db, customer_id)


@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return customer_service.update_customer(db, customer_id, payload)


@router.delete("/{customer_id}", response_model=CustomerOut)
def deactivate_customer(
    customer_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete: sets is_active=false. Order history references stay valid."""
    return customer_service.deactivate_customer(db, customer_id)
