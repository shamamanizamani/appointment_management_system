"""§4 waiting-time estimate (CLAUDE.md §7)."""

import math
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Counter, CounterStatus, Service, Token, TokenStatus, counter_services

ROLLING_WINDOW = 20


def estimate(people_ahead: int, avg_duration_min: float, active_counters: int) -> int:
    """Brief §4: 5 people ahead × 4 min ÷ 2 counters = 10 min."""
    return math.ceil(people_ahead * avg_duration_min / max(active_counters, 1))


async def avg_duration(db: AsyncSession, service: Service, day: date) -> float:
    """Mean minutes of the last 20 services completed today, else the configured average."""
    minutes = func.extract("epoch", Token.completed_at - Token.service_started_at) / 60
    recent = (
        select(minutes.label("m"))
        .where(
            Token.service_id == service.id,
            Token.queue_date == day,
            Token.status == TokenStatus.completed,
            Token.service_started_at.is_not(None),
        )
        .order_by(Token.completed_at.desc())
        .limit(ROLLING_WINDOW)
        .subquery()
    )
    avg = await db.scalar(select(func.avg(recent.c.m)))
    return float(avg) if avg is not None else service.average_duration_min


async def active_counters(db: AsyncSession, service_id: int) -> int:
    """Counters serving this service that are open (available or busy)."""
    return await db.scalar(
        select(func.count())
        .select_from(Counter)
        .join(counter_services)
        .where(
            counter_services.c.service_id == service_id,
            Counter.status.in_((CounterStatus.available, CounterStatus.busy)),
        )
    )
