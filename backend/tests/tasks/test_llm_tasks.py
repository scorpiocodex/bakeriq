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
    parse_and_send,
)

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
