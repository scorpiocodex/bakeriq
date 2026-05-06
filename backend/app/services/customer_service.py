"""Customer business logic — keeps validation rules in one place."""

from uuid import UUID

from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session


def _check_phone_uniqueness(
    db: Session,
    primary_phone: str | None,
    secondary_phone: str | None,
    exclude_customer_id: UUID | None = None,
) -> None:
    """Verify no other customer has either phone in either of their phone columns.

    Raises HTTPException(409) if duplication found. The schema doc decided
    to enforce cross-column uniqueness in the app layer rather than via DB
    triggers — this is that enforcement.

    exclude_customer_id is set on UPDATE to skip the row being updated
    (otherwise an update that doesn't change phones would match itself).
    """
    phones_to_check = [p for p in (primary_phone, secondary_phone) if p is not None]
    if not phones_to_check:
        return

    # SELECT * FROM customers
    # WHERE (primary_phone IN (...) OR secondary_phone IN (...))
    #   AND id != exclude_customer_id (if provided)
    query = select(Customer).where(
        or_(
            Customer.primary_phone.in_(phones_to_check),
            Customer.secondary_phone.in_(phones_to_check),
        )
    )
    if exclude_customer_id is not None:
        query = query.where(Customer.id != exclude_customer_id)

    conflicting = db.scalars(query).first()
    if conflicting is not None:
        # Tell the caller WHICH phone collided, so the frontend can highlight
        # the right field in the form.
        if conflicting.primary_phone in phones_to_check:
            collided_phone = conflicting.primary_phone
        else:
            collided_phone = conflicting.secondary_phone
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Phone number {collided_phone} is already used by another customer",
        )


def create_customer(db: Session, payload: CustomerCreate) -> Customer:
    _check_phone_uniqueness(db, payload.primary_phone, payload.secondary_phone)

    customer = Customer(**payload.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def get_customer(db: Session, customer_id: UUID) -> Customer:
    """Fetch by ID. Raises 404 if not found."""
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    return customer


def list_customers(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    whatsapp_only: bool | None = None,
    include_inactive: bool = False,
) -> tuple[list[Customer], int]:
    """List with pagination + filters. Returns (items, total)."""
    query = select(Customer)
    count_query = select(Customer)

    if not include_inactive:
        query = query.where(Customer.is_active == True)
        count_query = count_query.where(Customer.is_active == True)

    if whatsapp_only is not None:
        query = query.where(Customer.whatsapp_enabled == whatsapp_only)
        count_query = count_query.where(Customer.whatsapp_enabled == whatsapp_only)

    if search:
        # Case-insensitive search on name OR primary/secondary phones.
        # ILIKE for case-insensitive on Postgres.
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Customer.name.ilike(search_pattern),
                Customer.primary_phone.ilike(search_pattern),
                Customer.secondary_phone.ilike(search_pattern),
            )
        )
        count_query = count_query.where(
            or_(
                Customer.name.ilike(search_pattern),
                Customer.primary_phone.ilike(search_pattern),
                Customer.secondary_phone.ilike(search_pattern),
            )
        )

    # Get total before applying skip/limit
    total = len(db.scalars(count_query).all())

    # Apply ordering and pagination
    query = query.order_by(Customer.name.asc()).offset(skip).limit(limit)
    items = list(db.scalars(query).all())

    return items, total


def update_customer(
    db: Session, customer_id: UUID, payload: CustomerUpdate
) -> Customer:
    customer = get_customer(db, customer_id)

    update_data = payload.model_dump(exclude_unset=True)

    # If either phone is being changed, check uniqueness against everyone
    # except this customer.
    if "primary_phone" in update_data or "secondary_phone" in update_data:
        new_primary = update_data.get("primary_phone", customer.primary_phone)
        new_secondary = update_data.get("secondary_phone", customer.secondary_phone)
        _check_phone_uniqueness(
            db, new_primary, new_secondary, exclude_customer_id=customer.id
        )

    for field, value in update_data.items():
        setattr(customer, field, value)

    db.commit()
    db.refresh(customer)
    return customer


def deactivate_customer(db: Session, customer_id: UUID) -> Customer:
    """Soft-delete via is_active=False.
    We never DELETE because of order history FKs."""
    customer = get_customer(db, customer_id)
    if not customer.is_active:
        # Idempotent — deactivating an already-inactive customer is fine.
        return customer
    customer.is_active = False
    db.commit()
    db.refresh(customer)
    return customer
