"""The declarative base every ORM model inherits from.

A standard Alembic-friendly naming convention: without one, Alembic
autogenerate produces unstable, unpredictable constraint names across
runs/dialects, which makes migration diffs noisy and downgrade scripts
fragile.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """The one ``DeclarativeBase`` every ``db/models/*.py`` class maps onto."""

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)
