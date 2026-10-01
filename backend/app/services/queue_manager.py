"""Walk-in queue (§3, §4, §7): token numbers, queue ordering, positions and estimates."""

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import time as clock
from app.core.errors import AppError
from app.models import (
    Appointment,
    QueueEvent,
    QueueEventType,
    Service,
    Token,
    TokenSequence,
    TokenSource,
    User,
)
from app.models.token import ACTIVE
from app.models.token import TokenStatus as T
from app.schemas.org import WEEKDAYS, WorkingHours
from app.services import appointment_manager as am
from app.services import org, rules_engine, wait_time
from app.utils.state_machine import check_transition

# CLAUDE.md §6 token state machine.
ALLOWED = {
    T.waiting: {T.called, T.cancelled},
    T.called: {T.in_service, T.no_response, T.skipped},
    T.no_response: {T.recalled, T.missed},
    T.recalled: {T.called, T.skipped, T.missed},
    T.skipped: {T.waiting},
    T.in_service: {T.completed},
}
# Status → the queue_events row it writes. Re-entering `waiting` after a skip writes none.
_EVENT = {T.in_service: QueueEventType.started, T.waiting: None}

DUE_SOON = timedelta(minutes=5)


def transition(db: AsyncSession, token: Token, to: T, counter_id: int | None = None) -> None:
    check_transition(ALLOWED, "token", token.status, to)
    event = _EVENT.get(to, QueueEventType(to.value))
    if event:
        db.add(QueueEvent(token_id=token.id, event=event, counter_id=counter_id))
    token.status = to
    if to != T.waiting:
        token.queue_position = token.estimated_wait_min = None


async def ordered_queue(db: AsyncSession, service: Service) -> list[Token]:
    """§7 queue order: the only place it is decided. Today's waiting tokens, sorted by
    1. priority, 2. checked-in appointments starting within 5 minutes, 3. time joined."""
    due = (Token.source == TokenSource.appointment) & (
        Appointment.start_time <= clock.now() + DUE_SOON
    )
    stmt = (
        select(Token)
        .outerjoin(Appointment, Token.appointment_id == Appointment.id)
        .where(
            Token.service_id == service.id,
            Token.queue_date == am.local_today(service),
            Token.status == T.waiting,
        )
        .order_by(Token.priority.desc(), case((due, 0), else_=1), Token.created_at, Token.id)
    )
    return list(await db.scalars(stmt))


async def recalculate_queue(db: AsyncSession, service: Service) -> list[Token]:
    """§4: refresh position and estimate of every waiting token in the service's queue."""
    tokens = await ordered_queue(db, service)
    avg = await wait_time.avg_duration(db, service, am.local_today(service))
    counters = await wait_time.active_counters(db, service.id)
    for ahead, token in enumerate(tokens):
        token.queue_position = ahead + 1
        token.estimated_wait_min = wait_time.estimate(ahead, avg, counters)
    return tokens


async def current_token(db: AsyncSession, service: Service) -> str | None:
    """The token most recently called for this service today (brief §3 "Current Token")."""
    return await db.scalar(
        select(Token.token_number)
        .where(
            Token.service_id == service.id,
            Token.queue_date == am.local_today(service),
            Token.called_at.is_not(None),
        )
        .order_by(Token.called_at.desc())
        .limit(1)
    )


async def refresh(db: AsyncSession, token: Token) -> Token:
    """Fill in live position, estimate and current token for a response."""
    if token.status == T.waiting:
        await recalculate_queue(db, token.service)
    token.current_token = await current_token(db, token.service)
    return token


def _check_open_now(service: Service) -> None:
    am.check_open(service)
    dept = service.department
    local = clock.now().astimezone(ZoneInfo(dept.timezone))
    hours = getattr(WorkingHours.model_validate(dept.working_hours), WEEKDAYS[local.weekday()])
    if hours is None or not hours.start <= local.time() < hours.end:
        raise AppError(
            409,
            "SERVICE_CLOSED",
            "This queue is closed right now. Please come back during opening hours.",
        )


async def _next_number(db: AsyncSession, service_id: int, day: date) -> int:
    """§7: one atomic upsert on token_sequences. The row lock it takes makes concurrent joins
    wait their turn, and a rolled-back join rolls its number back too, so there are no gaps."""
    stmt = (
        insert(TokenSequence)
        .values(service_id=service_id, day=day, last_number=1)
        .on_conflict_do_update(
            index_elements=["service_id", "date"],
            set_={"last_number": TokenSequence.last_number + 1},
        )
        .returning(TokenSequence.last_number)
    )
    return await db.scalar(stmt)


async def join(db: AsyncSession, user: User, service_id: int) -> Token:
    # Serialise this customer's joins so the duplicate and limit checks can't race.
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    service = await org.get_or_404(db, Service, service_id, "Service")
    _check_open_now(service)
    day = am.local_today(service)

    mine = select(func.count()).where(
        Token.user_id == user.id, Token.queue_date == day, Token.status.in_(ACTIVE)
    )
    if await db.scalar(mine.where(Token.service_id == service.id)):
        raise AppError(409, "DUPLICATE_TOKEN", "You already have a token for this service.")
    limit = await rules_engine.get(db, "max_tokens_per_user", service.department_id)
    if await db.scalar(mine) >= limit:
        raise AppError(409, "LIMIT_REACHED", f"You can hold at most {limit} tokens at once.")

    priority_ids = await rules_engine.get(db, "priority_services", service.department_id)
    number = await _next_number(db, service.id, day)
    token = Token(
        token_number=f"{service.code}-{number:03d}",
        user=user,
        service=service,
        queue_date=day,
        source=TokenSource.walk_in,
        status=T.waiting,
        priority=service.is_priority or service.id in priority_ids,  # §10 priority services
    )
    db.add(token)
    await db.flush()
    db.add(QueueEvent(token_id=token.id, event=QueueEventType.created))
    await recalculate_queue(db, service)
    await db.commit()
    token.current_token = await current_token(db, service)
    return token


async def cancel(db: AsyncSession, token: Token) -> Token:
    transition(db, token, T.cancelled)
    await db.flush()
    await recalculate_queue(db, token.service)
    await db.commit()
    return await refresh(db, token)


def mine_active_query(user: User):
    return (
        select(Token)
        .where(Token.user_id == user.id, Token.status.in_(ACTIVE))
        .order_by(Token.created_at)
    )
