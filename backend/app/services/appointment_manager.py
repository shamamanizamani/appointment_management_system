"""Appointments (§3, §5, §10): slot generation, booking without overbooking, cancel, reschedule."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import time as clock
from app.core.errors import AppError
from app.models import ActivityLog, Appointment, Role, Service, User
from app.models.appointment import ACTIVE, RELEASED
from app.models.appointment import AppointmentStatus as S
from app.schemas.org import WEEKDAYS, BreakWindow, WorkingHours
from app.services import activity, rules_engine
from app.utils.state_machine import check_transition

# CLAUDE.md §6 appointment state machine.
ALLOWED = {
    S.booked: {S.confirmed, S.cancelled, S.rescheduled},
    S.confirmed: {S.checked_in, S.cancelled, S.rescheduled, S.missed},
    S.checked_in: {S.waiting},
    S.waiting: {S.in_service, S.delayed},
    S.in_service: {S.completed, S.delayed},
    S.delayed: {S.waiting, S.in_service},
}

MAX_DATE_RANGE_DAYS = 31


def transition(db: AsyncSession, actor: User | None, appt: Appointment, to: S) -> None:
    check_transition(ALLOWED, "appointment", appt.status, to)
    activity.log(db, actor, "status", "appointment", appt.id, {"from": appt.status, "to": to})
    appt.status = to


# --- slot generation (§5) ---


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _time(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def slot_times(
    day: date, working_hours: dict, break_windows: list, length_min: int
) -> list[tuple[time, time]]:
    """Local (start, end) slots: the day's working hours minus its breaks, cut into
    `length_min` pieces. Each stretch between breaks starts fresh, so no slot crosses a break."""
    weekday = WEEKDAYS[day.weekday()]
    hours = getattr(WorkingHours.model_validate(working_hours), weekday)
    if hours is None:
        return []
    segments = [(_minutes(hours.start), _minutes(hours.end))]
    for b in map(BreakWindow.model_validate, break_windows):
        if b.days is not None and weekday not in b.days:
            continue
        bs, be = _minutes(b.start), _minutes(b.end)
        segments = [
            part
            for s, e in segments
            for part in ((s, min(e, bs)), (max(s, be), e))
            if part[0] < part[1]
        ]
    return [
        (_time(t), _time(t + length_min))
        for s, e in sorted(segments)
        for t in range(s, e - length_min + 1, length_min)
    ]


def _tz(service: Service) -> ZoneInfo:
    return ZoneInfo(service.department.timezone)


def _local_today(service: Service) -> date:
    return clock.now().astimezone(_tz(service)).date()


def _check_open(service: Service) -> None:
    if not service.active_status or not service.department.active:
        raise AppError(409, "SERVICE_CLOSED", "This service isn't taking bookings right now.")


async def _window_end(db: AsyncSession, service: Service) -> date:
    days = await rules_engine.get(db, "booking_window_days", service.department_id)
    return _local_today(service) + timedelta(days=days)


async def _check_window(db: AsyncSession, service: Service, day: date) -> None:
    if not _local_today(service) <= day <= await _window_end(db, service):
        days = await rules_engine.get(db, "booking_window_days", service.department_id)
        raise AppError(
            422, "OUTSIDE_BOOKING_WINDOW", f"You can book from today up to {days} days ahead."
        )


async def _booked_counts(
    db: AsyncSession, service_id: int, first: date, last: date
) -> dict[datetime, int]:
    """Bookings holding each slot (start_time → count). Released statuses don't count (§7)."""
    rows = await db.execute(
        select(Appointment.start_time, func.count())
        .where(
            Appointment.service_id == service_id,
            Appointment.appointment_date.between(first, last),
            Appointment.status.not_in(RELEASED),
        )
        .group_by(Appointment.start_time)
    )
    return dict(rows.all())


