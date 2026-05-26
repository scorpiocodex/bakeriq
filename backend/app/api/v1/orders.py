"""Order endpoints.

  POST   /orders                       — create
  GET    /orders                       — list (compact rows, filterable)
  GET    /orders/{order_id}            — full detail with items
  PUT    /orders/{order_id}            — edit date/notes/items (not status)
  PATCH  /orders/{order_id}/status     — change status (validated transition)
  DELETE /orders/{order_id}            — hard-delete
  GET    /customers/{id}/order-prefill — suggested items from default order

This step adds the router + the status endpoint. Step 6 adds the rest.
"""

from datetime import date
from uuid import UUID

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.default_order import DefaultOrder
from app.models.order import OrderStatus
from app.models.user import User
from app.schemas.order import (
    OrderCreate,
    OrderListItem,
    OrderOut,
    OrderStatusUpdate,
    OrderUpdate,
)
from app.services import order_service
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/orders", tags=["orders"])


@router.patch("/{order_id}/status", response_model=OrderOut)
def change_order_status(
    order_id: UUID,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Move an order to a new status.

    Allowed: forward/back within received→preparing→ready→delivering, and
    cancel from any state. Forbidden: reactivating a cancelled order (422).

    Returns the updated order with full detail.
    """
    order = order_service.change_status(db, order_id, payload.status)
    return OrderOut.model_validate(order)


@router.post(
    "",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new order. Items are snapshotted (name/price/unit captured
    now); total computed from subtotals. 404 if customer missing, 422 if any
    product is invalid/inactive or items is empty."""
    order = order_service.create_order(db, payload)
    return OrderOut.model_validate(order)


@router.get(
    "",
    response_model=dict,
)
def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status_filter: OrderStatus | None = Query(None, alias="status"),
    customer_id: UUID | None = Query(None),
    order_date: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List orders newest-first, with optional filters: status, customer_id,
    order_date. Returns compact rows (no line items) plus pagination info.

    Each row carries item_count rather than the items themselves — the detail
    endpoint returns full items when an order is selected.
    """
    orders, total = order_service.list_orders(
        db,
        skip=skip,
        limit=limit,
        status_filter=status_filter,
        customer_id=customer_id,
        order_date=order_date,
    )
    items = [
        OrderListItem(
            id=o.id,
            customer=o.customer,
            status=o.status,
            order_date=o.order_date,
            total_amount=o.total_amount,
            item_count=len(o.items),
            created_at=o.created_at,
        )
        for o in orders
    ]
    return {
        "items": [item.model_dump(mode="json") for item in items],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get(
    "/{order_id}",
    response_model=OrderOut,
)
def get_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full order detail with all line items. 404 if not found."""
    order = order_service.get_order(db, order_id)
    return OrderOut.model_validate(order)


@router.put(
    "/{order_id}",
    response_model=OrderOut,
)
def update_order(
    order_id: UUID,
    payload: OrderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit order date/notes and optionally replace items (re-snapshotted,
    total recomputed). Status is NOT changed here — use the status endpoint.
    404 if not found, 422 if a provided item is invalid/inactive."""
    order = order_service.update_order(db, order_id, payload)
    return OrderOut.model_validate(order)


@router.delete(
    "/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Hard-delete an order (items cascade). Prefer cancelling for real
    orders; delete is for genuine mistakes. 404 if not found."""
    order_service.delete_order(db, order_id)
    return None


# Customer-scoped prefill route — lives under /customers, like default-order
prefill_router = APIRouter(prefix="/customers", tags=["orders"])


@prefill_router.get(
    "/{customer_id}/order-prefill",
    response_model=dict,
)
def order_prefill(
    customer_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Suggested order lines from the customer's default order template.

    Returns { items: [...], skipped_count: N }. Inactive template products
    are skipped; skipped_count tells the UI how many were dropped so it can
    show a note. Empty items list if the customer has no template.
    Prices are CURRENT product prices (fresh snapshot at order time).
    """
    suggestions = order_service.build_prefill_items_from_default(db, customer_id)

    # Compare against the raw template size to compute how many were skipped

    template = db.scalars(
        select(DefaultOrder).where(DefaultOrder.customer_id == customer_id)
    ).first()
    template_count = len(template.items) if template else 0
    skipped = template_count - len(suggestions)

    return {
        "items": [
            {
                "product_id": str(s["product_id"]),
                "product_name": s["product_name"],
                "unit_price": s["unit_price"],
                "unit_label": s["unit_label"],
                "quantity": s["quantity"],
            }
            for s in suggestions
        ],
        "skipped_count": skipped,
    }
