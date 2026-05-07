"""customer address fields - replace single address with 5 columns

This migration replaces the single free-text `address` column with
5 structured columns matching Indian postal format.

Important: existing customer rows must be deleted before this migration
applies, because the new NOT NULL columns can't be backfilled with
meaningful data. At time of writing the customers table contains only
test data (Anita Menon from Milestone A backend testing). Production
deployments should never run this migration with real customer data.

Revision ID: bf696517878c
Revises: 075d1f382176
Create Date: 2026-05-06 08:17:20.139257

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bf696517878c"
down_revision: Union[str, None] = "075d1f382176"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: clear existing customer rows.
    # The new NOT NULL columns (address_line_1, city, state, pincode)
    # have no sensible default for legacy rows. Test data only — no
    # real customer records lost.
    op.execute("DELETE FROM customers")

    # Step 2: add the 5 new address columns.
    # All NOT NULL on city/state/pincode; address_line_2 is the only
    # optional one.
    op.add_column(
        "customers",
        sa.Column("address_line_1", sa.String(length=255), nullable=False),
    )
    op.add_column(
        "customers",
        sa.Column("address_line_2", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "customers",
        sa.Column("city", sa.String(length=100), nullable=False),
    )
    op.add_column(
        "customers",
        sa.Column("state", sa.String(length=100), nullable=False),
    )
    op.add_column(
        "customers",
        sa.Column("pincode", sa.String(length=6), nullable=False),
    )

    # Step 3: drop the legacy single-column address.
    # Note: we deliberately do NOT touch the secondary_phone unique
    # index here. Autogenerate proposed converting it from a unique
    # index to a unique constraint, but they're functionally identical
    # in Postgres and the existing index works fine. Less churn = safer.
    op.drop_column("customers", "address")


def downgrade() -> None:
    # Restore the legacy column. Note: legacy data is permanently lost
    # — downgrade restores the schema, not the prior content.
    op.add_column(
        "customers",
        sa.Column("address", sa.TEXT(), nullable=True),
    )
    op.drop_column("customers", "pincode")
    op.drop_column("customers", "state")
    op.drop_column("customers", "city")
    op.drop_column("customers", "address_line_2")
    op.drop_column("customers", "address_line_1")