def _build_slots(service: Service, day: date, counts: dict[datetime, int]) -> list[dict]:
    cfg, tz, now = service.slot_config, _tz(service), clock.now()
    times = slot_times(
        day, service.department.working_hours, service.department.break_windows, cfg.slot_length_min
    )
    starts = [datetime.combine(day, st, tz).astimezone(UTC) for st, _ in times]
    day_total = sum(counts.get(s, 0) for s in starts)
    day_full = cfg.daily_limit is not None and day_total >= cfg.daily_limit
    slots = []
    for (st, en), start in zip(times, starts, strict=True):
        booked = counts.get(start, 0)
        if start <= now:
            status = "past"
        elif day_full or booked >= cfg.max_per_slot:
            status = "full"
        else:
            status = "available"
        slots.append(
            {
                "start": start,
                "end": datetime.combine(day, en, tz).astimezone(UTC),
                "local_start": st.strftime("%H:%M"),
                "local_end": en.strftime("%H:%M"),
                "max": cfg.max_per_slot,
                "booked": booked,
                "status": status,
            }
        )
    return slots


async def slot_grid(db: AsyncSession, service: Service, day: date) -> dict:
    _check_open(service)
    await _check_window(db, service, day)
    slots = _build_slots(service, day, await _booked_counts(db, service.id, day, day))
    return {
        "service_id": service.id,
        "date": day,
        "timezone": service.department.timezone,
        "slot_length_min": service.slot_config.slot_length_min,
        "daily_limit": service.slot_config.daily_limit,
        "booked_total": sum(s["booked"] for s in slots),
        "slots": slots,
    }


async def available_dates(
    db: AsyncSession, service: Service, first: date | None, last: date | None
) -> list[dict]:
    _check_open(service)
    first = first or _local_today(service)
    last = last or await _window_end(db, service)
    if (last - first).days >= MAX_DATE_RANGE_DAYS or last < first:
        raise AppError(
            422, "VALIDATION_ERROR", f"Choose a range of 1 to {MAX_DATE_RANGE_DAYS} days."
        )
    await _check_window(db, service, first)
    await _check_window(db, service, last)
    counts = await _booked_counts(db, service.id, first, last)
    out = []
    for i in range((last - first).days + 1):
        day = first + timedelta(days=i)
        slots = [s for s in _build_slots(service, day, counts) if s["status"] != "past"]
        free = sum(s["status"] == "available" for s in slots)
        status = "closed" if not slots else "available" if free else "full"
        out.append({"date": day, "available_slots": free, "status": status})
    return out


# --- booking ---


async def _lock(db: AsyncSession, user_id: int, service_id: int) -> Service:
    """Row locks serialise bookings: per user (daily limit) and per service (slot capacity and
    daily_limit). Always user first, then service, so two bookings can't deadlock."""
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())
    service = await db.scalar(select(Service).where(Service.id == service_id).with_for_update())
    if service is None:
        raise AppError(404, "NOT_FOUND", "Service not found.")
    return service


async def _place(db: AsyncSession, user: User, service: Service, start: datetime) -> Appointment:
    """Validate and insert one appointment. Caller holds the locks from _lock()."""
    _check_open(service)
    start = start.astimezone(UTC)
    day = start.astimezone(_tz(service)).date()
    await _check_window(db, service, day)

    counts = await _booked_counts(db, service.id, day, day)
    slot = next((s for s in _build_slots(service, day, counts) if s["start"] == start), None)
    if slot is None:
        raise AppError(422, "OUTSIDE_WORKING_HOURS", "That time isn't one of this service's slots.")
    if slot["status"] == "past":
        raise AppError(422, "SLOT_PASSED", "That slot has already started.")

    mine = select(func.count()).where(
        Appointment.user_id == user.id,
        Appointment.appointment_date == day,
        Appointment.status.in_(ACTIVE),
    )
    if await db.scalar(mine.where(Appointment.service_id == service.id)):
        raise AppError(
            409,
            "DUPLICATE_APPOINTMENT",
            "You already have an appointment for this service that day.",
        )
    limit = await rules_engine.get(db, "max_appointments_per_user_per_day", service.department_id)
    if await db.scalar(mine) >= limit:
        raise AppError(
            409, "LIMIT_REACHED", f"You can have at most {limit} appointments on one day."
        )
    if slot["status"] == "full":
        cfg = service.slot_config
        if slot["booked"] >= cfg.max_per_slot:
            raise AppError(409, "SLOT_FULL", "This slot is full. Please pick another time.")
        raise AppError(409, "SLOT_FULL", "This service is fully booked that day.")

    appt = Appointment(
        user=user,
        service=service,
        appointment_date=day,
        start_time=start,
        end_time=slot["end"],
        status=S.booked,
    )
    db.add(appt)
    await db.flush()
    activity.log(db, user, "create", "appointment", appt.id, {"start": start.isoformat()})
    transition(db, user, appt, S.confirmed)  # §3: availability checked → confirmed
    return appt


