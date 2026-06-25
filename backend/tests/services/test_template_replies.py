"""Tests for app.services.template_replies — Content Template Reply factories.

Three factories: cart_link_reply, nav_reply, fallback_reply. Each:
  - Returns a template Reply if the relevant CONTENT_SID_* is set
  - Falls back to a text Reply if the SID is None (bootstrap not run)
  - Includes a useful audit log_body when sending as a template

We monkeypatch settings to exercise both branches without touching .env.
Pure tests — no DB, no Twilio, no fixtures from conftest.
"""

import pytest
from app.core.config import settings
from app.services.template_replies import (
    cart_link_reply,
    fallback_reply,
    nav_reply,
)

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def all_sids_set(monkeypatch):
    """Force all CONTENT_SID_* to known test values regardless of .env.

    Lets us assert on exact SID values rather than 'whatever happens to
    be in env at test time', which would couple tests to environment
    state.
    """
    monkeypatch.setattr(settings, "CONTENT_SID_GREETING", "HX_test_greeting")
    monkeypatch.setattr(settings, "CONTENT_SID_NAV", "HX_test_nav")
    monkeypatch.setattr(settings, "CONTENT_SID_CART_LINK", "HX_test_cart_link")
    monkeypatch.setattr(settings, "CONTENT_SID_FALLBACK", "HX_test_fallback")


@pytest.fixture
def all_sids_none(monkeypatch):
    """Force all CONTENT_SID_* to None to exercise the text-fallback path.

    This simulates a freshly-cloned repo where bootstrap_content_templates.py
    hasn't been run yet — handlers should still produce sendable Replies,
    just text instead of templates.
    """
    monkeypatch.setattr(settings, "CONTENT_SID_GREETING", None)
    monkeypatch.setattr(settings, "CONTENT_SID_NAV", None)
    monkeypatch.setattr(settings, "CONTENT_SID_CART_LINK", None)
    monkeypatch.setattr(settings, "CONTENT_SID_FALLBACK", None)


# ============================================================
# cart_link_reply
# ============================================================


class TestCartLinkReply:
    """cart_link_reply substitutes {{1}} = token into the template's URL,
    or falls back to a plain-text message containing the full link plus
    a 30-minute-expiry note."""

    def test_returns_template_when_sid_set(self, all_sids_set):
        token = "tok_abc123xyz"
        link = "https://example.ngrok-free.dev/web/new/tok_abc123xyz"
        reply = cart_link_reply(token, link)

        assert reply.is_template is True
        assert reply.content_sid == "HX_test_cart_link"
        assert reply.content_variables == {"1": token}

    def test_template_log_body_includes_link(self, all_sids_set):
        """The audit log_body should include the full link so the admin
        transcript viewer renders something useful — not just the SID."""
        link = "https://example.ngrok-free.dev/web/new/tok_xyz"
        reply = cart_link_reply("tok_xyz", link)

        assert reply.log_body is not None
        assert link in reply.log_body

    def test_falls_back_to_text_when_sid_none(self, all_sids_none):
        link = "https://example.ngrok-free.dev/web/new/tok_xyz"
        reply = cart_link_reply("tok_xyz", link)

        assert reply.is_template is False
        assert reply.body is not None
        assert link in reply.body

    def test_text_fallback_includes_expiry_note(self, all_sids_none):
        """The 30-minute expiry was visible in the original text UX. It's
        lost when we move to the template (template body is static),
        but the fallback should preserve it for users who hit the
        unset-SID path."""
        reply = cart_link_reply("tok_xyz", "https://example.com/x")

        assert reply.body is not None
        assert "30 minutes" in reply.body


# ============================================================
# nav_reply
# ============================================================


class TestNavReply:
    """nav_reply is the mid-conversation prompt — Reorder/New/Status
    buttons. No variables to substitute."""

    def test_returns_template_when_sid_set(self, all_sids_set):
        reply = nav_reply()

        assert reply.is_template is True
        assert reply.content_sid == "HX_test_nav"
        # No variables on this template
        assert reply.content_variables is None

    def test_template_log_body_mentions_options(self, all_sids_set):
        """log_body should make it obvious what was offered to the
        customer when reviewing the audit trail."""
        reply = nav_reply()

        assert reply.log_body is not None
        # The exact wording can change; just check we reference at least
        # one of the button options so transcripts are readable.
        assert (
            "Reorder" in reply.log_body
            or "New" in reply.log_body
            or "status" in reply.log_body.lower()
        )

    def test_falls_back_to_text_when_sid_none(self, all_sids_none):
        reply = nav_reply()

        assert reply.is_template is False
        assert reply.body is not None
        # The fallback should hint at the available options as inline
        # keywords (e.g. "Reply *menu*, *new order*..."). Don't pin the
        # exact wording; assert the customer has at least one option
        # name visible.
        assert (
            "new order" in reply.body.lower()
            or "menu" in reply.body.lower()
            or "status" in reply.body.lower()
        )


# ============================================================
# fallback_reply
# ============================================================


class TestFallbackReply:
    """fallback_reply is used when the LLM understood an order intent
    but couldn't match any items. Unlike nav_reply, this template's
    primary button is Menu (so the customer can see what IS available)
    rather than Reorder."""

    def test_returns_template_when_sid_set(self, all_sids_set):
        reply = fallback_reply()

        assert reply.is_template is True
        assert reply.content_sid == "HX_test_fallback"
        assert reply.content_variables is None

    def test_distinct_sid_from_nav_reply(self, all_sids_set):
        """fallback_reply must use a different SID from nav_reply.

        These templates show different buttons (Menu/New/Status vs
        Reorder/New/Status); reusing one SID for both would silently
        send the wrong UX. This test catches a future refactor that
        unifies them by accident.
        """
        assert nav_reply().content_sid != fallback_reply().content_sid

    def test_falls_back_to_text_when_sid_none(self, all_sids_none):
        reply = fallback_reply()

        assert reply.is_template is False
        assert reply.body is not None


# ============================================================
# Mixed state (one SID set, others unset) — defensive
# ============================================================


class TestPartialSIDState:
    """In practice .env either has all four SIDs (bootstrap ran) or none
    (bootstrap pending). But a half-state could happen if a developer
    manually edits .env. Each factory should consult its own SID only,
    not assume the others are in any particular state."""

    def test_cart_link_template_when_only_cart_link_sid_set(self, monkeypatch):
        monkeypatch.setattr(settings, "CONTENT_SID_CART_LINK", "HX_only_cart")
        monkeypatch.setattr(settings, "CONTENT_SID_NAV", None)
        monkeypatch.setattr(settings, "CONTENT_SID_FALLBACK", None)

        reply = cart_link_reply("tok", "https://x.com/y")
        assert reply.is_template is True

        # The other factories fall back independently
        assert nav_reply().is_template is False
        assert fallback_reply().is_template is False

    def test_nav_template_when_only_nav_sid_set(self, monkeypatch):
        monkeypatch.setattr(settings, "CONTENT_SID_CART_LINK", None)
        monkeypatch.setattr(settings, "CONTENT_SID_NAV", "HX_only_nav")
        monkeypatch.setattr(settings, "CONTENT_SID_FALLBACK", None)

        reply = nav_reply()
        assert reply.is_template is True

        assert cart_link_reply("tok", "https://x.com").is_template is False
        assert fallback_reply().is_template is False
