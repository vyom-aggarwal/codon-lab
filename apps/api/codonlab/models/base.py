"""Shared model primitives.

Note on inheritance: SQLAlchemy ``Column`` instances cannot be shared between
mapped classes, so base classes here use ``sa_type`` rather than ``sa_column``.
Passing ``sa_column`` from a base would raise on the second subclass.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Timezone-aware now. Every timestamp in this schema is UTC."""
    return datetime.now(UTC)


def utc_timestamp(
    *,
    nullable: bool,
    index: bool = False,
    default_factory: Callable[[], datetime] | None = None,
) -> Any:
    """A timezone-aware timestamp column.

    Returns ``Any`` because SQLModel types ``sa_type`` as a class rather than an
    instance, so ``DateTime(timezone=True)`` — the only way to get a tz-aware
    column — matches none of ``Field``'s overloads. The runtime result is correct;
    the generated DDL is ``TIMESTAMP WITH TIME ZONE``. Confining the escape hatch
    to this one helper keeps it out of the model definitions themselves.
    """
    options: dict[str, Any] = {
        "sa_type": DateTime(timezone=True),
        "nullable": nullable,
        "index": index,
    }
    if default_factory is None:
        options["default"] = None
    else:
        options["default_factory"] = default_factory
    return Field(**options)


class UUIDModel(SQLModel):
    """Primary key is a UUID so ids can be minted client-side and stay stable
    across the API/queue boundary without a round trip."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class TimestampedModel(UUIDModel):
    created_at: datetime = utc_timestamp(nullable=False, index=True, default_factory=utcnow)
