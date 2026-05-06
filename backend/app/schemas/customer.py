"""Pydantic schemas for Customer — request/response shapes for the API."""

from datetime import datetime
from uuid import UUID

from app.models.customer import PreferredPhone
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Phone validation regex. Accepts E.164 format with optional spaces.
# +91 98470 12345 or +919847012345 both pass; 1234567890 doesn't.
PHONE_REGEX = r"^\+\d{10,15}$"


class CustomerBase(BaseModel):
    """Fields shared between create / update / read."""

    name: str = Field(min_length=1, max_length=255)
    primary_phone: str = Field(pattern=PHONE_REGEX)
    secondary_phone: str | None = Field(default=None, pattern=PHONE_REGEX)
    preferred_channel_phone: PreferredPhone = PreferredPhone.PRIMARY
    whatsapp_enabled: bool = False
    address: str | None = None
    notes: str | None = None

    @field_validator("primary_phone", "secondary_phone", mode="before")
    @classmethod
    def normalise_phone(cls, v: str | None) -> str | None:
        """Strip whitespace and hyphens BEFORE the regex pattern runs.

        mode='before' is critical: without it, the Field(pattern=...) check
        runs first and rejects whitespace before this validator can clean it.
        """
        if v is None:
            return v
        if isinstance(v, str):
            return v.replace(" ", "").replace("-", "")
        return v  # let other types fall through to the regex/type validation


class CustomerCreate(CustomerBase):
    """Used on POST /customers."""

    pass


class CustomerUpdate(BaseModel):
    """All fields optional — partial updates via PATCH semantics on PUT.

    Pydantic v2 idiom: every field defaulting to None means the API can
    accept just the fields the client wants to change.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    primary_phone: str | None = Field(default=None, pattern=PHONE_REGEX)
    secondary_phone: str | None = Field(default=None, pattern=PHONE_REGEX)
    preferred_channel_phone: PreferredPhone | None = None
    whatsapp_enabled: bool | None = None
    address: str | None = None
    notes: str | None = None
    is_active: bool | None = None  # Allows soft-delete / reactivation via PUT

    @field_validator("primary_phone", "secondary_phone", mode="before")
    @classmethod
    def normalise_phone(cls, v: str | None) -> str | None:
        """Strip whitespace and hyphens BEFORE the regex pattern runs.

        mode='before' is critical: without it, the Field(pattern=...) check
        runs first and rejects whitespace before this validator can clean it.
        """
        if v is None:
            return v
        if isinstance(v, str):
            return v.replace(" ", "").replace("-", "")
        return v  # let other types fall through to the regex/type validation


class CustomerOut(CustomerBase):
    """What the API returns to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CustomerListResponse(BaseModel):
    """Paginated list response — keeps total separate from items."""

    items: list[CustomerOut]
    total: int
    skip: int
    limit: int
