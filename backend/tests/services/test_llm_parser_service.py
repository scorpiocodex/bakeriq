"""Tests for the LLM parser service — Medium rigor.

We mock the Ollama client because:
  - The model takes 3-5s per call, way too slow for a test suite
  - LLM output is non-deterministic; tests against a real model
    would be flaky
  - We want to test OUR handling (catalog injection, defensive
    normalisation), not Ollama's behaviour

The live smoke tests in Substep 2 verified the LLM works against
real catalogs. These tests verify the wrapper code around it.

Coverage:
  Catalog injection (2): products appear in prompt, aliases included
  Parse handling (4): happy path, defensive normalisation of garbage
                      shape, empty items handled, malformed items dropped

Total: 6 tests.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from app.models.category import Category
from app.models.product import Product
from app.services.llm_parser_service import (
    _build_system_prompt,
    _load_todays_catalog,
    parse_message,
)


@pytest.fixture
def stub_products(db_session):
    """A small catalog for prompt + parse tests."""
    cat = Category(name="parser_test_cat", display_order=99, is_active=True)
    db_session.add(cat)
    db_session.flush()

    p1 = Product(
        name="Veg Puff",
        category_id=cat.id,
        unit_price=Decimal("18.00"),
        unit_label="piece",
        aliases=["vegetable puff", "veg patty"],
        is_available_today=True,
        is_active=True,
    )
    p2 = Product(
        name="Ladoo",
        category_id=cat.id,
        unit_price=Decimal("20.00"),
        unit_label="piece",
        aliases=None,  # no aliases — exercises the None branch
        is_available_today=True,
        is_active=True,
    )
    db_session.add_all([p1, p2])
    db_session.commit()
    return [p1, p2]


# === CATALOG INJECTION ===


def test_build_system_prompt_includes_product_names(db_session, stub_products):
    """The LLM needs to see today's products. Names appear verbatim."""
    products = _load_todays_catalog(db_session)
    prompt = _build_system_prompt(products)
    assert "Veg Puff" in prompt
    assert "Ladoo" in prompt


def test_build_system_prompt_includes_aliases(db_session, stub_products):
    """When a product has aliases, the prompt shows them so the LLM
    can resolve customer language to the canonical name."""
    products = _load_todays_catalog(db_session)
    prompt = _build_system_prompt(products)
    assert "vegetable puff" in prompt
    assert "veg patty" in prompt


# === PARSE HANDLING ===
# We mock client.chat to return canned responses and verify our
# normalisation of the result.


def _mock_ollama_response(content: str) -> dict:
    """Build the dict shape ollama.Client.chat returns."""
    return {"message": {"content": content}}


@patch("app.services.llm_parser_service.get_client")
def test_parse_message_happy_path(mock_get_client, db_session, stub_products):
    """LLM returns well-formed JSON; parser passes it through."""
    mock_client = MagicMock()
    mock_client.chat.return_value = _mock_ollama_response(
        '{"items": [{"product_name": "Veg Puff", "quantity": 2}]}'
    )
    mock_get_client.return_value = mock_client

    result = parse_message(db_session, "2 veg puff")
    assert result == {"items": [{"product_name": "Veg Puff", "quantity": 2}]}


@patch("app.services.llm_parser_service.get_client")
def test_parse_message_drops_invalid_items(mock_get_client, db_session, stub_products):
    """Garbage shapes in individual items get dropped, valid ones kept.

    Schema enforcement should prevent this, but we don't rely on the
    SDK's invariant — defence in depth."""
    mock_client = MagicMock()
    mock_client.chat.return_value = _mock_ollama_response(
        '{"items": ['
        '  {"product_name": "Veg Puff", "quantity": 2},'
        '  {"product_name": "", "quantity": 1},'  # empty name
        '  {"product_name": "Ladoo", "quantity": 0},'  # zero qty
        '  {"product_name": "Ladoo", "quantity": -1},'  # negative qty
        '  {"product_name": null, "quantity": 1},'  # null name
        '  "not even a dict",'  # wrong type
        '  {"product_name": "Ladoo", "quantity": 3}'  # valid
        "]}"
    )
    mock_get_client.return_value = mock_client

    result = parse_message(db_session, "noisy input")
    # Only the two well-formed items survive
    assert result == {
        "items": [
            {"product_name": "Veg Puff", "quantity": 2},
            {"product_name": "Ladoo", "quantity": 3},
        ]
    }


@patch("app.services.llm_parser_service.get_client")
def test_parse_message_handles_empty_items(mock_get_client, db_session, stub_products):
    """Empty items list (greeting, no order intent) passes through."""
    mock_client = MagicMock()
    mock_client.chat.return_value = _mock_ollama_response('{"items": []}')
    mock_get_client.return_value = mock_client

    result = parse_message(db_session, "hi how are you")
    assert result == {"items": []}


@patch("app.services.llm_parser_service.get_client")
def test_parse_message_handles_wrong_top_level_shape(
    mock_get_client, db_session, stub_products
):
    """If the LLM returns valid JSON but the wrong top-level shape,
    we return an empty items list rather than raising."""
    mock_client = MagicMock()
    mock_client.chat.return_value = _mock_ollama_response("[1, 2, 3]")  # list, not dict
    mock_get_client.return_value = mock_client

    result = parse_message(db_session, "anything")
    assert result == {"items": []}
