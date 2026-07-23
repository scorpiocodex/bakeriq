"""Inventory API — owner-only.

    GET   /inventory/stock                    stockable products + counts
    GET   /inventory/prep                     today's baking, if in window
    PATCH /inventory/stock/{product_id}       set an absolute count
    PATCH /inventory/settings/{product_id}    tracking on/off + threshold

Customers never see any of this. What reaches them is a single
`is_low_stock` flag on the menu payload — enough to warn, not enough to
expose the bakery's stock position.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.product import Product
from app.models.user import User
from app.schemas.inventory import (
    PrepListResponse,
    StockItem,
    StockListResponse,
    StockSettingsUpdate,
    StockUpdate,
)
from app.services import inventory_service
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/inventory", tags=["inventory"])


def _to_stock_item(product: Product) -> StockItem:
    return StockItem(
        id=product.id,
        name=product.name,
        unit_label=product.unit_label,
        stock_quantity=product.stock_quantity,
        low_stock_threshold=product.low_stock_threshold,
        is_low_stock=inventory_service.is_low_stock(product),
    )


@router.get("/stock", response_model=StockListResponse)
def list_stock(
    low_only: bool = Query(False, description="Only products at or below threshold"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StockListResponse:
    """Stockable products, lowest stock first.

    Sorted by how close each is to running out rather than alphabetically —
    the owner opens this to find what needs restocking.
    """
    products = inventory_service.list_stock(db, low_only=low_only)
    return StockListResponse(
        items=[_to_stock_item(p) for p in products],
        total=len(products),
        low_stock_count=inventory_service.count_low_stock(db),
    )


@router.get("/prep", response_model=PrepListResponse)
def get_prep_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PrepListResponse:
    """How much of each made-to-order item to bake today.

    Always computes the list; `is_visible` says whether it's worth showing.
    Returning the data either way means the frontend can decide, and a
    developer checking at 2 AM still sees something.
    """
    items = inventory_service.get_prep_list(db)
    return PrepListResponse(
        items=items,
        total=len(items),
        is_visible=inventory_service.prep_list_is_visible(),
    )


@router.patch("/stock/{product_id}", response_model=StockItem)
def set_stock(
    product_id: UUID,
    payload: StockUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StockItem:
    """Set a product's stock to an absolute figure — a shelf count."""
    try:
        product = inventory_service.set_stock(
            db, product_id=product_id, quantity=payload.quantity
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        # 404 for a missing product, 422 for a real product that isn't
        # stocked — the second is a usable correction, the first isn't.
        code = 404 if "not found" in str(e).lower() else 422
        raise HTTPException(status_code=code, detail=str(e))

    logger.info(
        f"set_stock: {current_user.email} set {product.name} to {payload.quantity}"
    )
    return _to_stock_item(product)


@router.patch("/settings/{product_id}", response_model=StockItem)
def update_stock_settings(
    product_id: UUID,
    payload: StockSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StockItem:
    """Turn stock tracking on or off, and set the low-stock threshold.

    Turning tracking off clears the count rather than keeping it: a number
    nothing maintains goes stale, and a stale number is worse than none.
    Turning it on starts at zero, which the owner then corrects with a real
    shelf count.
    """
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")

    if payload.is_stockable is not None:
        if payload.is_stockable and not product.is_stockable:
            product.is_stockable = True
            if product.stock_quantity is None:
                product.stock_quantity = 0
        elif not payload.is_stockable and product.is_stockable:
            product.is_stockable = False
            product.stock_quantity = None
            product.low_stock_threshold = None

    if payload.low_stock_threshold is not None and product.is_stockable:
        product.low_stock_threshold = payload.low_stock_threshold

    db.commit()
    db.refresh(product)
    return _to_stock_item(product)
