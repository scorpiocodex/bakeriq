"""Outbound reply primitives shared by handlers and the dispatcher.

A handler returns either None (no fast-path match — caller routes to
the LLM safety valve) or a list[Reply] (one or more outbound messages
to send in order). Each Reply is either text-based (body) or
template-based (content_sid + variables); never both.

The webhook dispatcher decides delivery channel (TwiML vs REST API)
based on the Reply shape — see app.api.v1.webhooks.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Reply:
    """One outbound WhatsApp message.

    Exactly one of `body` (free-form text) or `content_sid` (Content
    Template) must be set; the XOR is enforced in __post_init__.

    Use the factory classmethods Reply.text() and Reply.template() at
    call sites for readability — bare-constructor calls with both fields
    None would fail at runtime.

    Fields:
        body: Plain text body to send via send_text.
        content_sid: Twilio ContentSid (HX...) for a Content Template.
        content_variables: {"1": "name", ...} substitution map for the
            template's {{1}}, {{2}}, ... placeholders. None if the
            template has no variables.
        log_body: Optional human-readable text to record in the audit
            log when sending a template. Ignored if body is set (the
            body itself goes into the log). See whatsapp_sender.send_template
            for rationale.
    """

    body: str | None = None
    content_sid: str | None = None
    content_variables: dict[str, str] | None = None
    log_body: str | None = None

    def __post_init__(self) -> None:
        # XOR check — exactly one of body / content_sid must be set.
        if (self.body is None) == (self.content_sid is None):
            raise ValueError("Reply requires exactly one of body or content_sid")

    @classmethod
    def text(cls, body: str) -> "Reply":
        """Factory: free-form text reply."""
        return cls(body=body)

    @classmethod
    def template(
        cls,
        content_sid: str,
        *,
        variables: dict[str, str] | None = None,
        log_body: str | None = None,
    ) -> "Reply":
        """Factory: Content Template reply with optional variable substitutions."""
        return cls(
            content_sid=content_sid,
            content_variables=variables,
            log_body=log_body,
        )

    @property
    def is_template(self) -> bool:
        return self.content_sid is not None
