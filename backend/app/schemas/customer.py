"""Pydantic schemas for Customer — request/response shapes for the API.

Phone validation: backend accepts whitespace and hyphens in phone input
(via mode='before' validator that strips them) so users can type formatted
numbers like "+91 99999 12345". The regex pattern then enforces final shape.

Address validation: 5 fields matching Indian postal format. address_line_1,
city, state, pincode are required; address_line_2 is optional.
PIN code: validated as exactly 6 digits via regex.
"""

from datetime import datetime
from uuid import UUID

from app.models.customer import PreferredPhone
from pydantic import BaseModel, ConfigDict, Field, field_validator

# === Validation regexes ===
# Phone: + followed by 10-15 digits. Permissive enough for India (12 digits
# incl. country code) plus future international support without changes.
PHONE_REGEX = r"^\+\d{10,15}$"

# Pincode: exactly 6 digits. Indian PIN codes are always this format.
# When the bakery expands beyond India this becomes a problem; for now,
# strict validation catches typos at the API layer rather than the DB.
PINCODE_REGEX = r"^\d{6}$"


class CustomerBase(BaseModel):
    """Fields shared between create / update / read."""

    model_config = ConfigDict(use_enum_values=True)

    name: str = Field(min_length=1, max_length=255)
    primary_phone: str = Field(pattern=PHONE_REGEX)
    secondary_phone: str | None = Field(default=None, pattern=PHONE_REGEX)
    preferred_channel_phone: PreferredPhone = PreferredPhone.PRIMARY
    whatsapp_enabled: bool = False

    # === Address fields — Indian postal format ===
    address_line_1: str = Field(min_length=1, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    pincode: str = Field(pattern=PINCODE_REGEX)

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
        return v

    @field_validator("pincode", mode="before")
    @classmethod
    def normalise_pincode(cls, v: str | None) -> str | None:
        """Strip whitespace before the 6-digit regex check.

        Allows users to paste "682 314" or "682314 " from forms/emails.
        Final value stored in DB is always 6 digits with nothing else.
        """
        if v is None:
            return v
        if isinstance(v, str):
            return v.strip().replace(" ", "")
        return v


class CustomerCreate(CustomerBase):
    """Used on POST /customers — same shape as Base, just renamed for clarity."""

    pass


class CustomerUpdate(BaseModel):
    """All fields optional — partial updates via PATCH semantics on PUT.

    Fields not included in the request are left unchanged on the server.
    This is enabled by service-layer use of model_dump(exclude_unset=True).
    """

    model_config = ConfigDict(use_enum_values=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    primary_phone: str | None = Field(default=None, pattern=PHONE_REGEX)
    secondary_phone: str | None = Field(default=None, pattern=PHONE_REGEX)
    preferred_channel_phone: PreferredPhone | None = None
    whatsapp_enabled: bool | None = None

    # === Address fields (optional in updates — keep your existing values) ===
    address_line_1: str | None = Field(default=None, min_length=1, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, min_length=1, max_length=100)
    pincode: str | None = Field(default=None, pattern=PINCODE_REGEX)

    notes: str | None = None
    is_active: bool | None = None  # Allows soft-delete / reactivation via PUT

    @field_validator("primary_phone", "secondary_phone", mode="before")
    @classmethod
    def normalise_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if isinstance(v, str):
            return v.replace(" ", "").replace("-", "")
        return v

    @field_validator("pincode", mode="before")
    @classmethod
    def normalise_pincode(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if isinstance(v, str):
            return v.strip().replace(" ", "")
        return v


class CustomerOut(CustomerBase):
    """What the API returns to the client.

    from_attributes=True lets us call CustomerOut.model_validate(orm_object)
    so we don't manually transcribe each field from SQLAlchemy to Pydantic.
    """

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

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
