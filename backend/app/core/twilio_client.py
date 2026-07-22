"""Twilio integration — client + signature verification.

We use Twilio for the WhatsApp Business Platform (Sandbox in dev, real
sender in prod).

Signature verification protects the inbound webhook: Twilio signs every
request with HMAC-SHA1 of (URL + sorted-form-data) using your Auth Token.
We verify the signature on every request and reject anything that doesn't
match — without this, anyone could POST to our webhook and fake messages.

The verification is wrapped in a FastAPI dependency so each webhook route
declares `_ = Depends(verify_twilio_signature)` and the request is rejected
upstream of the handler if the signature is bad.
"""

from twilio.request_validator import RequestValidator
from twilio.rest import Client

from app.core.config import settings
from fastapi import HTTPException, Request, status


_twilio_client: Client | None = None


def get_twilio_client() -> Client:
    """Return the singleton twilio REST client"""
    global _twilio_client
    if _twilio_client is None:
        _twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return _twilio_client


async def verify_twilio_signature(request: Request) -> None:
    """FastAPI dependency that rejects requests not signed by Twilio"""
    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing X-Twilio-Signature header"
        )

    # Reconstruct Twilio URL
    url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}{request.url.path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    # Twilio form-encoded POST bodies
    form = await request.form()
    params = {k: v for k, v in form.items()}

    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    if not validator.validate(url, params, signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio Signature"
        )
