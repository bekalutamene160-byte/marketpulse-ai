"""SQLAlchemy declarative base for MarketPulse (blueprint 5.4: infrastructure/db).

A shared ``Base`` carries a naming convention so constraint names are deterministic
across runs and environments. That matters for Alembic: ``op.f("...")`` references
and ``DROP CONSTRAINT`` calls resolve to the same name whether the migration ran
against local, staging or production. Models register themselves on this ``Base``
by being imported (see ``models/__init__.py``).

This module is infrastructure: it imports SQLAlchemy, so it may never be imported by
``domain`` or ``application`` (enforced by tests/unit/test_architecture.py).
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
