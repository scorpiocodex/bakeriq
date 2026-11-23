"""Auth routes: register, login, current-user."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_superuser, get_current_user
from app.core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
)
from app.models import User
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_active_superuser),
) -> User:
    """Create a dashboard account. Superuser only.

    This used to be open to anyone who could reach the API, which meant
    anyone could register, log in and read customer data. Now a logged-in
    superuser (the seeded owner) must make the call: 401 without a token,
    403 for a normal user. The first account is created out of band with
    `python -m scripts.create_owner`.
    """
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=get_password_hash(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    user = db.query(User).filter(User.email == form_data.username).first()
    if user is None or not verify_password(form_data.password, user.password_hash):
        # IMPORTANT: same error for "no such user" and "wrong password" —
        # don't let attackers enumerate accounts.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )

    return Token(access_token=create_access_token(subject=user.id))


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
