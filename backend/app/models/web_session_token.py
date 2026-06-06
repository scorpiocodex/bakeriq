"""Web Session Token — auth token for customer web app links.

When the bot sends a customer a link like
  https://order.bakeriq.app/reorder/k7m2abc...
the path segment `k7m2abc...` is a token in this table. It's the only
authentication for the customer web app — the web app validates the token
against this table, gets the customer_id and kind ('reorder'|'new'|'edit'),
and serves the appropriate page.

Tokens are session-style (not single-use):
  - Multi-use during their TTL (customer might save once, come back later,
    edit again, place order — all on the same token)
  - 30-minute expiry from creation
  - consumed_at is set when the customer hits 'Place order' — locks the
    token from further use (the order is now real, no more editing via
    that token)

Stored in Postgres rather than Redis because we want a permanent audit
trail of "customer X opened web session Y at time Z" for support cases
later. Redis still holds the cart contents — only the token-to-customer
binding lives here.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from app.models.base import Base
from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.customer import Customer


class WebSessionToken(Base):
    __tablename__ = "web_session_tokens"
    __table_args__ = (
        Index("idx_web_session_tokens_customer", "customer_id"),
        Index("idx_web_session_tokens_expires", "expires_at"),
    )

    # The token IS the primary key — 32-char URL-safe random string.
    # Generated via secrets.token_urlsafe(24) which yields 32 chars.
    token: Mapped[str] = mapped_column(String(32), primary_key=True)

    customer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 'reorder' | 'new' | 'edit' — which web page the token grants access to.
    kind: Mapped[str] = mapped_column(String(20), nullable=False)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Set when 'Place order' is hit — token becomes inert from then on.
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    customer: Mapped["Customer"] = relationship(
        "Customer",
        lazy="joined",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
