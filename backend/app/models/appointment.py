from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import now
from app.models.base import Base
from app.models.service import Service
from app.models.user import User


class AppointmentStatus(StrEnum):
    booked = "booked"
    confirmed = "confirmed"
    checked_in = "checked_in"
    waiting = "waiting"
    in_service = "in_service"
    completed = "completed"
    cancelled = "cancelled"
    missed = "missed"
    rescheduled = "rescheduled"
    delayed = "delayed"


S = AppointmentStatus
# Still going ahead: counts for duplicates and per-user limits.
ACTIVE = (S.booked, S.confirmed, S.checked_in, S.waiting, S.in_service, S.delayed)
# Gave its slot back (§7: a missed appointment frees the slot).
RELEASED = (S.cancelled, S.missed, S.rescheduled)

_active_sql = ", ".join(f"'{s.value}'" for s in ACTIVE)


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appointments_service_day", "service_id", "appointment_date"),
        # §10: one active appointment per user per service per day, enforced by the database.
        Index(
            "uq_appointments_active_user_service_day",
            "user_id",
            "service_id",
            "appointment_date",
            unique=True,
            postgresql_where=text(f"status IN ({_active_sql})"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    appointment_date: Mapped[date]  # department-local date
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, native_enum=False, create_constraint=True, length=20, name="status")
    )
    check_in_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    service_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    counter_id: Mapped[int | None] = mapped_column(ForeignKey("counters.id", ondelete="SET NULL"))
    rescheduled_from_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    service: Mapped[Service] = relationship(lazy="selectin")
    user: Mapped[User] = relationship(lazy="selectin")

    @property
    def appointment_number(self) -> str:
        return f"APT-{self.id:06d}"

    # Flat fields for the API, so the app doesn't need extra calls per row.
    @property
    def customer_name(self) -> str:
        return self.user.name

    @property
    def customer_phone(self) -> str | None:
        return self.user.phone

    @property
    def service_name(self) -> str:
        return self.service.name

    @property
    def service_code(self) -> str:
        return self.service.code

    @property
    def department_id(self) -> int:
        return self.service.department_id

    @property
    def department_name(self) -> str:
        return self.service.department.name
