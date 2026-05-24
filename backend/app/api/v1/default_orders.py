"""Default Order endpoints — a customer's recurring order template.

Customer-scoped URLs (the template only exists in relation to a customer):
  GET    /customers/{customer_id}/default-order  — fetch the template
  PUT    /customers/{customer_id}/default-order  — create or replace it
  DELETE /customers/{customer_id}/default-order  — remove it entirely

All require auth via Depends(get_current_user).

Note the router has NO prefix of its own — it mounts under the customers
path. We attach the customer_id-scoped routes directly. The main router
includes this with the /customers prefix.
"""

from uuid import UUID

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.default_order import DefaultOrderOut, DefaultOrderWrite
from app.services import default_order_service
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/customers", tags=["default-orders"])


@router.get(
    "/{customer_id}/default-order",
    response_model=DefaultOrderOut,
)
def get_default_order(
    customer_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch a customer's default order template.

    Returns 404 if the customer doesn't exist OR if the customer exists
    but has no template yet. The frontend treats 404 as "no template,
    show the empty add-items form."
    """
    default_order = default_order_service.get_default_order(db, customer_id)
    if default_order is None:
        # Customer exists (service validated) but has no template

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This customer has no default order template yet",
        )
    return DefaultOrderOut.model_validate(default_order)


@router.put(
    "/{customer_id}/default-order",
    response_model=DefaultOrderOut,
)
def upsert_default_order(
    customer_id: UUID,
    payload: DefaultOrderWrite,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create or replace a customer's default order template.

    Idempotent: sending the same payload twice produces the same result.
    The items list is replaced wholesale — whatever you send becomes the
    complete template.

    Returns 404 if the customer doesn't exist.
    Returns 422 if any product_id in items is invalid or inactive.
    """
    default_order = default_order_service.upsert_default_order(db, customer_id, payload)
    return DefaultOrderOut.model_validate(default_order)


@router.delete(
    "/{customer_id}/default-order",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_default_order(
    customer_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a customer's default order template entirely (parent + items).

    Returns 404 if the customer has no template.
    """
    default_order_service.delete_default_order(db, customer_id)
    return None
