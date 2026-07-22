"""Tests for the Celery LLM tasks.

We test the FUNCTION body of parse_and_send by calling it directly via
.run() — the @celery_app.task decorator preserves the underlying
function. This skips the broker entirely; we test our business logic,
not Celery.

Mocks at two external boundaries:
  - Ollama (parse step)
  - Twilio (outbound send — patched at the task's import boundary)

Everything else (matcher, handoff service, cart write to Redis, DB
session) runs for real, giving us full integration coverage without
network flakiness.

Coverage (post Substep 5 — list[Reply] shape):
  Branch selection (3): handoff Reply pair when matched; nothing-available
                        Reply pair when only dropped; no-match Reply pair
                        when both empty.
  Reply structure (2): handoff produces text + cart_link_template;
                       no-match/nothing-available produce text + nav/fallback
                       templates.
  Side effects (2): outbound is sent to the correct phone; matched
                    branch leaves a populated cart in Redis.
  Customer missing (1): graceful no-op if the customer was deleted between
                        webhook and worker pickup.

Total: 8 tests.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest
from app.core.config import settings
from app.models.category import Category
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.product import Product
from app.services import cart_cache
from app.tasks.llm import (
    MSG_NO_MATCH,
    MSG_NOTHING_AVAILABLE,
    MSG_SERVICE_DEGRADED,
    RETRY_EXCEPTIONS,
    parse_and_send,
)
from ollama import RequestError, ResponseError

PHONE = "+919888777555"


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def customer(db_session):
    c = Customer(
        name="Task Tester",
        primary_phone=PHONE,
        whatsapp_enabled=True,
        is_active=True,
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def conversation(db_session, customer):
    conv = Conversation(
        customer_id=customer.id,
        phone=customer.primary_phone,
    )
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    return conv


@pytest.fixture
def stub_products(db_session):
    cat = Category(name="task_test_cat", display_order=99, is_active=True)
    db_session.add(cat)
    db_session.flush()

    veg_puff = Product(
        name="Veg Puff",
        category_id=cat.id,
        unit_price=Decimal("18.00"),
        unit_label="piece",
        is_available_today=True,
        is_active=True,
    )
    ladoo = Product(
        name="Ladoo",
        category_id=cat.id,
        unit_price=Decimal("20.00"),
        unit_label="piece",
        is_available_today=True,
        is_active=True,
    )
    db_session.add_all([veg_puff, ladoo])
    db_session.commit()
    db_session.refresh(veg_puff)
    db_session.refresh(ladoo)
    return {"veg_puff": veg_puff, "ladoo": ladoo}


@pytest.fixture(autouse=True)
def _clear_redis_between_tests():
    from app.core.redis_client import get_redis

    r = get_redis()
    for key in r.scan_iter("cart:*"):
        r.delete(key)
    yield
    for key in r.scan_iter("cart:*"):
        r.delete(key)


@pytest.fixture(autouse=True)
def _redirect_task_session_to_test_db(monkeypatch):
    """The Celery task opens its own SessionLocal() — separate from the
    test's db_session fixture. By default that hits the main dev DB,
    which doesn't see test-fixture data. Point it at TestSessionLocal
    so the worker reads what the test wrote.

    monkeypatch reverts the change after each test, so the live app
    code is unaffected.
    """
    from tests.conftest import TestSessionLocal

    monkeypatch.setattr("app.tasks.llm.SessionLocal", TestSessionLocal)


# ============================================================
# Helpers
# ============================================================


def _mock_ollama_returning(json_content: str) -> MagicMock:
    """Build a mock Ollama client that returns the given JSON string."""
    mock_client = MagicMock()
    mock_client.chat.return_value = {"message": {"content": json_content}}
    return mock_client


def _get_sent_replies(mock_send_replies: MagicMock) -> list:
    """Extract the `replies` kwarg from the (single) send_replies call."""
    mock_send_replies.assert_called_once()
    return mock_send_replies.call_args.kwargs["replies"]


def _get_sent_phone(mock_send_replies: MagicMock) -> str:
    """Extract the `to_phone` kwarg from the (single) send_replies call."""
    return mock_send_replies.call_args.kwargs["to_phone"]


# ============================================================
# Branch selection — verifies which Reply shape each outcome produces
# ============================================================


@patch("app.tasks.llm.whatsapp_sender.send_replies")
@patch("app.services.llm_parser_service.get_client")
def test_handoff_branch_when_matched(
    mock_get_client,
    mock_send_replies,
    db_session,
    customer,
    conversation,
    stub_products,
):
    """Items matched → [parse_confirmation_text, cart_link_template]."""
    mock_get_client.return_value = _mock_ollama_returning(
        '{"items": [{"product_name": "Veg Puff", "quantity": 2}]}'
    )
    mock_send_replies.return_value = ["SM_text", "SM_template"]

    result = parse_and_send.run(
        customer_id=str(customer.id),
        conversation_id=str(conversation.id),
        phone=PHONE,
        body="2 veg puff please",
    )

    assert result["status"] == "sent"
    assert result["outcome"] == "handoff"
    assert result["matched"] == 1
    assert result["dropped"] == 0

    replies = _get_sent_replies(mock_send_replies)
    assert len(replies) == 2

    # First reply: parse confirmation prose (text Reply, no SID)
    text_reply = replies[0]
    assert text_reply.content_sid is None
    assert text_reply.body is not None
    assert "Veg Puff" in text_reply.body
    assert "× 2" in text_reply.body
    assert "Total:" in text_reply.body
    # Crucially: no cart-link prose. That moved into the template.
    assert "Tap to review" not in text_reply.body

    # Second reply: cart-link Content Template with token in variables["1"]
    template_reply = replies[1]
    assert template_reply.content_sid == settings.CONTENT_SID_CART_LINK
    assert template_reply.content_variables is not None
    assert "1" in template_reply.content_variables


@patch("app.tasks.llm.whatsapp_sender.send_replies")
@patch("app.services.llm_parser_service.get_client")
def test_nothing_available_branch_when_only_dropped(
    mock_get_client,
    mock_send_replies,
    db_session,
    customer,
    conversation,
    stub_products,
):
    """LLM understood food intent but nothing matched →
    [MSG_NOTHING_AVAILABLE_text, fallback_template] (Menu button)."""
    mock_get_client.return_value = _mock_ollama_returning(
        '{"items": [{"product_name": "Tiramisu", "quantity": 1}]}'
    )
    mock_send_replies.return_value = ["SM_text", "SM_template"]

    result = parse_and_send.run(
        customer_id=str(customer.id),
        conversation_id=str(conversation.id),
        phone=PHONE,
        body="1 tiramisu",
    )

    assert result["outcome"] == "nothing_available"
    assert result["matched"] == 0
    assert result["dropped"] == 1

    replies = _get_sent_replies(mock_send_replies)
    assert len(replies) == 2

    text_reply = replies[0]
    assert text_reply.body == MSG_NOTHING_AVAILABLE

    # fallback_reply uses CONTENT_SID_FALLBACK (Menu / New / Status buttons)
    template_reply = replies[1]
    assert template_reply.content_sid == settings.CONTENT_SID_FALLBACK


@patch("app.tasks.llm.whatsapp_sender.send_replies")
@patch("app.services.llm_parser_service.get_client")
def test_no_match_branch_when_both_empty(
    mock_get_client,
    mock_send_replies,
    db_session,
    customer,
    conversation,
    stub_products,
):
    """No order intent at all → [MSG_NO_MATCH_text, nav_template]."""
    mock_get_client.return_value = _mock_ollama_returning('{"items": []}')
    mock_send_replies.return_value = ["SM_text", "SM_template"]

    result = parse_and_send.run(
        customer_id=str(customer.id),
        conversation_id=str(conversation.id),
        phone=PHONE,
        body="how are you doing today",
    )

    assert result["outcome"] == "no_match"
    assert result["matched"] == 0
    assert result["dropped"] == 0

    replies = _get_sent_replies(mock_send_replies)
    assert len(replies) == 2

    text_reply = replies[0]
    assert text_reply.body == MSG_NO_MATCH

    # nav_reply uses CONTENT_SID_NAV (Reorder / New / Status buttons)
    template_reply = replies[1]
    assert template_reply.content_sid == settings.CONTENT_SID_NAV


# ============================================================
# Side effects
# ============================================================


@patch("app.tasks.llm.whatsapp_sender.send_replies")
@patch("app.services.llm_parser_service.get_client")
def test_send_to_phone_matches_arg(
    mock_get_client,
    mock_send_replies,
    db_session,
    customer,
    conversation,
    stub_products,
):
    """Outbound goes to the `phone` arg, not customer.primary_phone (which
    could differ if the inbound came from a secondary number)."""
    mock_get_client.return_value = _mock_ollama_returning('{"items": []}')
    mock_send_replies.return_value = ["SM_text", "SM_template"]

    parse_and_send.run(
        customer_id=str(customer.id),
        conversation_id=str(conversation.id),
        phone="+919999000000",  # different from customer.primary_phone
        body="hello",
    )

    assert _get_sent_phone(mock_send_replies) == "+919999000000"


@patch("app.tasks.llm.whatsapp_sender.send_replies")
@patch("app.services.llm_parser_service.get_client")
def test_handoff_writes_cart_to_redis(
    mock_get_client,
    mock_send_replies,
    db_session,
    customer,
    conversation,
    stub_products,
):
    """Handoff branch leaves a populated cart in Redis.

    We pull the token directly from the cart-link Reply's
    content_variables — the URL no longer appears in prose since the
    template carries it.
    """
    mock_get_client.return_value = _mock_ollama_returning(
        '{"items": [{"product_name": "Ladoo", "quantity": 3}]}'
    )
    mock_send_replies.return_value = ["SM_text", "SM_template"]

    parse_and_send.run(
        customer_id=str(customer.id),
        conversation_id=str(conversation.id),
        phone=PHONE,
        body="3 ladoo",
    )

    replies = _get_sent_replies(mock_send_replies)
    template_reply = replies[1]
    assert template_reply.content_variables is not None
    token = template_reply.content_variables["1"]
    # Tokens are URL-safe random strings (web_link_service uses secrets.token_urlsafe)
    assert isinstance(token, str)
    assert len(token) > 8

    cart = cart_cache.get_cart(token)
    assert cart is not None
    assert cart["kind"] == "new"
    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 3


# ============================================================
# Customer missing
# ============================================================


@patch("app.tasks.llm.whatsapp_sender.send_replies")
@patch("app.services.llm_parser_service.get_client")
def test_customer_not_found_returns_early(
    mock_get_client,
    mock_send_replies,
    db_session,
    conversation,
):
    """Customer deleted between webhook and worker pickup — task logs
    and bails rather than crashing or sending a confusing reply."""
    fake_customer_id = "00000000-0000-0000-0000-000000000000"

    result = parse_and_send.run(
        customer_id=fake_customer_id,
        conversation_id=str(conversation.id),
        phone=PHONE,
        body="2 veg puff",
    )

    assert result == {"status": "customer_not_found"}
    # LLM not called, no outbound attempted
    mock_get_client.assert_not_called()
    mock_send_replies.assert_not_called()


class TestRetryConfig:
    """Static checks on the @celery_app.task decoration. These guard
    against narrowing the retry tuple inadvertently — a single PR
    could re-introduce silent message loss otherwise."""

    def test_retry_tuple_includes_ollama_exceptions(self):
        """The two ollama-SDK exception classes must trigger autoretry."""
        assert ResponseError in RETRY_EXCEPTIONS
        assert RequestError in RETRY_EXCEPTIONS

    def test_retry_tuple_includes_httpx_connection_errors(self):
        """The three httpx exceptions we observed in production logs
        (Ollama down, slow cold-load, container-firewall blocking)
        must trigger autoretry."""

        from app.tasks.llm import RETRY_EXCEPTIONS

        assert httpx.ConnectError in RETRY_EXCEPTIONS
        assert httpx.ConnectTimeout in RETRY_EXCEPTIONS
        assert httpx.ReadTimeout in RETRY_EXCEPTIONS

    def test_parse_and_send_decorator_uses_retry_tuple(self):
        """The decorated task should expose autoretry_for as a
        superset of RETRY_EXCEPTIONS — Celery may wrap or extend it,
        but our classes must all be present."""
        from app.tasks.llm import RETRY_EXCEPTIONS, parse_and_send

        # Celery stores this as a tuple of classes on the task object.
        decorated = set(parse_and_send.autoretry_for)
        expected = set(RETRY_EXCEPTIONS)
        assert expected.issubset(decorated), (
            f"parse_and_send.autoretry_for is missing exception classes: "
            f"{expected - decorated}"
        )

    def test_parse_and_send_has_max_retries_set(self):
        """Explicit max_retries — defends against the Celery default
        silently changing across upgrades, and documents intent."""
        from app.tasks.llm import parse_and_send

        # max_retries lives on the task class, not the function
        assert parse_and_send.max_retries == 3


# ============================================================
# Honest send-status reporting (the logging-bug fix)
# ============================================================


class TestSendStatusReporting:
    """The result dict's status field should reflect what actually
    reached Twilio, not just whether the pipeline completed. Old
    behavior: always status=sent even when both Twilio calls returned
    None. New behavior: classify based on the send_replies result."""

    def test_classifier_all_sent(self):
        from app.tasks.llm import _classify_send_results

        assert _classify_send_results(["SM1", "SM2"]) == "sent"

    def test_classifier_all_failed(self):
        from app.tasks.llm import _classify_send_results

        assert _classify_send_results([None, None]) == "all_sends_failed"

    def test_classifier_partial_failure(self):
        from app.tasks.llm import _classify_send_results

        assert _classify_send_results(["SM1", None]) == "partial_send_failure"
        assert _classify_send_results([None, "SM2"]) == "partial_send_failure"

    def test_classifier_empty_list(self):
        """Defensive: an empty list should NOT report 'sent' just
        because vacuously-all-sids-are-not-None is True."""
        from app.tasks.llm import _classify_send_results

        assert _classify_send_results([]) == "all_sends_failed"

    @patch("app.tasks.llm.whatsapp_sender.send_replies")
    @patch("app.services.llm_parser_service.get_client")
    def test_all_sends_failed_reports_honestly(
        self,
        mock_get_client,
        mock_send_replies,
        db_session,
        customer,
        conversation,
        stub_products,
    ):
        """Twilio rejected both messages (e.g. quota exhausted) → the
        result dict must say so, not claim 'sent'."""
        mock_get_client.return_value = _mock_ollama_returning('{"items": []}')
        mock_send_replies.return_value = [None, None]

        result = parse_and_send.run(
            customer_id=str(customer.id),
            conversation_id=str(conversation.id),
            phone=PHONE,
            body="hello",
        )

        assert result["status"] == "all_sends_failed"
        assert result["outcome"] == "no_match"
        assert result["sids"] == [None, None]

    @patch("app.tasks.llm.whatsapp_sender.send_replies")
    @patch("app.services.llm_parser_service.get_client")
    def test_partial_send_failure_reports_honestly(
        self,
        mock_get_client,
        mock_send_replies,
        db_session,
        customer,
        conversation,
        stub_products,
    ):
        """First message sent, second failed → partial_send_failure."""
        mock_get_client.return_value = _mock_ollama_returning('{"items": []}')
        mock_send_replies.return_value = ["SM_first_succeeded", None]

        result = parse_and_send.run(
            customer_id=str(customer.id),
            conversation_id=str(conversation.id),
            phone=PHONE,
            body="hello",
        )

        assert result["status"] == "partial_send_failure"
        assert result["sids"] == ["SM_first_succeeded", None]

    @patch("app.tasks.llm.whatsapp_sender.send_replies")
    @patch("app.services.llm_parser_service.get_client")
    def test_successful_send_still_reports_sent(
        self,
        mock_get_client,
        mock_send_replies,
        db_session,
        customer,
        conversation,
        stub_products,
    ):
        """Regression check — the existing happy path still works."""
        mock_get_client.return_value = _mock_ollama_returning(
            '{"items": [{"product_name": "Veg Puff", "quantity": 2}]}'
        )
        mock_send_replies.return_value = ["SM_text", "SM_template"]

        result = parse_and_send.run(
            customer_id=str(customer.id),
            conversation_id=str(conversation.id),
            phone=PHONE,
            body="2 veg puff",
        )

        assert result["status"] == "sent"
        assert result["outcome"] == "handoff"


# ============================================================
# Retry-exhaustion fallback (MSG_SERVICE_DEGRADED path)
# ============================================================


class TestRetryExhaustedFallback:
    """When retries are exhausted (MaxRetriesExceededError surfaces
    from the autoretry layer), the task fires MSG_SERVICE_DEGRADED so
    the customer is informed rather than stuck in silence."""

    @patch("app.tasks.llm.whatsapp_sender.send_replies")
    @patch("app.tasks.llm.parse_message")
    def test_retry_exhausted_fires_service_degraded(
        self,
        mock_parse_message,
        mock_send_replies,
        db_session,
        customer,
        conversation,
    ):
        """Simulate retry exhaustion by raising MaxRetriesExceededError
        from the parse step. The task should catch it and send
        MSG_SERVICE_DEGRADED + nav_reply."""
        from celery.exceptions import MaxRetriesExceededError

        mock_parse_message.side_effect = MaxRetriesExceededError()
        mock_send_replies.return_value = ["SM_degraded", "SM_nav"]

        result = parse_and_send.run(
            customer_id=str(customer.id),
            conversation_id=str(conversation.id),
            phone=PHONE,
            body="i want 2 veg puff",
        )

        assert result["status"] == "fallback_after_retry_exhausted"
        assert result["outcome"] == "service_degraded"

        # The fallback path uses its own DB session — verify it called
        # send_replies once with MSG_SERVICE_DEGRADED.
        mock_send_replies.assert_called_once()
        sent_replies = mock_send_replies.call_args.kwargs["replies"]
        assert len(sent_replies) == 2
        assert sent_replies[0].body == MSG_SERVICE_DEGRADED
        # Second reply is the nav template — assert it carries the
        # right CONTENT_SID rather than relying on text fallback.
        from app.core.config import settings

        assert sent_replies[1].content_sid == settings.CONTENT_SID_NAV

    @patch("app.tasks.llm.whatsapp_sender.send_replies")
    @patch("app.tasks.llm.parse_message")
    def test_retry_exhausted_with_twilio_also_failing(
        self,
        mock_parse_message,
        mock_send_replies,
        db_session,
        customer,
        conversation,
    ):
        """Worst case: retries exhausted AND the fallback Twilio call
        also fails. We can't reach the customer at all; the task must
        report this honestly (status=fallback_send_failed) so the
        monitoring layer can alert."""
        from celery.exceptions import MaxRetriesExceededError

        mock_parse_message.side_effect = MaxRetriesExceededError()
        mock_send_replies.return_value = [None, None]

        result = parse_and_send.run(
            customer_id=str(customer.id),
            conversation_id=str(conversation.id),
            phone=PHONE,
            body="i want 2 veg puff",
        )

        assert result["status"] == "fallback_send_failed"
        assert result["outcome"] == "service_degraded"
