"""Product endpoints — CRUD for the bakery's product catalog.

Endpoints:
  GET    /products         — paginated list with filters (status, category, available_today, search)
  GET    /products/{id}    — fetch one
  POST   /products         — create
  PUT    /products/{id}    — partial update
  DELETE /products/{id}    — soft-delete (sets is_active=False)

All endpoints require auth via Depends(get_current_user).
Reactivation handled via PUT with is_active=True (same pattern as customers).
"""

from uuid import UUID

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.product import (
    ProductCreate,
    ProductListResponse,
    ProductOut,
    ProductUpdate,
)
from app.services import product_service
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ProductListResponse)
def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, max_length=100),
    category_id: UUID | None = None,
    available_today: bool | None = None,
    status_filter: str = Query(
        "active",
        alias="status",
        pattern="^(active|inactive|all)$",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List products with pagination and filters.

    Query parameters:
      skip / limit:    pagination
      search:          ILIKE on product name and description (lowercase)
      category_id:     restrict to a specific category
      available_today: filter by today's availability flag
      status:          'active' (default) | 'inactive' | 'all'

    Results are ordered by category name, then product name — so
    products on the products page naturally group by category.
    """
    items, total = product_service.list_products(
        db,
        skip=skip,
        limit=limit,
        search=search,
        category_id=category_id,
        available_today=available_today,
        status_filter=status_filter,
    )
    return ProductListResponse(
        items=[ProductOut.model_validate(p) for p in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = product_service.get_product(db, product_id)
    return ProductOut.model_validate(product)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a product. Returns 422 if category_id is invalid or inactive."""
    product = product_service.create_product(db, payload)
    return ProductOut.model_validate(product)


@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Partial update.

    Includes is_active for soft-delete reversal: send {"is_active": true}
    to reactivate a deactivated product. Same pattern as customers.
    """
    product = product_service.update_product(db, product_id, payload)
    return ProductOut.model_validate(product)


@router.delete("/{product_id}", response_model=ProductOut)
def deactivate_product(
    product_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete by setting is_active=False.

    Order history references remain valid because the row stays in the
    database. Reactivation is via PUT with {"is_active": true}.
    """
    product = product_service.deactivate_product(db, product_id)
    return ProductOut.model_validate(product)
