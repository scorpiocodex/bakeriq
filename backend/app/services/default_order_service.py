"""Default Order business logic.

The signature operation here is the NESTED WRITE with replace-all
semantics. When the owner saves a customer's template, the client sends
the complete desired items list. The service:
  1. Validates the customer exists
  2. Validates every product_id in the items list exists and is active
  3. Finds-or-creates the DefaultOrder parent row
  4. Replaces ALL items: assigns the new list to default_order.items;
     SQLAlchemy's cascade="all, delete-orphan" deletes the old rows and
     inserts the new ones in one transaction

This is the first place we rely on the delete-orphan cascade. Reassigning
the .items collection is all it takes — no manual DELETE loop.
"""

from uuid import UUID

from app.models.customer import Customer
from app.models.default_order import DefaultOrder, DefaultOrderItem
from app.models.product import Product
from app.schemas.default_order import DefaultOrderWrite
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session


def _validate_customer_exists(db: Session, customer_id: UUID) -> Customer:
    """Raises 404 if the customer doesn't exist. Returns the customer."""
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    return customer


def _validate_products(db: Session, items: list) -> None:
    """Raises 422 if any product_id in the items list doesn't exist or is
    inactive. Checked all at once with a single query for efficiency.

    422 (not 404) because the bad data is in the request body — the
    items list references a product that can't be used.
    """
    if not items:
        return

    requested_ids = {item.product_id for item in items}
    found = db.scalars(select(Product).where(Product.id.in_(requested_ids))).all()
    found_by_id = {p.id: p for p in found}

    for pid in requested_ids:
        product = found_by_id.get(pid)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Product with id {pid} does not exist",
            )
        if not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Product '{product.name}' is inactive and can't be added to a default order",
            )


def get_default_order(db: Session, customer_id: UUID) -> DefaultOrder | None:
    """Fetch a customer's default order template, or None if they have none.

    Validates the customer exists first (404 if not). Returning None for
    "customer exists but has no template" lets the endpoint return a clean
    404 with a template-specific message vs the customer-not-found 404.
    """
    _validate_customer_exists(db, customer_id)
    default_order = db.scalars(
        select(DefaultOrder).where(DefaultOrder.customer_id == customer_id)
    ).first()
    return default_order


def upsert_default_order(
    db: Session, customer_id: UUID, payload: DefaultOrderWrite
) -> DefaultOrder:
    """Create or replace a customer's default order template.

    "Upsert" because the customer-scoped PUT means "make the template look
    like this" regardless of whether one already exists. If none exists,
    create it. If one does, replace its items wholesale.

    The replace-all magic: we assign default_order.items = [new objects].
    SQLAlchemy's cascade="all, delete-orphan" diffs the collection and
    issues DELETEs for removed items + INSERTs for new ones, all inside
    the single db.commit() transaction.
    """
    _validate_customer_exists(db, customer_id)
    _validate_products(db, payload.items)

    # Find existing template or create a new parent row
    default_order = db.scalars(
        select(DefaultOrder).where(DefaultOrder.customer_id == customer_id)
    ).first()

    if default_order is None:
        default_order = DefaultOrder(customer_id=customer_id)
        db.add(default_order)

    # Update parent fields
    default_order.notes = payload.notes
    default_order.is_active = payload.is_active

    # Replace-all items. Building fresh DefaultOrderItem objects and
    # assigning the list triggers the delete-orphan cascade: old items
    # not in the new list are deleted, new ones inserted.
    default_order.items = [
        DefaultOrderItem(
            product_id=item.product_id,
            quantity=item.quantity,
        )
        for item in payload.items
    ]

    db.commit()
    db.refresh(default_order)
    return default_order


def delete_default_order(db: Session, customer_id: UUID) -> None:
    """Hard-delete a customer's template entirely (parent + items via cascade).

    Used when the owner wants to remove the template completely rather
    than just deactivating it. The ON DELETE CASCADE on default_order_items
    means deleting the parent removes the children automatically.

    Raises 404 if the customer has no template.
    """
    _validate_customer_exists(db, customer_id)
    default_order = db.scalars(
        select(DefaultOrder).where(DefaultOrder.customer_id == customer_id)
    ).first()
    if default_order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This customer has no default order template",
        )
    db.delete(default_order)
    db.commit()
