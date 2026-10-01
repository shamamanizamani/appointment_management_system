from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActivityLog, User


def log(
    db: AsyncSession,
    actor: User | None,
    action: str,
    entity: str,
    entity_id: int | None,
    details: dict[str, Any] | None = None,
) -> None:
    """§10 activity log. Added to the caller's transaction; committed together with the change."""
    db.add(
        ActivityLog(
            actor_id=actor.id if actor else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details,
        )
    )
