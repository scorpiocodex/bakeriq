"""Tests for app.services.reply — the Reply outbound primitive.

The Reply dataclass enforces a body XOR content_sid invariant so a single
outbound is unambiguously either a text message or a Content Template,
never both. Factory classmethods (Reply.text, Reply.template) are the
canonical call sites; bare constructors with both fields None fail.

These tests are pure — no DB, no Twilio, no fixtures from conftest.
"""

import pytest
from app.services.reply import Reply

# ============================================================
# Factory: Reply.text
# ============================================================


class TestReplyText:
    def test_creates_text_reply(self):
        r = Reply.text("hello")
        assert r.body == "hello"
        assert r.content_sid is None
        assert r.content_variables is None
        assert r.log_body is None

    def test_is_template_false_for_text(self):
        r = Reply.text("hello")
        assert r.is_template is False

    def test_empty_body_string_is_valid(self):
        """Empty string is a valid body — the XOR check uses `is None`,
        not truthiness, so '' satisfies the invariant. Whether sending
        an empty message is *useful* is a different concern, but the
        Reply primitive itself doesn't reject it."""
        r = Reply.text("")
        assert r.body == ""
        assert r.is_template is False


# ============================================================
# Factory: Reply.template
# ============================================================


class TestReplyTemplate:
    def test_creates_template_reply_minimal(self):
        r = Reply.template("HX_abc123")
        assert r.content_sid == "HX_abc123"
        assert r.body is None
        assert r.content_variables is None
        assert r.log_body is None

    def test_creates_template_reply_with_variables(self):
        r = Reply.template(
            "HX_abc123",
            variables={"1": "Anita", "2": "tok_xyz"},
        )
        assert r.content_sid == "HX_abc123"
        assert r.content_variables == {"1": "Anita", "2": "tok_xyz"}

    def test_creates_template_reply_with_log_body(self):
        """log_body is the human-readable audit-trail text for templates."""
        r = Reply.template(
            "HX_abc123",
            variables={"1": "Anita"},
            log_body="Hi Anita! How can we help today?",
        )
        assert r.log_body == "Hi Anita! How can we help today?"

    def test_is_template_true_for_template(self):
        r = Reply.template("HX_abc123")
        assert r.is_template is True


# ============================================================
# XOR invariant — exactly one of body / content_sid must be set
# ============================================================


class TestXORInvariant:
    """The dataclass __post_init__ raises ValueError if both fields are
    None or both are set. These cases shouldn't happen if you use the
    factory classmethods; the test guards against future refactors that
    might call the bare constructor."""

    def test_both_none_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            Reply()

    def test_both_set_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            Reply(body="hello", content_sid="HX_abc")

    def test_only_body_is_valid(self):
        # No exception
        r = Reply(body="hello")
        assert r.body == "hello"

    def test_only_content_sid_is_valid(self):
        # No exception
        r = Reply(content_sid="HX_abc")
        assert r.content_sid == "HX_abc"


# ============================================================
# Immutability — frozen=True on the dataclass
# ============================================================


class TestImmutability:
    """Reply is frozen so handlers can't mutate replies in flight (which
    would make audit logging unreliable). Verify the freeze works."""

    def test_frozen_body_cannot_be_reassigned(self):
        r = Reply.text("original")
        with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
            r.body = "mutated"  # type: ignore[misc]

    def test_frozen_content_sid_cannot_be_reassigned(self):
        r = Reply.template("HX_abc")
        with pytest.raises(Exception):
            r.content_sid = "HX_other"  # type: ignore[misc]
