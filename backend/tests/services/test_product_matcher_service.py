"""Tests for the product matcher service — Medium rigor.

These tests run against real Postgres (no mocking) because the matcher
is pure logic over the products table. Fast enough — each test is a
truncate + a tiny seed + a function call.

The fuzzy-match threshold (0.85) is calibrated in the production
module; here we verify behaviour at the boundaries so a future
threshold tweak doesn't silently break expectations.

Coverage:
  Exact + alias matching (3): exact name, case-insensitive, alias
  Fuzzy matching (2): typos + plurals match, garbage drops
  Edge cases (3): empty input, dedup with qty sum, drops vs matches
  Filtering (1): inactive/unavailable products are not matched

Total: 9 tests.
"""

from decimal import Decimal

import pytest
from app.models.category import Category
from app.models.product import Product
from app.services.product_matcher_service import (
    match_items,
)


@pytest.fixture
def stub_products(db_session):
    """Three products covering: aliases, no aliases, and a product
    we'll mark inactive in one test."""
    cat = Category(name="matcher_test_cat", display_order=99, is_active=True)
    db_session.add(cat)
    db_session.flush()

    veg_puff = Product(
        name="Veg Puff",
        category_id=cat.id,
        unit_price=Decimal("18.00"),
        unit_label="piece",
        aliases=["vegetable puff", "veg patty"],
        is_available_today=True,
        is_active=True,
    )
    chicken_puff = Product(
        name="Chicken Puff",
        category_id=cat.id,
        unit_price=Decimal("27.00"),
        unit_label="piece",
        aliases=None,
        is_available_today=True,
        is_active=True,
    )
    ladoo = Product(
        name="Ladoo",
        category_id=cat.id,
        unit_price=Decimal("20.00"),
        unit_label="piece",
        aliases=None,
        is_available_today=True,
        is_active=True,
    )
    db_session.add_all([veg_puff, chicken_puff, ladoo])
    db_session.commit()
    db_session.refresh(veg_puff)
    db_session.refresh(chicken_puff)
    db_session.refresh(ladoo)
    return {"veg_puff": veg_puff, "chicken_puff": chicken_puff, "ladoo": ladoo}


# === EXACT + ALIAS MATCHING ===


def test_match_exact_name(db_session, stub_products):
    """Canonical name as-is → matched via 'name' strategy."""
    items = [{"product_name": "Veg Puff", "quantity": 2}]
    matched, dropped = match_items(db_session, items)

    assert dropped == []
    assert len(matched) == 1
    assert matched[0].product_name == "Veg Puff"
    assert matched[0].quantity == 2
    assert matched[0].matched_via == "name"
    assert matched[0].product_id == stub_products["veg_puff"].id


def test_match_name_is_case_insensitive(db_session, stub_products):
    """Lowercase input still matches the canonical Capitalised name."""
    items = [{"product_name": "veg puff", "quantity": 1}]
    matched, dropped = match_items(db_session, items)

    assert dropped == []
    assert len(matched) == 1
    assert matched[0].matched_via == "name"


def test_match_via_alias(db_session, stub_products):
    """LLM uses an alias from the catalog — resolves via 'alias' strategy."""
    items = [{"product_name": "vegetable puff", "quantity": 3}]
    matched, dropped = match_items(db_session, items)

    assert dropped == []
    assert len(matched) == 1
    assert matched[0].product_name == "Veg Puff"
    assert matched[0].quantity == 3
    assert matched[0].matched_via == "alias"


# === FUZZY MATCHING ===


def test_match_via_fuzzy_handles_typos_and_plurals(db_session, stub_products):
    """Plurals + typos exceed the FUZZY_THRESHOLD and match correctly."""
    items = [
        {"product_name": "veg puffs", "quantity": 1},  # plural
        {"product_name": "chiken puff", "quantity": 2},  # typo
    ]
    matched, dropped = match_items(db_session, items)

    assert dropped == []
    assert len(matched) == 2

    by_name = {m.product_name: m for m in matched}
    assert "Veg Puff" in by_name
    assert "Chicken Puff" in by_name
    assert by_name["Veg Puff"].matched_via == "fuzzy"
    assert by_name["Chicken Puff"].matched_via == "fuzzy"


def test_match_drops_garbage_below_threshold(db_session, stub_products):
    """Truly unrelated input — way below 0.85 — is dropped, not matched."""
    items = [{"product_name": "XYZNONSENSE", "quantity": 1}]
    matched, dropped = match_items(db_session, items)

    assert matched == []
    assert dropped == ["XYZNONSENSE"]


# === EDGE CASES ===


def test_match_empty_input(db_session, stub_products):
    """Empty input → empty result. No exceptions."""
    matched, dropped = match_items(db_session, [])
    assert matched == []
    assert dropped == []


def test_match_dedups_and_sums_quantities(db_session, stub_products):
    """When the LLM names the same product twice (e.g. 'veg puff' and
    'veg puffs'), we sum quantities into one cart row, not two."""
    items = [
        {"product_name": "Veg Puff", "quantity": 2},
        {"product_name": "veg puffs", "quantity": 1},  # same product, plural
    ]
    matched, dropped = match_items(db_session, items)

    assert dropped == []
    assert len(matched) == 1
    assert matched[0].product_name == "Veg Puff"
    assert matched[0].quantity == 3  # 2 + 1


def test_match_mixed_matches_and_drops(db_session, stub_products):
    """A real LLM output usually has some matches and some drops."""
    items = [
        {"product_name": "Veg Puff", "quantity": 2},  # exact
        {"product_name": "samosa", "quantity": 1},  # off-menu
        {"product_name": "Ladoo", "quantity": 1},  # exact
    ]
    matched, dropped = match_items(db_session, items)

    assert dropped == ["samosa"]
    assert len(matched) == 2
    names = {m.product_name for m in matched}
    assert names == {"Veg Puff", "Ladoo"}


def test_match_skips_inactive_products(db_session, stub_products):
    """A product marked inactive is invisible to the matcher — even
    exact name matches fail."""
    stub_products["ladoo"].is_active = False
    db_session.commit()

    items = [{"product_name": "Ladoo", "quantity": 1}]
    matched, dropped = match_items(db_session, items)

    assert matched == []
    assert dropped == ["Ladoo"]
