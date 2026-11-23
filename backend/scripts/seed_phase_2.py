"""Seed Phase 2 fixtures — admin user, customers, categories, products.

Run as: python -m scripts.seed_phase_2
(from inside the api container, with /app as cwd)

What this seeds:
  - 1 admin user: owner@bakeriq.com / bakeriqowner
  - 8 customer fixtures with full Indian-postal-format addresses
  - 5 categories (savoury, sweet, cake, bread, other)
  - 8 product fixtures referencing categories

Idempotency:
  - Admin user: skipped if email already exists (so re-running this is safe)
  - Customers, categories, products: NOT individually deduplicated. The
    bash callers (reset-db.sh, seed.sh) clear these tables before running
    this script.

Why this script and not Alembic migrations:
We're using the "fixtures stay out of the migration chain" pattern. Production
deploys run alembic upgrade head and never run this script. Dev runs both
via `make reset-db`.
"""

from __future__ import annotations

import sys
from decimal import Decimal

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.category import Category
from app.models.customer import Customer, PreferredPhone
from app.models.default_order import DefaultOrder, DefaultOrderItem
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product
from app.models.user import User

# === Admin user fixture ======================================================
ADMIN_USER_FIXTURE = {
    "email": "owner@bakeriq.com",
    "full_name": "Bakery Owner",
    "password": "bakeriqowner",  # plaintext; hashed before insert
    "is_active": True,
    "is_superuser": True,
}


# === Customer fixtures =======================================================
CUSTOMER_FIXTURES = [
    {
        "name": "Anita Menon",
        "primary_phone": "+919999912345",
        "secondary_phone": "+919988800001",
        "preferred_channel_phone": PreferredPhone.PRIMARY,
        "whatsapp_enabled": True,
        "address_line_1": "TC 14/789, Pattom Palace Road",
        "address_line_2": "Near Pattom Junction",
        "city": "Thiruvananthapuram",
        "state": "Kerala",
        "pincode": "695004",
        "notes": "Daily customer, prefers extra crispy puffs",
    },
    {
        "name": "Ravi Sankar",
        "primary_phone": "+919999923456",
        "secondary_phone": None,
        "preferred_channel_phone": PreferredPhone.PRIMARY,
        "whatsapp_enabled": True,
        "address_line_1": "Sankar's Café, Kowdiar Road",
        "address_line_2": "Kowdiar P.O.",
        "city": "Thiruvananthapuram",
        "state": "Kerala",
        "pincode": "695003",
        "notes": "Office orders, large quantities on Fridays",
    },
    {
        "name": "Lakshmi Amma",
        "primary_phone": "+919944034567",
        "secondary_phone": "+919988800002",
        "preferred_channel_phone": PreferredPhone.SECONDARY,
        "whatsapp_enabled": False,
        "address_line_1": "Krishna Nivas, Vellayambalam",
        "address_line_2": "Vellayambalam P.O.",
        "city": "Thiruvananthapuram",
        "state": "Kerala",
        "pincode": "695010",
        "notes": "Voice only — primary is daughter's number; prefers calls to secondary",
    },
    {
        "name": "Suresh Kumar",
        "primary_phone": "+919999945678",
        "secondary_phone": None,
        "preferred_channel_phone": PreferredPhone.PRIMARY,
        "whatsapp_enabled": True,
        "address_line_1": "32/B, Pettah Main Road",
        "address_line_2": "Near Pettah Bus Station",
        "city": "Thiruvananthapuram",
        "state": "Kerala",
        "pincode": "695024",
        "notes": "Sometimes slow to reply on WhatsApp — give him 30 min before fallback",
    },
    {
        "name": "Priya Raghavan",
        "primary_phone": "+919999956789",
        "secondary_phone": "+919988800003",
        "preferred_channel_phone": PreferredPhone.PRIMARY,
        "whatsapp_enabled": True,
        "address_line_1": "Raghavan Manor, Kazhakkoottam",
        "address_line_2": "Technopark Phase II Road",
        "city": "Thiruvananthapuram",
        "state": "Kerala",
        "pincode": "695582",
        "notes": "Wedding-catering customer, occasional bulk orders (50+ units)",
    },
    {
        "name": "Mohan Vasudev",
        "primary_phone": "+919944067890",
        "secondary_phone": None,
        "preferred_channel_phone": PreferredPhone.PRIMARY,
        "whatsapp_enabled": False,
        "address_line_1": "Vasudev Bhavan, Sasthamangalam",
        "address_line_2": "Near Sasthamangalam Temple",
        "city": "Thiruvananthapuram",
        "state": "Kerala",
        "pincode": "695010",
        "notes": "Voice only, calls daily at 6:15 AM sharp",
    },
    {
        "name": "Deepa Krishnan",
        "primary_phone": "+919999978901",
        "secondary_phone": None,
        "preferred_channel_phone": PreferredPhone.PRIMARY,
        "whatsapp_enabled": True,
        "address_line_1": "Sea View Apartments, Flat 4B",
        "address_line_2": "Marine Drive, Ernakulam South",
        "city": "Kochi",
        "state": "Kerala",
        "pincode": "682011",
        "notes": "Skips Mondays — takes weekly off",
    },
    {
        "name": "Arjun Mathew",
        "primary_phone": "+919999989012",
        "secondary_phone": "+919988800004",
        "preferred_channel_phone": PreferredPhone.PRIMARY,
        "whatsapp_enabled": True,
        "address_line_1": "Mathew Towers, 3rd Floor",
        "address_line_2": "MG Road, near High Court",
        "city": "Kollam",
        "state": "Kerala",
        "pincode": "691001",
        "notes": "Office building order, ~25 puffs daily for breakfast",
    },
]

