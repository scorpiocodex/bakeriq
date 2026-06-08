"""Product matcher — resolves LLM-extracted product names to real
Product UUIDs.

The LLM gives us strings like "Veg Puff" (ideally exact-match the
catalog) or sometimes "veg puffs" or "vegpuff" (typos, casing,
plurals). This module takes that fuzzy input and decides which real
Product (by UUID) the customer meant. If we can't decide with
confidence, we drop the item — better to surface a fallback than to
order the wrong thing.

Matching strategy (in order, first hit wins):
  1. Exact case-insensitive name match. Covers the happy path where
     the LLM correctly used the canonical catalog name.
  2. Exact case-insensitive match against any alias. Catches
     "vegetable puff" → Veg Puff when aliases include it.
  3. Fuzzy match via difflib.SequenceMatcher with a confidence cutoff.
     Catches "veg puffs" (plural), "vegpuff" (typo), and other near-
     misses. The cutoff is conservative (0.85 ratio) — we'd rather
     drop an item than match a wrong one.

Why not Levenshtein / RapidFuzz / etc:
  - difflib is in the stdlib, no new dependencies.
  - At our catalog size (~10-50 products), the O(n) full scan is
    sub-millisecond. Fancier libraries would be overkill.
  - SequenceMatcher's ratio() handles substring + ordering effects
    that pure edit distance misses ("veg puffs" still ratios highly
    to "Veg Puff" because the common subsequence is large).

The matcher works on ACTIVE + AVAILABLE products only — same view of
the world that the menu and cart endpoints use. Inactive or hidden
products won't be matched even by exact name.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import Product

# Confidence threshold for fuzzy matching. SequenceMatcher.ratio()
# returns 0.0-1.0; 0.85 means strings must be ~85% similar.
#
# Calibration:
#   - "veg puff" vs "Veg Puff" lowercase → 1.0 (exact ci match, handled
#     by step 1 anyway)
#   - "veg puffs" vs "Veg Puff" → ~0.94 (plural — should match)
#   - "vegpuff" vs "Veg Puff" → ~0.87 (no space — should match)
#   - "chicken roll" vs "Veg Puff" → ~0.40 (different product — drop)
#
# Bias toward dropping > false-positive matching for an order system.
FUZZY_THRESHOLD = 0.85


@dataclass
class MatchedItem:
    """A successfully matched cart item — what the matcher produces
    for downstream cart-cache + token-issuance."""

    product_id: UUID
    product_name: str  # canonical name from the catalog
    quantity: int
    matched_via: str  # 'name' | 'alias' | 'fuzzy' — for logging


def _normalise(s: str) -> str:
    """Lowercase + strip + collapse whitespace. Applied to BOTH the
    input string and the catalog values before comparison."""
    return " ".join(s.lower().strip().split())


def _load_active_products(db: Session) -> list[Product]:
    """Today's available products. Same query as the menu/cart code."""
    return list(
        db.scalars(
            select(Product)
            .where(Product.is_active.is_(True))
            .where(Product.is_available_today.is_(True))
        )
    )


def _match_one(name: str, products: list[Product]) -> tuple[Product, str] | None:
    """Try to match a single LLM-output name to a Product.

    Returns (product, strategy) on hit, None on miss. strategy is one
    of 'name', 'alias', 'fuzzy' — purely for logging downstream.
    """
    needle = _normalise(name)

    # 1. Exact case-insensitive name match
    for p in products:
        if _normalise(p.name) == needle:
            return (p, "name")

    # 2. Exact case-insensitive alias match
    for p in products:
        aliases = p.aliases or []
        for alias in aliases:
            if _normalise(alias) == needle:
                return (p, "alias")

    # 3. Fuzzy match — score against name + aliases, take the best
    best_product: Product | None = None
    best_score = 0.0
    for p in products:
        candidates = [p.name] + list(p.aliases or [])
        for candidate in candidates:
            score = SequenceMatcher(None, needle, _normalise(candidate)).ratio()
            if score > best_score:
                best_score = score
                best_product = p

    if best_product is not None and best_score >= FUZZY_THRESHOLD:
        return (best_product, "fuzzy")

    return None


def match_items(
    db: Session,
    llm_items: list[dict],
) -> tuple[list[MatchedItem], list[str]]:
    """Resolve LLM-extracted items to real products.

    Args:
        llm_items: List of {"product_name": str, "quantity": int}
            from llm_parser_service.parse_message.

    Returns:
        (matched, dropped) where:
          - matched is the list of MatchedItem with UUIDs ready for
            cart insertion.
          - dropped is the list of product_name strings that couldn't
            be matched. Surfaced so callers can mention them to the
            customer ("Sorry, we don't have X today").

    Items with quantity <= 0 are silently dropped before matching.
    Duplicates in the LLM output (same product mentioned twice) get
    their quantities summed, not duplicated as separate cart rows.
    """
    products = _load_active_products(db)

    matched: dict[UUID, MatchedItem] = {}  # dedup by product_id
    dropped: list[str] = []

    for entry in llm_items:
        name = entry.get("product_name", "")
        qty = entry.get("quantity", 0)
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(qty, int)
            or qty <= 0
        ):
            continue

        result = _match_one(name, products)
        if result is None:
            dropped.append(name)
            continue

        product, via = result
        if product.id in matched:
            # Customer said the same thing twice (e.g., "2 veg puff and
            # 1 more veg puff") — sum quantities rather than overwrite.
            matched[product.id].quantity += qty
        else:
            matched[product.id] = MatchedItem(
                product_id=product.id,
                product_name=product.name,
                quantity=qty,
                matched_via=via,
            )

    return list(matched.values()), dropped
