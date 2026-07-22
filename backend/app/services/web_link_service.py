"""Web link generation — bot-side helper to build customer web app URLs.

The bot issues a fresh token via token_service, then this module
formats the URL the customer taps in their WhatsApp message.

URL shape:
  CUSTOMER_WEB_BASE_URL + '/<kind>/<token>'
  e.g. https://customer-abc.ngrok-free.dev/reorder/8u4cv-VKz9...

The kind determines which page the customer web app router renders:
  - 'reorder' → /reorder/:token → ReorderPage (last order pre-filled)
  - 'new'     → /new/:token     → NewOrderPage (empty cart)
  - 'edit'    → /edit/:token    → EditPage (resume in-progress cart)
"""

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.customer import Customer
from app.services import token_service


def issue_link(db: Session, *, customer: Customer, kind: str) -> tuple[str, str]:
    """Issue a token + return (link, token_string).

    Caller is responsible for db.commit() — this function calls flush
    but not commit, so the caller can batch the token issue with the
    conversation_message insert.
    """
    token_row = token_service.issue_token(db, customer=customer, kind=kind)
    base = settings.CUSTOMER_WEB_BASE_URL.rstrip("/")
    link = f"{base}/{kind}/{token_row.token}"
    return link, token_row.token
