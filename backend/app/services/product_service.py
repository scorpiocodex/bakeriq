"""Product business logic — CRUD operations plus category validation.

Categories are validated by FK existence at write time: the service
checks the category exists before insert/update. The DB also has the
FK constraint as a safety net — but checking in the service gives
nicer error messages.
"""

from uuid import UUID

from app.models.category import Category
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session


def _validate_category_exists(db: Session, category_id: UUID) -> None:
    """Raises 422 if the category doesn't exist or is inactive.

    422 (not 404) because from the client's perspective the *product*
    doesn't fail to exist — the *request* fails validation. The bad
    field is category_id.
    """
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Category with id {category_id} does not exist",
        )
    if not category.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Category '{category.name}' is inactive. "
                "Reactivate it or pick a different category."
            ),
        )


def create_product(db: Session, payload: ProductCreate) -> Product:
    """Insert a new product. Validates that category_id references an
    existing active category before insert."""
    _validate_category_exists(db, payload.category_id)

    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def get_product(db: Session, product_id: UUID) -> Product:
    """Fetch by ID. Raises 404 if not found.

    The lazy='joined' relationship on Product.category means the
    category is fetched in the same query — no separate round-trip.
    """
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return product


def list_products(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    category_id: UUID | None = None,
    available_today: bool | None = None,
    status_filter: str = "active",
) -> tuple[list[Product], int]:
    """List with pagination + filters. Returns (items, total).

    Filter parameters all optional and combinable:
      - search: case-insensitive ILIKE on name or aliases JSON
      - category_id: only products in this specific category
      - available_today: filter by today's availability flag
      - status_filter: 'active' | 'inactive' | 'all' (matches customer pattern)

    Ordering: category name ASC, then product name ASC. So products in
    the products page list naturally group by category.
    """
    query = select(Product)
    count_query = select(Product)

    # === Status filter ===
    if status_filter == "active":
        query = query.where(Product.is_active == True)
        count_query = count_query.where(Product.is_active == True)
    elif status_filter == "inactive":
        query = query.where(Product.is_active == False)
        count_query = count_query.where(Product.is_active == False)
    elif status_filter == "all":
        pass
    else:
        # Defensive fallback
        query = query.where(Product.is_active == True)
        count_query = count_query.where(Product.is_active == True)

    # === Category filter ===
    if category_id is not None:
        query = query.where(Product.category_id == category_id)
        count_query = count_query.where(Product.category_id == category_id)

    # === Available today filter ===
    if available_today is not None:
        query = query.where(Product.is_available_today == available_today)
        count_query = count_query.where(Product.is_available_today == available_today)

    # === Search ===
    if search:
        search_pattern = f"%{search.lower()}%"
        # Search name OR description (case-insensitive)
        # Aliases (JSONB array) is searched separately because it's an
        # array — we use jsonb_path_exists/string_to_array logic.
        # For now, simple ILIKE on name + description is enough.
        query = query.where(
            or_(
                Product.name.ilike(search_pattern),
                Product.description.ilike(search_pattern),
            )
        )
        count_query = count_query.where(
            or_(
                Product.name.ilike(search_pattern),
                Product.description.ilike(search_pattern),
            )
        )

    total = len(db.scalars(count_query).all())

    # Order by category name, then product name. Natural reading order
    # for the products page.
    query = (
        query.join(Category, Product.category_id == Category.id)
        .order_by(Category.name.asc(), Product.name.asc())
        .offset(skip)
        .limit(limit)
    )
    items = list(db.scalars(query).all())

    return items, total


def update_product(db: Session, product_id: UUID, payload: ProductUpdate) -> Product:
    """Partial update. If category_id is changed, validate the new one
    exists and is active."""
    product = get_product(db, product_id)

    update_data = payload.model_dump(exclude_unset=True)

    # If category is being changed, validate the new one
    if "category_id" in update_data:
        _validate_category_exists(db, update_data["category_id"])

    for field, value in update_data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)
    return product


def deactivate_product(db: Session, product_id: UUID) -> Product:
    """Soft-delete via is_active=False. Order history references stay
    valid because we never DELETE."""
    product = get_product(db, product_id)
    if not product.is_active:
        return product
    product.is_active = False
    db.commit()
    db.refresh(product)
    return product
