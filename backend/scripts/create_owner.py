"""Create the first dashboard account (a superuser) without the seed data.

Run as: python -m scripts.create_owner --email you@example.com --name "Your Name"
(from inside the api container, with /app as cwd; add -it to docker compose
exec so the password prompt works)

Why this exists: POST /api/v1/auth/register now needs a logged-in superuser,
so on a database nobody has logged in to yet there is no way to make the
first account through the API. The seed script can't fill that gap — it
wipes and refills demo data and carries a published password. This creates
one account and touches nothing else.

The password is read from a hidden prompt, or from the
BAKERIQ_OWNER_PASSWORD environment variable when there is no terminal. It is
deliberately not a command-line flag, which would leave it in shell history
and the process list.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User
from app.schemas.user import UserCreate
from pydantic import ValidationError
from sqlalchemy.orm import Session


class OwnerExistsError(Exception):
    """A user with this email is already in the database."""


def create_owner(
    db: Session, *, email: str, full_name: str | None, password: str
) -> User:
    """Insert a superuser. Raises OwnerExistsError if the email is taken, or
    pydantic's ValidationError if the email or password is unacceptable."""
    # Reuse the API's own rules (valid email, 8-72 character password).
    data = UserCreate(email=email, full_name=full_name, password=password)

    if db.query(User).filter(User.email == data.email).first() is not None:
        raise OwnerExistsError(data.email)

    user = User(
        email=data.email,
        full_name=data.full_name,
        password_hash=get_password_hash(data.password),
        is_active=True,
        is_superuser=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _read_password() -> str:
    from_env = os.environ.get("BAKERIQ_OWNER_PASSWORD")
    if from_env:
        return from_env
    if not sys.stdin.isatty():
        raise SystemExit(
            "No terminal for the password prompt. Run with `docker compose exec -it`, "
            "or set BAKERIQ_OWNER_PASSWORD."
        )
    first = getpass.getpass("Password: ")
    if getpass.getpass("Repeat password: ") != first:
        raise SystemExit("Passwords did not match.")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create the first BakeriQ superuser.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default=None, help="full name shown in the dashboard")
    args = parser.parse_args(argv)

    password = _read_password()

    db = SessionLocal()
    try:
        user = create_owner(
            db, email=args.email, full_name=args.name, password=password
        )
    except OwnerExistsError:
        print(
            f"A user with email {args.email} already exists; nothing changed.",
            file=sys.stderr,
        )
        return 1
    except ValidationError as e:
        print(f"Invalid input: {e.errors()[0]['msg']}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"Created superuser {user.email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
