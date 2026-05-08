"""Category endpoints — CRUD for product taxonomy.

Endpoints:
  GET    /categories         — paginated list with status filter
  GET    /categories/{id}    — fetch one
  POST   /categories         — create
  PUT    /categories/{id}    — partial update (rename, reactivate, reorder)
  DELETE /categories/{id}    — soft-delete (sets is_active=False)
  DELETE /categories/{id}/hard — hard-delete (only if no products reference it)

All endpoints require auth via Depends(get_current_user).
"""

from uuid import UUID

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.category import (
    CategoryCreate,
    CategoryListResponse,
    CategoryOut,
    CategoryUpdate,
)
from app.services import category_service
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=CategoryListResponse)
def list_categories(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    status_filter: str = Query(
        "active",
        alias="status",
        pattern="^(active|inactive|all)$",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paginated list of categories.

    status query parameter:
      - 'active' (default): only active categories
      - 'inactive': only deactivated
      - 'all': both
    """
    items, total = category_service.list_categories(
        db, skip=skip, limit=limit, status_filter=status_filter
    )
    return CategoryListResponse(
        items=[CategoryOut.model_validate(c) for c in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{category_id}", response_model=CategoryOut)
def get_category(
    category_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    category = category_service.get_category(db, category_id)
    return CategoryOut.model_validate(category)


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a category. Returns 409 if name already exists."""
    category = category_service.create_category(db, payload)
    return CategoryOut.model_validate(category)


@router.put("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Partial update — rename, change display order, reactivate.

    Use this endpoint to reactivate a soft-deleted category by sending
    {"is_active": true}.
    """
    category = category_service.update_category(db, category_id, payload)
    return CategoryOut.model_validate(category)


@router.delete("/{category_id}", response_model=CategoryOut)
def deactivate_category(
    category_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete by setting is_active=False.

    Categories can always be deactivated, even if products reference
    them. The categories dropdown in the UI filters out inactive
    entries, but products keep their FK reference (their category
    name still displays correctly on existing rows).

    Use DELETE /categories/{id}/hard for true deletion.
    """
    category = category_service.deactivate_category(db, category_id)
    return CategoryOut.model_validate(category)


@router.delete("/{category_id}/hard", status_code=status.HTTP_204_NO_CONTENT)
def hard_delete_category(
    category_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Hard-delete the category row entirely.

    Only succeeds if no products reference the category. Otherwise
    returns 409 with a message asking to reassign or deactivate first.

    This is for cleanup of typo'd or never-used categories. Most of
    the time, soft-delete via the regular DELETE endpoint is what you
    want.
    """
    category_service.delete_category(db, category_id)
    return None
