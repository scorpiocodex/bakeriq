"""phase 5 inventory: stock fields on products

Revision ID: abd7ac3d857c
Revises: 209624631a94
Create Date: 2026-07-23 08:03:46.728513

Three nullable columns on products. No new tables.

Only sealed, packaged goods carry stock — ladoo packets, bread, biscuits,
some cakes. Made-to-order items are baked and sold the same day, so their
"inventory" is the chef's prep list, derived from today's orders at read
time rather than stored.

Existing rows get is_stockable=false and null counts, which is correct:
nothing was tracked before, and the owner opts each product in.

Hand-cleaned from autogenerate, which also emitted:
  - a drop/recreate of ix_customers_secondary_phone (a no-op it re-detects
    on every migration touching customers)
  - VARCHAR length changes on pending_registrations already reconciled in
    209624631a94 — cosmetic differences between the declared length and
    what Postgres reports
  - op.drop_constraint(None, 'customers', ...) in the downgrade, which
    would crash if anyone ever rolled back
See DEVELOPMENT.md for the full list of autogen quirks on this schema.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "abd7ac3d857c"
down_revision: Union[str, None] = "209624631a94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default so existing rows get false rather than failing the
    # NOT NULL constraint.
    op.add_column(
        "products",
        sa.Column(
            "is_stockable",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )

    # Nullable rather than defaulting to 0 — "not tracked" and "tracked but
    # empty" are different states, and the low-stock query has to tell them
    # apart.
    op.add_column(
        "products",
        sa.Column("stock_quantity", sa.Integer(), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("low_stock_threshold", sa.Integer(), nullable=True),
    )

    op.create_index(
        op.f("ix_products_is_stockable"),
        "products",
        ["is_stockable"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_products_is_stockable"), table_name="products")
    op.drop_column("products", "low_stock_threshold")
    op.drop_column("products", "stock_quantity")
    op.drop_column("products", "is_stockable")