async def book(db: AsyncSession, user: User, service_id: int, start: datetime) -> Appointment:
    service = await _lock(db, user.id, service_id)
    appt = await _place(db, user, service, start)
    await db.commit()
    return appt


async def reschedule(
    db: AsyncSession, actor: User, appt: Appointment, start: datetime
) -> Appointment:
    """Old appointment → rescheduled; a new confirmed one links back via rescheduled_from_id."""
    service = await _lock(db, appt.user_id, appt.service_id)
    transition(db, actor, appt, S.rescheduled)
    await db.flush()  # frees the old slot and duplicate-index entry before placing the new one
    new = await _place(db, appt.user, service, start)
    new.rescheduled_from_id = appt.id
    await db.commit()
    return new


async def cancel(db: AsyncSession, actor: User, appt: Appointment) -> Appointment:
    if actor.role == Role.customer:
        # §10 cancellation limit: the customer's own cancellations in the last 7 days.
        limit = await rules_engine.get(db, "cancellation_limit", appt.department_id)
        recent = await db.scalar(
            select(func.count()).where(
                ActivityLog.actor_id == actor.id,
                ActivityLog.entity == "appointment",
                ActivityLog.details["to"].astext == S.cancelled,
                ActivityLog.created_at >= clock.now() - timedelta(days=7),
            )
        )
        if recent >= limit:
            raise AppError(
                409, "LIMIT_REACHED", f"You can cancel at most {limit} appointments in 7 days."
            )
    transition(db, actor, appt, S.cancelled)
    appt.cancelled_at = clock.now()
    await db.commit()
    return appt


# --- access and listing ---


def check_access(user: User, appt: Appointment, manage: bool = False) -> None:
    """Customers: own only (404 otherwise, so ids don't leak). Staff/managers: own department;
    staff can view but not cancel/reschedule. Admins: everything."""
    if user.role == Role.customer:
        if appt.user_id != user.id:
            raise AppError(404, "NOT_FOUND", "Appointment not found.")
    elif user.role != Role.admin:
        if user.department_id != appt.department_id or (manage and user.role == Role.staff):
            raise AppError(403, "FORBIDDEN", "You don't have permission to do this.")


def mine_query(user: User, when: str, status: S | None) -> Select:
    stmt = select(Appointment).where(Appointment.user_id == user.id)
    now = clock.now()
    if when == "upcoming":
        stmt = stmt.where(Appointment.start_time >= now).order_by(Appointment.start_time)
    else:
        if when == "past":
            stmt = stmt.where(Appointment.start_time < now)
        stmt = stmt.order_by(Appointment.start_time.desc())
    if status:
        stmt = stmt.where(Appointment.status == status)
    return stmt


def department_query(
    department_id: int | None, service_id: int | None, day: date | None, status: S | None
) -> Select:
    stmt = select(Appointment).join(Service).order_by(Appointment.start_time)
    if department_id is not None:
        stmt = stmt.where(Service.department_id == department_id)
    if service_id is not None:
        stmt = stmt.where(Appointment.service_id == service_id)
    if day is not None:
        stmt = stmt.where(Appointment.appointment_date == day)
    if status:
        stmt = stmt.where(Appointment.status == status)
    return stmt
