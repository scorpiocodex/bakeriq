"""Tests for the Celery LLM tasks — Medium rigor.

We test the FUNCTION body of parse_and_send by calling the underlying
function directly (the @celery_app.task decorator preserves the
original — we access it via .run()). This skips the broker
entirely — we're not testing Celery itself, we're testing our
business logic.

We mock at two boundaries:
  - Ollama (external API)
  - Twilio outbound (external API + side-effects)

Everything else (matcher, handoff, cart write, DB log) runs for real
so we get coverage of the full integration without flakiness from
network calls.

Coverage:
  Branch selection (3): handoff message when matched, nothing-available
                        when only dropped, no-match when both empty
  Side effects (2): outbound is sent, cart lands in Redis on handoff
  Customer missing (1): graceful no-op if the customer was deleted

Total: 6 tests.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
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


def _mock_ollama_returning(json_content: str) -> MagicMock:
    """Build a mock Ollama client that returns the given JSON string."""
    mock_client = MagicMock()
    mock_client.chat.return_value = {"message": {"content": json_content}}
    return mock_client


# === BRANCH SELECTION ===
# The task picks one of three messages based on (matched, dropped):
#   matched>0          → handoff cart-summary message
#   matched=0, dropped>0 → "nothing available today" fallback
#   matched=0, dropped=0 → generic "didn't catch that" fallback


@patch("app.services.whatsapp_sender.send_text")
@patch("app.services.llm_parser_service.get_client")
def test_handoff_branch_when_matched(
    mock_get_client,
    mock_send_text,
    db_session,
    customer,
    conversation,
    stub_products,
):
    """Items matched → handoff message with cart summary."""
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

    # send_text was called with the handoff message text
    mock_send_text.assert_called_once()
    sent_body = mock_send_text.call_args.kwargs["body"]
    assert "Veg Puff × 2" in sent_body
    assert "Total:" in sent_body
    assert "Tap to review" in sent_body


@patch("app.services.whatsapp_sender.send_text")
@patch("app.services.llm_parser_service.get_client")
def test_nothing_available_branch_when_only_dropped(
    mock_get_client,
    mock_send_text,
    db_session,
    customer,
    conversation,
    stub_products,
):
    """LLM understood food intent but nothing matched → 'nothing available'."""
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

    mock_send_text.assert_called_once()
    assert mock_send_text.call_args.kwargs["body"] == MSG_NOTHING_AVAILABLE


@patch("app.services.whatsapp_sender.send_text")
@patch("app.services.llm_parser_service.get_client")
def test_no_match_branch_when_both_empty(
    mock_get_client,
    mock_send_text,
    db_session,
    customer,
    conversation,
    stub_products,
):
    """No order intent at all → generic fallback."""
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

    mock_send_text.assert_called_once()
    assert mock_send_text.call_args.kwargs["body"] == MSG_NO_MATCH


# === SIDE EFFECTS ===


@patch("app.services.whatsapp_sender.send_text")
@patch("app.services.llm_parser_service.get_client")
def test_send_to_phone_matches_arg(
    mock_get_client,
    mock_send_text,
    db_session,
    customer,
    conversation,
    stub_products,
):
    """The outbound message goes to the phone we passed in, not the
    customer's stored phone (which could differ if the inbound came
    from a secondary number)."""
    mock_get_client.return_value = _mock_ollama_returning('{"items": []}')

    parse_and_send.run(
        customer_id=str(customer.id),
        conversation_id=str(conversation.id),
        phone="+919999000000",  # different from customer.primary_phone
        body="hello",
    )

    mock_send_text.assert_called_once()
    assert mock_send_text.call_args.kwargs["to_phone"] == "+919999000000"


@patch("app.services.whatsapp_sender.send_text")
@patch("app.services.llm_parser_service.get_client")
def test_handoff_writes_cart_to_redis(
    mock_get_client,
    mock_send_text,
    db_session,
    customer,
    conversation,
    stub_products,
):
    """The handoff branch leaves a populated cart in Redis. We verify by
    parsing the outbound message to find the token (32-char trailing
    URL segment) and looking it up directly."""
    mock_get_client.return_value = _mock_ollama_returning(
        '{"items": [{"product_name": "Ladoo", "quantity": 3}]}'
    )

    parse_and_send.run(
        customer_id=str(customer.id),
        conversation_id=str(conversation.id),
        phone=PHONE,
        body="3 ladoo",
    )

    sent_body = mock_send_text.call_args.kwargs["body"]
    # Token is the last 32 chars after the final slash in the message
    token = sent_body.rsplit("/", 1)[-1].strip()
    assert len(token) == 32

    cart = cart_cache.get_cart(token)
    assert cart is not None
    assert cart["kind"] == "new"
    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 3


# === CUSTOMER MISSING ===


@patch("app.services.whatsapp_sender.send_text")
@patch("app.services.llm_parser_service.get_client")
def test_customer_not_found_returns_early(
    mock_get_client,
    mock_send_text,
    db_session,
    conversation,
):
    """Customer was deleted between webhook and worker pickup — the task
    logs and bails rather than crashing or sending a confusing reply."""
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
    mock_send_text.assert_not_called()
