"""Declarative base + portable column types.

Types use Postgres variants (JSONB, CITEXT, INET) but fall back to portable types
so the same models run on sqlite in tests and on PostgreSQL 16 in production. UUID
primary keys default Python-side (uuid4) so they work on both backends without
needing the pgcrypto `gen_random_uuid()` default (which the Alembic migration adds
for PostgreSQL).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Portable column types: native on PostgreSQL, generic elsewhere (e.g. sqlite tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")
EmailType = String(320).with_variant(CITEXT(), "postgresql")
IPType = String(45).with_variant(INET(), "postgresql")


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
