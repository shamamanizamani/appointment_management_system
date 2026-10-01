from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def paginate(db: AsyncSession, stmt: Select, limit: int, offset: int) -> dict:
    """Run a select as a {"items", "total"} page (CLAUDE.md §10 list shape)."""
    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    items = (await db.scalars(stmt.limit(limit).offset(offset))).all()
    return {"items": items, "total": total}
