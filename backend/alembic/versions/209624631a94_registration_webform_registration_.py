"""registration webform: registration_tokens + pending_registrations reshape

Revision ID: 209624631a94
Revises: <PREVIOUS_REVISION_ID>
Create Date: 2026-07-16

Two schema changes bundled together for the Phase 3.5 webform migration:

  1. Create the `registration_tokens` table for the new webform-based
     registration flow (Phase 3.5).

  2. Reshape `pending_registrations` to match the new flow:
     - Drop `conversation_state` (bot state machine deleted)
     - Drop `area` (replaced by structured address fields)
     - Add `address_line_1`, `address_line_2`, `city`, `state`, `pincode`
       (matches Customer table for clean 1:1 mapping on approval)
     - Rename status value 'pending' → 'awaiting_approval' for clarity

Data preservation: 1 existing row today, already-approved (customer_id
populated). The `area` column value is lost. That's acceptable since
the approved row already promoted to Customer and the Customer has
its own address fields (currently null in that row — the "Area: X"
notes text was the only signal).

Autogen was too aggressive with cosmetic type changes (VARCHAR length
tweaks, unique-constraint index rename on customers.secondary_phone).
Those aren't real schema changes at the Postgres level — they're
SQLAlchemy 2.0 metadata differences. This migration was rewritten by
hand to avoid running that noise.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Alembic will fill these in when it detects the file. Do NOT hand-edit
# them; if they get regenerated for some reason let alembic set them.
revision = "209624631a94"
down_revision = "0ead500de10a"  # <-- alembic will populate this from the current head
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ============================================================
    # 1. Create registration_tokens table
    # ============================================================
    op.create_table(
        "registration_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("phone", sa.String(length=24), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )
    op.create_index("ix_registration_tokens_phone", "registration_tokens", ["phone"])
    op.create_index(
        "ix_registration_tokens_token",
        "registration_tokens",
        ["token"],
        unique=True,
    )

    # ============================================================
    # 2. Reshape pending_registrations
    # ============================================================
    # 2a. Drop the columns we no longer use.
    op.drop_column("pending_registrations", "conversation_state")
    op.drop_column("pending_registrations", "area")

    # 2b. Add the structured address fields.
    op.add_column(
        "pending_registrations",
        sa.Column("address_line_1", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "pending_registrations",
        sa.Column("address_line_2", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "pending_registrations",
        sa.Column("city", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "pending_registrations",
        sa.Column("state", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "pending_registrations",
        sa.Column("pincode", sa.String(length=10), nullable=True),
    )

    # 2c. Rename status value 'pending' → 'awaiting_approval' if any
    # rows exist with the old value. Idempotent — if the data is fresh
    # or already migrated, this is a no-op.
    op.execute(
        "UPDATE pending_registrations SET status = 'awaiting_approval' "
        "WHERE status = 'pending'"
    )


def downgrade() -> None:
    # Reverse of upgrade. Data will be lost — the address fields go away,
    # and 'awaiting_approval' rows revert to 'pending' semantically but
    # we can't restore data that isn't there.

    # Reverse the status rename
    op.execute(
        "UPDATE pending_registrations SET status = 'pending' "
        "WHERE status = 'awaiting_approval'"
    )

    # Drop the new address columns
    op.drop_column("pending_registrations", "pincode")
    op.drop_column("pending_registrations", "state")
    op.drop_column("pending_registrations", "city")
    op.drop_column("pending_registrations", "address_line_2")
    op.drop_column("pending_registrations", "address_line_1")

    # Re-add the old columns (nullable — no data to restore)
    op.add_column(
        "pending_registrations",
        sa.Column("conversation_state", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "pending_registrations",
        sa.Column("area", sa.String(length=200), nullable=True),
    )

    # Drop the registration_tokens table
    op.drop_index("ix_registration_tokens_token", "registration_tokens")
    op.drop_index("ix_registration_tokens_phone", "registration_tokens")
    op.drop_table("registration_tokens")
