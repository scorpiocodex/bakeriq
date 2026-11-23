"""Twilio Content API client for managing WhatsApp Content Templates.

The Twilio Python SDK (twilio==9.x as of this writing) does not expose a
client method for *creating* Content Templates — only for sending
messages that reference an existing ContentSid. Twilio's own docs direct
you to the REST API for template management:

    https://www.twilio.com/docs/content/content-api-resources
    https://www.twilio.com/en-us/blog/get-started-with-content-api

This module wraps that REST surface using httpx2,
covering the operations BakeriQ needs:

* create_quick_reply         — twilio/quick-reply, used for greeting + fallback
* create_call_to_action      — twilio/call-to-action, used for cart-link URL button
* get_template / list_templates / find_by_friendly_name
* delete_template

Templates created here are NOT submitted for WhatsApp approval. That's
intentional: per Twilio's docs, quick-reply and URL CTA buttons work
in-session (within the 24h sandbox window after a customer message)
without approval. Every BakeriQ reply is in-session by definition.

Sending messages that reference a ContentSid is done through the regular
Twilio SDK in app.services.whatsapp_sender — this module is only for
template management.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

import httpx2

from app.core.config import settings

CONTENT_API_BASE_URL = "https://content.twilio.com/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0
LIST_PAGE_SIZE = 50


class TwilioContentError(RuntimeError):
    """Raised when the Content API returns a non-2xx response."""

    def __init__(self, status_code: int, body: str, operation: str) -> None:
        super().__init__(
            f"Twilio Content API {operation} failed (HTTP {status_code}): {body[:500]}"
        )
        self.status_code = status_code
        self.body = body
        self.operation = operation


@dataclass(frozen=True)
class QuickReplyAction:
    """One tappable quick-reply button.

    `title` is the user-visible label. When the customer taps it, Twilio
    delivers Body=<title> to our inbound webhook, which is how the
    existing dispatcher matches taps to fast-path constants.

    `id` is an opaque payload string (max 200 chars) Twilio echoes back
    as ButtonPayload. We don't currently consume it but it is required.
    """

    title: str
    id: str


@dataclass(frozen=True)
class UrlAction:
    """One CTA URL button. `url` may include {{N}} placeholders."""

    title: str
    url: str


class TwilioContentClient:
    """Thin wrapper over the Twilio Content REST API.

    Construct via `get_content_client()` for normal use (reads creds from
    settings), or pass them explicitly with a custom `http_client` for
    tests:

        transport = httpx2.MockTransport(handler)
        with httpx2.Client(transport=transport) as http:
            client = TwilioContentClient(
                account_sid="ACtest", auth_token="t", http_client=http,
            )
            ...
    """

    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        http_client: httpx2.Client | None = None,
    ) -> None:
        self._auth: tuple[str, str] = (account_sid, auth_token)
        if http_client is None:
            self._http = httpx2.Client(timeout=DEFAULT_TIMEOUT_SECONDS)
            self._owns_http = True
        else:
            self._http = http_client
            self._owns_http = False

    # ---- create ---------------------------------------------------------

    def create_quick_reply(
        self,
        *,
        friendly_name: str,
        body: str,
        actions: list[QuickReplyAction],
        variables: dict[str, str] | None = None,
        language: str = "en",
    ) -> str:
        """Create a twilio/quick-reply template. Returns the ContentSid (HX...).

        WhatsApp permits 1-3 quick-reply buttons per template.
        """
        if not 1 <= len(actions) <= 3:
            raise ValueError(
                f"quick-reply requires between 1 and 3 actions, got {len(actions)}"
            )
        payload: dict[str, Any] = {
            "friendly_name": friendly_name,
            "language": language,
            "types": {
                "twilio/quick-reply": {
                    "body": body,
                    "actions": [{"title": a.title, "id": a.id} for a in actions],
                }
            },
        }
        if variables:
            payload["variables"] = variables
        return self._create(payload)

    def create_call_to_action(
        self,
        *,
        friendly_name: str,
        body: str,
        actions: list[UrlAction],
        variables: dict[str, str] | None = None,
        language: str = "en",
    ) -> str:
        """Create a twilio/call-to-action template with URL buttons.

        WhatsApp permits up to 2 buttons on a call-to-action, but only 1
        of each type (URL/phone). For BakeriQ we use exactly one URL.
        """
        if not 1 <= len(actions) <= 2:
            raise ValueError(
                f"call-to-action requires between 1 and 2 actions, got {len(actions)}"
            )
        payload: dict[str, Any] = {
            "friendly_name": friendly_name,
            "language": language,
            "types": {
                "twilio/call-to-action": {
                    "body": body,
                    "actions": [
                        {"type": "URL", "title": a.title, "url": a.url} for a in actions
                    ],
                }
            },
        }
        if variables:
            payload["variables"] = variables
        return self._create(payload)

    def _create(self, payload: dict[str, Any]) -> str:
        response = self._http.post(
            f"{CONTENT_API_BASE_URL}/Content",
            json=payload,
            auth=self._auth,
            headers={"Content-Type": "application/json"},
        )
        if response.status_code >= 400:
            raise TwilioContentError(
                response.status_code, response.text, operation="create"
            )
        sid = response.json().get("sid")
        if not sid:
            raise TwilioContentError(
                response.status_code,
                f"response missing 'sid': {response.text[:500]}",
                operation="create",
            )
        return str(sid)

    # ---- read -----------------------------------------------------------

    def get_template(self, content_sid: str) -> dict[str, Any]:
        """Fetch a single template by SID. Raises on 404."""
        response = self._http.get(
            f"{CONTENT_API_BASE_URL}/Content/{content_sid}",
            auth=self._auth,
        )
        if response.status_code >= 400:
            raise TwilioContentError(
                response.status_code, response.text, operation="get"
            )
        return response.json()

    def list_templates(self) -> Iterator[dict[str, Any]]:
        """Iterate over all templates, paginating as needed."""
        url: str | None = f"{CONTENT_API_BASE_URL}/Content"
        params: dict[str, Any] | None = {"PageSize": LIST_PAGE_SIZE}
        while url:
            response = self._http.get(url, params=params, auth=self._auth)
            if response.status_code >= 400:
                raise TwilioContentError(
                    response.status_code, response.text, operation="list"
                )
            body = response.json()
            for content in body.get("contents", []):
                yield content
            meta = body.get("meta", {})
            url = meta.get("next_page_url")
            params = None  # next_page_url already encodes its params

    def find_by_friendly_name(self, friendly_name: str) -> str | None:
        """Return the SID of the first template with this friendly_name, or None.

        O(n) over all templates; fine for our scale (we manage ~3).
        """
        for content in self.list_templates():
            if content.get("friendly_name") == friendly_name:
                sid = content.get("sid")
                return str(sid) if sid else None
        return None

    # ---- delete ---------------------------------------------------------

    def delete_template(self, content_sid: str) -> None:
        """Delete a template. Idempotent — 404 is swallowed."""
        response = self._http.delete(
            f"{CONTENT_API_BASE_URL}/Content/{content_sid}",
            auth=self._auth,
        )
        if response.status_code not in (204, 404):
            raise TwilioContentError(
                response.status_code, response.text, operation="delete"
            )

    # ---- lifecycle ------------------------------------------------------

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> "TwilioContentClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


def get_content_client() -> TwilioContentClient:
    """Construct a TwilioContentClient from app settings."""
    return TwilioContentClient(
        account_sid=settings.TWILIO_ACCOUNT_SID,
        auth_token=settings.TWILIO_AUTH_TOKEN,
    )
