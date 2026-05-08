"""Category business logic.

Categories are the simplest entity in the system — just name + sort
order. The service handles the standard CRUD plus a "category in use"
check that prevents deletion of categories referenced by products.
"""

from uuid import UUID

from app.models.category import Category
from app.models.product import Product
from app.schemas.category import CategoryCreate, CategoryUpdate
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def create_category(db: Session, payload: CategoryCreate) -> Category:
    """Insert a new category. The DB-level UNIQUE constraint on name
    catches duplicates; we translate that into a clean 409 response.

    Note: name normalisation (lowercase + trim) happens in the Pydantic
    schema, so by the time the value reaches here it's canonical.
    """
    category = Category(**payload.model_dump())
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        # The unique constraint on name fired. Roll back the failed
        # transaction so the session is reusable, then return a clean
        # error to the client.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Category '{payload.name}' already exists",
        )
    db.refresh(category)
    return category


def get_category(db: Session, category_id: UUID) -> Category:
    """Fetch by ID. Raises 404 if not found."""
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    return category


def list_categories(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status_filter: str = "active",
) -> tuple[list[Category], int]:
    """List categories with simple status filtering and sort.

    Sorted by display_order ASC, then by created_at ASC for stable
    ordering when multiple categories share the same display_order.

    status_filter takes three values:
      - 'active'   (default): only is_active=True  categories
      - 'inactive': only is_active=False categories
      - 'all':     both
    """
    query = select(Category)
    count_query = select(Category)

    if status_filter == "active":
        query = query.where(Category.is_active == True)
        count_query = count_query.where(Category.is_active == True)
    elif status_filter == "inactive":
        query = query.where(Category.is_active == False)
        count_query = count_query.where(Category.is_active == False)
    elif status_filter == "all":
        pass
    else:
        # Defensive fallback
        query = query.where(Category.is_active == True)
        count_query = count_query.where(Category.is_active == True)

    total = len(db.scalars(count_query).all())

    query = query.order_by(Category.display_order.asc(), Category.created_at.asc())
    query = query.offset(skip).limit(limit)
    items = list(db.scalars(query).all())

    return items, total


def update_category(
    db: Session, category_id: UUID, payload: CategoryUpdate
) -> Category:
    """Partial update. Renames trigger the same 409 path as creates if
    the new name collides with an existing category."""
    category = get_category(db, category_id)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A category with name '{update_data.get('name')}' already exists",
        )
    db.refresh(category)
    return category


def deactivate_category(db: Session, category_id: UUID) -> Category:
    """Soft-delete via is_active=False. Always succeeds — categories
    can be deactivated even if products reference them. Products
    keep their FK reference; the categories dropdown filters out
    inactive entries.
    """
    category = get_category(db, category_id)
    if not category.is_active:
        # Idempotent
        return category
    category.is_active = False
    db.commit()
    db.refresh(category)
    return category


def delete_category(db: Session, category_id: UUID) -> None:
    """Hard-delete. Only allowed if no products reference this category.

    Use deactivate_category for the soft-delete path; this is the
    "really actually delete it" path used for cleanup of typo'd
    categories before any products attach to them.

    The DB-level FK constraint (ON DELETE RESTRICT) would block this
    if products reference it, but checking explicitly first gives a
    cleaner error message to the API consumer.
    """
    category = get_category(db, category_id)

    in_use_count = db.scalars(
        select(Product).where(Product.category_id == category.id).limit(1)
    ).first()
    if in_use_count is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Category is in use by one or more products. "
                "Reassign or deactivate the products first, "
                "or deactivate the category instead of deleting."
            ),
        )

    db.delete(category)
    db.commit()
