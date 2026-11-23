"""JWT helpers: what must be accepted, and the ways a token must be refused."""

import base64
import hashlib
import hmac
import json
from datetime import timedelta

import jwt
from app.core.config import settings
from app.core.security import create_access_token, decode_token


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _hand_built(claims: dict, *, key: str | None = None, alg: str = "HS256") -> str:
    """A JWT assembled with only the standard library, so the test does not depend on
    the JWT library it is checking (and so it stands in for tokens issued before the
    library was swapped)."""
    header = {"alg": alg, "typ": "JWT"}
    signing_input = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"
    if alg == "none":
        return signing_input + "."
    digest = {"HS256": hashlib.sha256, "HS512": hashlib.sha512}[alg]
    signature = hmac.new((key or settings.SECRET_KEY).encode(), signing_input.encode(), digest).digest()
    return f"{signing_input}.{_b64(signature)}"


def _claims(sub: str = "user-123", *, expires_in: int = 3600) -> dict:
    import time

    now = int(time.time())
    return {"sub": sub, "iat": now, "exp": now + expires_in}


def test_round_trip_returns_the_subject():
    token = create_access_token(subject="user-123")
    claims = decode_token(token)
    assert claims is not None
    assert claims["sub"] == "user-123"
    assert {"iat", "exp"} <= set(claims)


def test_token_is_a_plain_string():
    assert isinstance(create_access_token(subject="x"), str)


def test_accepts_a_token_built_by_hand_the_standard_way():
    """Tokens issued before the library swap are plain HS256 JWTs and must still work,
    otherwise everyone is logged out on deploy."""
    assert decode_token(_hand_built(_claims("old-user")))["sub"] == "old-user"


def test_expired_token_is_refused():
    token = create_access_token(subject="x", expires_delta=timedelta(seconds=-5))
    assert decode_token(token) is None


def test_tampered_payload_is_refused():
    head, _payload, sig = create_access_token(subject="user-123").split(".")
    forged = _b64(json.dumps(_claims("someone-else")).encode())
    assert decode_token(f"{head}.{forged}.{sig}") is None


def test_token_signed_with_another_key_is_refused():
    assert decode_token(_hand_built(_claims(), key="not-the-real-secret-key-0123456789")) is None


def test_unsigned_alg_none_token_is_refused():
    assert decode_token(_hand_built(_claims(), alg="none")) is None


def test_token_using_a_different_hmac_algorithm_is_refused():
    """Signed with the right key but HS512 while the app expects HS256: the explicit
    algorithms list must win over whatever the token header claims."""
    assert settings.ALGORITHM == "HS256"
    assert decode_token(_hand_built(_claims(), alg="HS512")) is None


def test_garbage_is_refused_without_raising():
    for junk in ("", "not-a-token", "a.b.c", "....", "Bearer abc"):
        assert decode_token(junk) is None


def test_library_exception_type_is_the_one_the_code_catches():
    """If the JWT library changes its exception hierarchy, decode_token must still not leak it."""
    assert issubclass(jwt.InvalidTokenError, jwt.PyJWTError)
    assert decode_token(_hand_built(_claims(), alg="none")) is None
