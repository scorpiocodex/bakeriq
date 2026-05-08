"""Pydantic schemas for Category — request/response shapes for the API.

Categories are simple: name + optional display_order + is_active. The
only validation that matters is name normalisation (lowercase + trim)
so two categories like "Sweet" and "sweet" can't both exist.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CategoryBase(BaseModel):
    """Fields shared between create / update / read."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    display_order: int = Field(default=0, ge=0, le=9999)

    @field_validator("name", mode="before")
    @classmethod
    def normalise_name(cls, v: str | None) -> str | None:
        """Lowercase + trim. 'Sweet ' becomes 'sweet'.

        mode='before' so the normalised value is what the length
        validation checks against. Without this, "  " (whitespace
        only) would pass min_length=1 since string itself has length 2.
        """
        if v is None:
            return v
        if isinstance(v, str):
            return v.strip().lower()
        return v


class CategoryCreate(CategoryBase):
    """Used on POST /categories. Same shape as Base."""

    pass


class CategoryUpdate(BaseModel):
    """All fields optional — partial updates via PATCH semantics on PUT.

    Service layer uses model_dump(exclude_unset=True) so unspecified
    fields stay unchanged.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    display_order: int | None = Field(default=None, ge=0, le=9999)
    is_active: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalise_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if isinstance(v, str):
            return v.strip().lower()
        return v


class CategoryOut(CategoryBase):
    """What the API returns to the client."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryListResponse(BaseModel):
    """Paginated list response — keeps total separate from items."""

    items: list[CategoryOut]
    total: int
    skip: int
    limit: int
