"""Pydantic schemas for Inventory.

Two different things share this page, and they're not the same shape:

  Stock      Sealed goods with a countable quantity on hand.
  Prep list  How much of each made-to-order item to bake today, derived
             from today's orders rather than stored.

See inventory_service for why the second isn't persisted.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StockItem(BaseModel):
    """One stockable product and its count."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    unit_label: str
    stock_quantity: int | None
    low_stock_threshold: int | None
    is_low_stock: bool


class StockListResponse(BaseModel):
    items: list[StockItem]
    total: int
    low_stock_count: int


class PrepListItem(BaseModel):
    """One made-to-order item and how much of it today's orders need."""

    product_id: UUID
    product_name: str
    unit_label: str
    quantity: int
    order_count: int


class PrepListResponse(BaseModel):
    """Today's baking, plus whether it's worth showing.

    `is_visible` is false outside the baking window — before the 5 AM
    order cutoff the numbers are still moving, and after the day's baking
    they're history. The frontend hides the section rather than showing a
    stale or half-formed list.
    """

    items: list[PrepListItem]
    total: int
    is_visible: bool


class StockUpdate(BaseModel):
    """Set a product's stock to an absolute figure.

    Absolute rather than a delta: this is what the owner enters after
    counting a shelf, and making them work out the difference is exactly
    the arithmetic that introduces errors.
    """

    quantity: int = Field(ge=0)


class StockSettingsUpdate(BaseModel):
    """Turn stock tracking on or off for a product, and set its threshold.

    Separate from StockUpdate because these are different actions with
    different frequencies — the count changes daily, these barely change
    after setup.
    """

    is_stockable: bool | None = None
    low_stock_threshold: int | None = Field(default=None, ge=0)
