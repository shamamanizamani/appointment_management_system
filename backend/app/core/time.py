"""All time access goes through now(). Tests freeze it by setting _frozen."""

from datetime import UTC, datetime

_frozen: datetime | None = None


def now() -> datetime:
    return _frozen or datetime.now(UTC)
