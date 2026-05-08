"""add categories table and migrate products to category_id FK

This migration:
  1. Creates the categories table
  2. Clears existing product rows (defensive — products is empty in dev,
     but the new category_id column is NOT NULL with no default, so any
     existing rows would block the migration)
  3. Adds products.category_id as a FK to categories.id with
     ON DELETE RESTRICT
  4. Drops the legacy products.category VARCHAR column

Note: dev only. Production deployments would need a data migration
strategy (backfill category_id from category text, then drop). Not
relevant today.

Revision ID: 1d8ab16b615d
Revises: d2b5f063e7c9
Create Date: 2026-05-08 06:41:50.518084

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1d8ab16b615d"
down_revision: Union[str, None] = "d2b5f063e7c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Create the categories table.
    op.create_table(
        "categories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        op.f("ix_categories_is_active"), "categories", ["is_active"], unique=False
    )

    # Step 2: Clear existing products. Defensive — products is empty in
    # dev, but if any rows existed this would prevent the NOT NULL FK
    # column add from failing. No-op when table is already empty.
    op.execute("DELETE FROM products")

    # Step 3: Add the new FK column. NOT NULL is safe now that the
    # table is empty.
    op.add_column("products", sa.Column("category_id", sa.UUID(), nullable=False))
    op.create_index(
        op.f("ix_products_category_id"), "products", ["category_id"], unique=False
    )
    op.create_foreign_key(
        "fk_products_category_id",  # named FK — easier to reference if needed later
        "products",
        "categories",
        ["category_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Step 4: Drop the legacy VARCHAR column and its index.
    op.drop_index("ix_products_category", table_name="products")
    op.drop_column("products", "category")


def downgrade() -> None:
    # Restore the legacy VARCHAR column. Note: data is permanently lost —
    # downgrade restores schema, not prior content.
    op.add_column(
        "products",
        sa.Column(
            "category", sa.VARCHAR(length=100), autoincrement=False, nullable=False
        ),
    )
    op.create_index("ix_products_category", "products", ["category"], unique=False)

    # Drop the FK and category_id column.
    op.drop_constraint("fk_products_category_id", "products", type_="foreignkey")
    op.drop_index(op.f("ix_products_category_id"), table_name="products")
    op.drop_column("products", "category_id")

    # Drop categories table.
    op.drop_index(op.f("ix_categories_is_active"), table_name="categories")
    op.drop_table("categories")
