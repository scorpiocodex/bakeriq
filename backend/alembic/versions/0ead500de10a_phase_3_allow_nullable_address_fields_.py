"""phase-3: allow nullable address fields on customers (for bot-registered)

Revision ID: 0ead500de10a
Revises: caed2c7ae0e2
Create Date: 2026-06-06 12:36:30.725369

Bot-registered customers don't have a full address at the moment of
sign-up — they go through registration with just name + area on
WhatsApp, and the owner fills in the address when delivery is needed.
Relaxing the NOT NULL constraint on address fields supports that flow
without forcing the bot to invent placeholder values.

address_line_1, city, state, pincode go nullable.
address_line_2 was already nullable; no change.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0ead500de10a'
down_revision: Union[str, None] = 'caed2c7ae0e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'customers', 'address_line_1',
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.alter_column(
        'customers', 'city',
        existing_type=sa.String(length=100),
        nullable=True,
    )
    op.alter_column(
        'customers', 'state',
        existing_type=sa.String(length=100),
        nullable=True,
    )
    op.alter_column(
        'customers', 'pincode',
        existing_type=sa.String(length=6),
        nullable=True,
    )


def downgrade() -> None:
    # NOTE: downgrade will FAIL if any rows have NULL in these columns.
    # That's correct behaviour — downgrade is only safe on a database
    # where the application has been treating these as required all along.
    # For dev / fresh resets it's fine.
    op.alter_column(
        'customers', 'pincode',
        existing_type=sa.String(length=6),
        nullable=False,
    )
    op.alter_column(
        'customers', 'state',
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.alter_column(
        'customers', 'city',
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.alter_column(
        'customers', 'address_line_1',
        existing_type=sa.String(length=255),
        nullable=False,
    )
