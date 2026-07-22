"""phase-3: add is_draft, pending_registrations, conversations, web_session_tokens

Revision ID: caed2c7ae0e2
Revises: e9090fc68d66
Create Date: 2026-06-06 08:15:02.055196

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'caed2c7ae0e2'
down_revision: Union[str, None] = 'e9090fc68d66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === New table: pending_registrations ===
    op.create_table(
        'pending_registrations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=True),
        sa.Column('area', sa.String(length=200), nullable=True),
        sa.Column('conversation_state', sa.String(length=40), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pending_registrations_phone'), 'pending_registrations', ['phone'], unique=True)
    op.create_index(op.f('ix_pending_registrations_status'), 'pending_registrations', ['status'], unique=False)

    # === New table: web_session_tokens ===
    op.create_table(
        'web_session_tokens',
        sa.Column('token', sa.String(length=32), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('token'),
    )
    op.create_index('idx_web_session_tokens_customer', 'web_session_tokens', ['customer_id'], unique=False)
    op.create_index('idx_web_session_tokens_expires', 'web_session_tokens', ['expires_at'], unique=False)

    # === New table: conversations ===
    op.create_table(
        'conversations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('current_order_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_message_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['current_order_id'], ['orders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_conversations_customer_id'), 'conversations', ['customer_id'], unique=False)
    op.create_index(op.f('ix_conversations_phone'), 'conversations', ['phone'], unique=False)

    # === New table: conversation_messages ===
    op.create_table(
        'conversation_messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('direction', sa.String(length=10), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('twilio_sid', sa.String(length=40), nullable=True),
        sa.Column('intent', sa.String(length=40), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_conversation_messages_conv_created', 'conversation_messages', ['conversation_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_conversation_messages_conversation_id'), 'conversation_messages', ['conversation_id'], unique=False)

    # === Add is_draft column to orders ===
    # server_default='false' is essential: existing rows must get a value
    # when the column is added, otherwise the NOT NULL constraint fails.
    # New inserts from the application set the value explicitly via the
    # ORM default; this server_default only matters for the alter table.
    op.add_column(
        'orders',
        sa.Column('is_draft', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.create_index(op.f('ix_orders_is_draft'), 'orders', ['is_draft'], unique=False)


def downgrade() -> None:
    # === Reverse: orders.is_draft ===
    op.drop_index(op.f('ix_orders_is_draft'), table_name='orders')
    op.drop_column('orders', 'is_draft')

    # === Reverse: conversation_messages ===
    op.drop_index(op.f('ix_conversation_messages_conversation_id'), table_name='conversation_messages')
    op.drop_index('idx_conversation_messages_conv_created', table_name='conversation_messages')
    op.drop_table('conversation_messages')

    # === Reverse: conversations ===
    op.drop_index(op.f('ix_conversations_phone'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_customer_id'), table_name='conversations')
    op.drop_table('conversations')

    # === Reverse: web_session_tokens ===
    op.drop_index('idx_web_session_tokens_expires', table_name='web_session_tokens')
    op.drop_index('idx_web_session_tokens_customer', table_name='web_session_tokens')
    op.drop_table('web_session_tokens')

    # === Reverse: pending_registrations ===
    op.drop_index(op.f('ix_pending_registrations_status'), table_name='pending_registrations')
    op.drop_index(op.f('ix_pending_registrations_phone'), table_name='pending_registrations')
    op.drop_table('pending_registrations')
