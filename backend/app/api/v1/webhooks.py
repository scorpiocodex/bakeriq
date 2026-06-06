"""Twilio inbound webhook.

Twilio sends a POST here whenever a customer messages our WhatsApp number.
Right now this is an echo bot — replies with the same body. Step 3 will
replace the echo handler with the state-machine router.

Why TwiML for the response: we can reply synchronously by returning a
TwiML <Message> in the response body, and Twilio sends it to the customer.
For longer / async replies (LLM parsing), we'll switch to dispatching a
Celery task and returning empty TwiML — the worker sends the outbound
message via the REST API.

Signature verification is mandatory on every endpoint here. Without it,
anyone could fake an inbound message and trigger our handlers.
"""

from fastapi import APIRouter, Depends, Request, Response

from app.core.twilio_client import verify_twilio_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/twilio",
    dependencies=[Depends(verify_twilio_signature)],
    response_class=Response
)
async def twilio_inbound(request: Request) -> Response:
    """Receive an inbound twilio whatsapp message"""
    form = await request.form()
    body = form.get("Body", "")
    from_ = form.get("From", "unknown")

    # TwiML response
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f"  <Message>Echo from BakeriQ: {body}</Message>\n"
        "</Response>"
    )

    return Response(content=twiml, media_type="application/xml")
