"""Declarative base for all SQLAlchemy models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All ORM models inherit from this.

    SQLAlchemy 2.0 style — DeclarativeBase replaces the older
    declarative_base() function from 1.x.
    """

    pass
