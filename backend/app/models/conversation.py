"""Conversation models — audit trail of every inbound/outbound message.

A Conversation is a long-running thread between BakeriQ and one customer.
Each row in conversation_messages is a single message, inbound or outbound.

Why audit:
  - Debugging customer reports ("the bot said the wrong thing")
  - Owner review of bot behaviour
  - LLM context — the safety-valve parser can include the last N messages
    of conversation history when disambiguating
  - Phase 3 dashboard conversation viewer

Distinct from Redis state:
  - Redis holds the *current* conversation state (which step the bot is in)
    and is ephemeral (30-min TTL)
  - Postgres holds the *full history* and is permanent

The current_order_id is the most-recent draft order being built (if any) —
links the conversation to the order being assembled for it.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from app.models.base import Base
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.order import Order


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # Customer FK is nullable: pending registrations have conversations
    # too, before a Customer row exists.
    customer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Phone number is always present — it's the channel identifier.
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # The draft order currently being assembled in this conversation, if any.
    current_order_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
    )

    customer: Mapped["Customer | None"] = relationship(
        "Customer",
        lazy="joined",
    )

    current_order: Mapped["Order | None"] = relationship(
        "Order",
        lazy="joined",
    )

    # Messages are loaded on demand only — the conversation viewer fetches
    # them when the owner opens it, not on every conversation list query.
    messages: Mapped[list["ConversationMessage"]] = relationship(
        "ConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="ConversationMessage.created_at",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        # Index for the conversation-viewer query: "give me all messages
        # for this conversation ordered by time."
        Index(
            "idx_conversation_messages_conv_created",
            "conversation_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 'inbound' (from customer) or 'outbound' (from bot). String column,
    # not enum — only two values, no growth expected.
    direction: Mapped[str] = mapped_column(String(10), nullable=False)

    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Twilio's unique ID for the message. Inbound: from request payload.
    # Outbound: from the Twilio API response. Null for synthetic messages.
    twilio_sid: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # The intent classification for inbound messages, if the LLM safety
    # valve was called for this message. Null for outbound or for inbound
    # messages handled by fast-path keyword matching.
    intent: Mapped[str | None] = mapped_column(String(40), nullable=True)

    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
