"""Pydantic schemas for Product — request/response shapes for the API.

Validation:
  - category_id: UUID FK to categories.id. Existence is verified by
    the service layer (raises 404 if the category doesn't exist).
  - unit_price: must be > 0. NUMERIC at the DB; Decimal in Python;
    serialised as float in JSON responses.
  - aliases: list of strings, normalised to lowercase + trimmed before
    storage (the LLM parser does case-insensitive matching).

Response shape:
  - CustomerOut embeds the full Category object as `category` so clients
    don't need a follow-up call to display category name. This works
    because the SQLAlchemy model has lazy="joined" on the relationship
    — categories arrive in the same query.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.schemas.category import CategoryOut
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductBase(BaseModel):
    """Fields shared between create / update / read."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=300)
    category_id: UUID
    unit_price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    unit_label: str = Field(default="piece", min_length=1, max_length=30)
    is_available_today: bool = True
    aliases: list[str] = Field(default_factory=list)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("aliases", mode="before")
    @classmethod
    def normalise_aliases(cls, v) -> list[str] | None:
        """Lowercase + trim each alias, drop empty/duplicates.

        Owner might enter 'Veg Puff', 'veg puff', 'VEG PUFF' as separate
        aliases — same string from the bot's perspective. Normalising
        once at write time means the LLM parser (Phase 3) can do exact
        match instead of fuzzy.
        """
        if v is None:
            return v
        if not isinstance(v, list):
            return v
        seen = set()
        cleaned = []
        for alias in v:
            if not isinstance(alias, str):
                continue
            normalised = alias.strip().lower()
            if normalised and normalised not in seen:
                seen.add(normalised)
                cleaned.append(normalised)
        return cleaned


class ProductCreate(ProductBase):
    """Used on POST /products."""

    pass


class ProductUpdate(BaseModel):
    """All fields optional — partial updates via PATCH semantics on PUT.

    Service layer uses model_dump(exclude_unset=True) so unspecified
    fields stay unchanged.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=300)
    category_id: UUID | None = None
    unit_price: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    unit_label: str | None = Field(default=None, min_length=1, max_length=30)
    is_available_today: bool | None = None
    aliases: list[str] | None = None
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None  # Allows soft-delete / reactivation via PUT

    @field_validator("aliases", mode="before")
    @classmethod
    def normalise_aliases(cls, v) -> list[str] | None:
        if v is None:
            return v
        if not isinstance(v, list):
            return v
        seen = set()
        cleaned = []
        for alias in v:
            if not isinstance(alias, str):
                continue
            normalised = alias.strip().lower()
            if normalised and normalised not in seen:
                seen.add(normalised)
                cleaned.append(normalised)
        return cleaned


class ProductOut(BaseModel):
    """What the API returns to the client.

    Note this does NOT inherit from ProductBase — the response shape is
    different from the request shape. Request takes category_id (a UUID);
    response embeds the full Category object as `category`. Same data,
    different transformation.

    The lazy='joined' relationship on the model means SQLAlchemy fetches
    the category in the same query, so accessing product.category in
    Python is free (no extra round-trip).
    """

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: UUID
    name: str
    category: CategoryOut  # embedded full object, not just the ID
    unit_price: Decimal
    unit_label: str
    is_available_today: bool
    aliases: list[str]
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductListResponse(BaseModel):
    """Paginated list response — keeps total separate from items."""

    items: list[ProductOut]
    total: int
    skip: int
    limit: int
