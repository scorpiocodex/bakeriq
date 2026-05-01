"""Password hashing and JWT helpers."""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import jwt, JWTError

from app.core.config import settings

# bcrypt has a hard 72-byte input limit. We truncate at the byte level
# (not character level) because UTF-8 multibyte characters — emoji,
# non-Latin scripts — count as their byte length, not character count.
# A password of 72 emoji is 288 bytes and would otherwise raise.
_BCRYPT_MAX_BYTES = 72


def get_password_hash(password: str) -> str:
    """One-way hash with a fresh salt. Returns the encoded string."""
    password_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Constant-time comparison via bcrypt.checkpw."""
    plain_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    hashed_bytes = hashed_password.encode("utf-8")
    try:
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except ValueError:
        # Malformed hash in the database — treat as auth failure, don't crash.
        return False


def create_access_token(
    subject: str | Any,
    expires_delta: timedelta | None = None,
) -> str:
    """Build a signed JWT.

    Claims:
      sub — subject (user id as a string)
      iat — issued at (server time)
      exp — expiry (server time + delta)
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    now = datetime.now(timezone.utc)
    to_encode = {
        "sub": str(subject),
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Verify signature and return claims, or None if invalid/expired."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
