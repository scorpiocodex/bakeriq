"""Category model — taxonomy for products.

Schema notes:
  - One row per category. Examples: "savoury", "sweet", "cake", "bread".
    Owner manages this list — creates new ones from the products page,
    renames/deactivates from the settings page.
  - name: case-sensitive UNIQUE. Two categories can't share a name.
    Normalisation (lowercase + trim) happens at the Pydantic layer
    before storage, so DB stores canonical lowercase form.
  - display_order: optional integer, used to sort the dropdown. Owner
    might want "savoury" before "sweet" alphabetically; or the reverse
    based on what the bakery sells most. Defaults to 0 if not specified.
  - Soft-delete via is_active — preserves product references. Hard
    delete blocked by FK ON DELETE RESTRICT (see product model).
"""

from datetime import datetime
from uuid import UUID, uuid4

from app.models.base import Base
from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # name is unique and indexed (the unique constraint creates the index
    # implicitly). Stored lowercase — Pydantic normalises before insert.
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    # display_order: lower values sort earlier in dropdowns. Default 0
    # means "use insertion order" effectively, since categories created
    # later get later created_at timestamps and we sort by (display_order,
    # created_at).
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
