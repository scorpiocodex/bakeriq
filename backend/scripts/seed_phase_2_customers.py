"""Seed Phase 2 fixtures — admin user and 8 customers.

Run as: python -m scripts.seed_phase_2_customers
(from inside the api container, with /app as cwd)

What this seeds:
  - 1 admin user: owner@bakeriq.com / bakeriqowner
  - 8 customer fixtures with full addresses (Phase 2 task 1 testing)

Why the user is in here too:
make reset-db drops the public schema, which drops the users table
along with everything else. Without re-seeding the user, login breaks
after every reset. So the user is treated as a fixture, same as customers.

Idempotent for the admin user: skipped if a user with the same email
already exists (so `make seed` won't crash on subsequent runs).
Customers are not deduplicated here — bash callers (scripts/seed.sh,
scripts/reset-db.sh) clear the customers table before invoking this.

Why this script and not an Alembic migration:
We're using the "fixtures stay out of the migration chain" pattern
(see BakeriQ_Phase2_SeedData_Draft_v2.md, Option B). Production
deploys run alembic upgrade head and never run this script. Dev runs
both via `make reset-db`.
"""
from __future__ import annotations

import sys

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.customer import Customer, PreferredPhone
from app.models.user import User


# === Admin user fixture ======================================================
# This is the test user every dev session uses to log in. Hardcoded
# password is fine here — the password is only valid against the local
# dev database, which gets wiped regularly. NEVER use these credentials
# anywhere real.

ADMIN_USER_FIXTURE = {
    "email": "owner@bakeriq.com",
    "full_name": "Bakery Owner",
    "password": "bakeriqowner",  # plaintext here; hashed before insert
    "is_active": True,
    "is_superuser": True,
}


# === Customer fixtures =======================================================
# 8 customers from BakeriQ_Phase2_SeedData_Draft_v2.md.
#
# UUIDs are NOT specified — the model has default=uuid4, so SQLAlchemy
# generates a fresh one per row per insert. This means each `make reset-db`
# produces different IDs, which is correct: tests and code shouldn't
# depend on hardcoded fixture IDs.
#
# preferred_channel_phone uses the enum members directly rather than
# string values so a typo would be caught at import time, not at insert.

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


def _seed_admin_user(db) -> None:
    """Insert the admin test user. Skips if a user with this email already exists."""
    existing = db.query(User).filter(User.email == ADMIN_USER_FIXTURE["email"]).first()
    if existing is not None:
        # Already present — leave alone. Useful for `make seed` which
        # may be called multiple times without dropping users.
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


def main() -> int:
    db = SessionLocal()
    try:
        _seed_admin_user(db)
        _seed_customers(db)
        db.commit()

        # Print a single trace line. The bash caller pulls the customer
        # count from the database directly for the summary, but this
        # gives a useful breadcrumb in the spinner output if something
        # crashes mid-flight.
        print(
            f"Inserted admin user + {len(CUSTOMER_FIXTURES)} customers",
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