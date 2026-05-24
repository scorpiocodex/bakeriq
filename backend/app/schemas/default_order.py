"""
Pydantic schemas for Default Orders - a customer's recurring order template.

The client sends the whole template in one PUT; the service creates/replaces
parent + items in one transaction.
"""

from datetime import datetime
from uuid import UUID

from app.schemas.product import ProductOut
from pydantic import BaseModel, ConfigDict, Field

# ===== Item schemas ===== #


class DefaultOrderItemWrite(BaseModel):
    """One line template as sent by the client"""

    model_config = ConfigDict(str_strip_whitespace=True)
    product_id: UUID
    quantity: int = Field(gt=0, le=10000)


class DefaultOrderItemOut(BaseModel):
    """One line template as returned to client.
    Embeds the full product object (name, price, category, etc.)"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_id: UUID
    quantity: int
    product: ProductOut
    created_at: datetime
    updated_at: datetime


# ===== Parent Schemas ===== #


class DefaultOrderWrite(BaseModel):
    """The full template as sent by the client on PUT"""

    model_config = ConfigDict(str_strip_whitespace=True)
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool = True
    items: list[DefaultOrderItemWrite] = Field(default_factory=list)


class DefaultOrderOut(BaseModel):
    """The full template as returned to the client"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    customer_id: UUID
    notes: str | None
    is_active: bool
    items: list[DefaultOrderItemOut]
    created_at: datetime
    updated_at: datetime