# === Order fixtures ==========================================================
# Sample orders spanning statuses and a couple of days. Referenced by
# customer + product name; snapshotted at seed time. day_offset is relative
# to today (0 = today, -1 = yesterday).
ORDER_FIXTURES = [
    {
        "_customer": "Anita Menon",
        "status": OrderStatus.delivering,
        "day_offset": 0,
        "notes": "Morning regular",
        "items": [
            {"_product": "Veg Puff", "quantity": 3},
            {"_product": "Ladoo", "quantity": 2},
        ],
    },
    {
        "_customer": "Arjun Mathew",
        "status": OrderStatus.ready,
        "day_offset": 0,
        "notes": "Office order",
        "items": [
            {"_product": "Egg Puff", "quantity": 25},
        ],
    },
    {
        "_customer": "Priya Raghavan",
        "status": OrderStatus.preparing,
        "day_offset": 0,
        "notes": None,
        "items": [
            {"_product": "Black Forest Cake (1kg)", "quantity": 1},
            {"_product": "Chicken Puff", "quantity": 6},
        ],
    },
    {
        "_customer": "Anita Menon",
        "status": OrderStatus.received,
        "day_offset": 0,
        "notes": "Add extra napkins",
        "items": [
            {"_product": "Bread", "quantity": 2},
        ],
    },
    {
        "_customer": "Ravi Sankar",
        "status": OrderStatus.delivering,
        "day_offset": -1,
        "notes": "Yesterday's delivery",
        "items": [
            {"_product": "Veg Puff", "quantity": 10},
            {"_product": "Sweet Porotta", "quantity": 4},
        ],
    },
    {
        "_customer": "Priya Raghavan",
        "status": OrderStatus.cancelled,
        "day_offset": -1,
        "notes": "Customer cancelled — out of town",
        "items": [
            {"_product": "Black Forest Cake (1/2kg)", "quantity": 1},
        ],
    },
]

# === Category fixtures =======================================================
# Five canonical categories. display_order controls sort sequence in the
# dropdown. Owner can add/rename/reorder later via the categories UI.

CATEGORY_FIXTURES = [
    {"name": "savoury", "display_order": 10},
    {"name": "sweet", "display_order": 20},
    {"name": "cake", "display_order": 30},
    {"name": "bread", "display_order": 40},
    {"name": "other", "display_order": 99},
]


# === Product fixtures =======================================================
# Reference categories by name (we resolve to id at insert time). Prices
# are realistic for a Kerala bakery, sourced loosely from the Baker's
# Association price list. Owner can edit any of these via the products UI.
#
# Each fixture references a `_category` key (consumed at insert time, not
# stored on the model). At insert, we resolve `_category` to the category's
# UUID via name lookup.

