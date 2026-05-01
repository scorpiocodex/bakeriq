"""Pydantic schemas for the User domain."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """Shared fields between create / update / read."""

    email: EmailStr
    full_name: str | None = None


class UserCreate(UserBase):
    """Used on POST /register — adds password."""

    password: str = Field(min_length=8, max_length=72)
    # bcrypt has a 72-byte input limit. Document the cap explicitly.


class UserOut(UserBase):
    """What we send back to the client. Note: no password_hash."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    is_superuser: bool
    created_at: datetime