PRODUCT_FIXTURES = [
    {
        "name": "Veg Puff",
        "_category": "savoury",
        "unit_price": Decimal("18.00"),
        "unit_label": "piece",
        "is_available_today": True,
        "aliases": ["puff", "puffs", "veg puff", "vegetable puff"],
        "description": "Crispy savoury pastry with vegetable filling",
    },
    {
        "name": "Egg Puff",
        "_category": "savoury",
        "unit_price": Decimal("21.00"),
        "unit_label": "piece",
        "is_available_today": True,
        "aliases": ["egg puff", "egg puffs"],
        "description": "Pastry with seasoned egg filling",
    },
    {
        "name": "Chicken Puff",
        "_category": "savoury",
        "unit_price": Decimal("27.00"),
        "unit_label": "piece",
        "is_available_today": True,
        "aliases": ["chicken puff", "chicken puffs"],
        "description": "Pastry with spiced chicken filling",
    },
    {
        "name": "Ladoo",
        "_category": "sweet",
        "unit_price": Decimal("15.00"),
        "unit_label": "piece",
        "is_available_today": True,
        "aliases": ["ladoo", "ladoos", "laddu", "laddoo"],
        "description": "Round besan-based sweet",
    },
    {
        "name": "Black Forest Cake (1kg)",
        "_category": "cake",
        "unit_price": Decimal("580.00"),
        "unit_label": "kg",
        "is_available_today": True,
        "aliases": ["black forest", "bf cake", "black forest cake"],
        "description": "Chocolate sponge with cherry and cream layers",
    },
    {
        "name": "Black Forest Cake (1/2kg)",
        "_category": "cake",
        "unit_price": Decimal("320.00"),
        "unit_label": "half_kg",
        "is_available_today": True,
        "aliases": ["black forest half kg", "bf cake half"],
        "description": "Chocolate sponge with cherry and cream layers, half-kg variant",
    },
    {
        "name": "Bread",
        "_category": "bread",
        "unit_price": Decimal("48.00"),
        "unit_label": "loaf",
        "is_available_today": True,
        "aliases": ["bread", "loaf", "white bread"],
        "description": "Standard white sliced bread loaf",
    },
    {
        "name": "Sweet Porotta",
        "_category": "other",
        "unit_price": Decimal("18.00"),
        "unit_label": "piece",
        "is_available_today": False,
        "aliases": ["sweet porotta", "sweet parotta"],
        "description": "Sweet flaky flatbread — only made on weekends",
    },
]


# === Default order fixtures ==================================================
# Two customers get recurring templates. Referenced by customer name +
# product name; resolved to IDs at insert time (fixtures don't hardcode UUIDs).
#
# Anita: a daily breakfast regular — puffs + a sweet
# Arjun: the office order — bulk puffs
DEFAULT_ORDER_FIXTURES = [
    {
        "_customer": "Anita Menon",
        "notes": "Morning regular — usually before 8 AM",
        "is_active": True,
        "items": [
            {"_product": "Veg Puff", "quantity": 3},
            {"_product": "Ladoo", "quantity": 2},
        ],
    },
    {
        "_customer": "Arjun Mathew",
        "notes": "Office breakfast order, weekdays",
        "is_active": True,
        "items": [
            {"_product": "Egg Puff", "quantity": 25},
        ],
    },
]


def _seed_admin_user(db) -> None:
    """Insert the admin user. Skipped if a user with this email already exists."""
    existing = db.query(User).filter(User.email == ADMIN_USER_FIXTURE["email"]).first()
    if existing is not None:
        return

    fixture = ADMIN_USER_FIXTURE.copy()
    plaintext_password = fixture.pop("password")
    user = User(
        password_hash=get_password_hash(plaintext_password),
        **fixture,
    )
    db.add(user)


def _seed_customers(db) -> None:
    """Insert all 8 customer fixtures."""
    for fixture in CUSTOMER_FIXTURES:
        customer = Customer(**fixture)
        db.add(customer)


def _seed_categories(db) -> dict[str, Category]:
    """Insert all 5 categories. Returns a dict {name: Category} for product lookup."""
    categories_by_name = {}
    for fixture in CATEGORY_FIXTURES:
        category = Category(**fixture)
        db.add(category)
        categories_by_name[fixture["name"]] = category
    db.flush()  # Force INSERT so categories get UUIDs we can reference below
    return categories_by_name


def _seed_products(db, categories_by_name: dict[str, Category]) -> None:
    """Insert all 8 product fixtures, resolving _category to category_id."""
    for fixture in PRODUCT_FIXTURES:
        # Pop the marker key and resolve to a real FK
        category_name = fixture.pop("_category")
        category = categories_by_name.get(category_name)
        if category is None:
            raise ValueError(
                f"Product fixture '{fixture['name']}' references category "
                f"'{category_name}' which is not in CATEGORY_FIXTURES"
            )
        product = Product(category_id=category.id, **fixture)
        db.add(product)


def _seed_default_orders(db) -> None:
    """Insert default order templates, resolving customer + product names to IDs.

    Must run AFTER customers and products are committed (or at least flushed)
    so the name lookups find them.
    """
    for fixture in DEFAULT_ORDER_FIXTURES:
        # Resolve the customer by name
        customer_name = fixture["_customer"]
        customer = db.query(Customer).filter(Customer.name == customer_name).first()
        if customer is None:
            raise ValueError(
                f"Default order fixture references customer '{customer_name}' "
                "which wasn't seeded"
            )

        default_order = DefaultOrder(
            customer_id=customer.id,
            notes=fixture["notes"],
            is_active=fixture["is_active"],
        )

        # Resolve each item's product by name
        for item_fixture in fixture["items"]:
            product_name = item_fixture["_product"]
            product = db.query(Product).filter(Product.name == product_name).first()
            if product is None:
                raise ValueError(
                    f"Default order item references product '{product_name}' "
                    "which wasn't seeded"
                )
            default_order.items.append(
                DefaultOrderItem(
                    product_id=product.id,
                    quantity=item_fixture["quantity"],
                )
            )

        db.add(default_order)


def _seed_orders(db) -> None:
    """Insert sample orders, snapshotting product details at seed time.

    Must run AFTER customers and products are flushed (name lookups need IDs).
    """
    from datetime import date, timedelta

    for fixture in ORDER_FIXTURES:
        customer_name = fixture["_customer"]
        customer = db.query(Customer).filter(Customer.name == customer_name).first()
        if customer is None:
            raise ValueError(
                f"Order fixture references customer '{customer_name}' "
                "which wasn't seeded"
            )

        order = Order(
            customer_id=customer.id,
            status=fixture["status"],
            order_date=date.today() + timedelta(days=fixture["day_offset"]),
            notes=fixture["notes"],
            total_amount=0,  # computed below
        )

        total = 0.0
        for item_fixture in fixture["items"]:
            product_name = item_fixture["_product"]
            product = db.query(Product).filter(Product.name == product_name).first()
            if product is None:
                raise ValueError(
                    f"Order item references product '{product_name}' "
                    "which wasn't seeded"
                )
            qty = item_fixture["quantity"]
            unit_price = float(product.unit_price)
            subtotal = round(unit_price * qty, 2)
            order.items.append(
                OrderItem(
                    product_id=product.id,
                    product_name=product.name,
                    unit_price=unit_price,
                    unit_label=product.unit_label,
                    quantity=qty,
                    subtotal=subtotal,
                )
            )
            total += subtotal

        order.total_amount = round(total, 2)
        db.add(order)


DEV_ENVIRONMENTS = {"development", "dev", "local", "test"}


def main() -> int:
    # The admin fixture above has a published password. Refuse to plant it
    # anywhere that isn't marked as a development environment; a real
    # deployment creates its owner with `python -m scripts.create_owner`.
    if settings.ENVIRONMENT.strip().lower() not in DEV_ENVIRONMENTS:
        print(
            f"Refusing to seed: ENVIRONMENT is {settings.ENVIRONMENT!r}, not a "
            "development environment. The seed data includes a fixed admin "
            "password. Create the owner with `python -m scripts.create_owner` "
            "instead.",
            file=sys.stderr,
            flush=True,
        )
        return 1

    db = SessionLocal()
    try:
        _seed_admin_user(db)
        _seed_customers(db)
        categories_by_name = _seed_categories(db)
        _seed_products(db, categories_by_name)
        db.flush()  # customers + products need IDs before dependents
        _seed_default_orders(db)
        _seed_orders(db)
        db.commit()

        print(
            f"Inserted admin user + {len(CUSTOMER_FIXTURES)} customers + "
            f"{len(CATEGORY_FIXTURES)} categories + {len(PRODUCT_FIXTURES)} products + "
            f"{len(DEFAULT_ORDER_FIXTURES)} default orders + "
            f"{len(ORDER_FIXTURES)} orders",
            flush=True,
        )
        return 0
    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}", file=sys.stderr, flush=True)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
