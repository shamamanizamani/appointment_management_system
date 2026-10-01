from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import now
from app.models.base import Base
from app.models.service import Service
from app.models.user import User


class TokenStatus(StrEnum):
    waiting = "waiting"
    called = "called"
    no_response = "no_response"
    recalled = "recalled"
    skipped = "skipped"
    in_service = "in_service"
    completed = "completed"
    missed = "missed"
    cancelled = "cancelled"


class TokenSource(StrEnum):
    walk_in = "walk_in"
    appointment = "appointment"


class QueueEventType(StrEnum):
    created = "created"
    called = "called"
    no_response = "no_response"
    recalled = "recalled"
    skipped = "skipped"
    missed = "missed"
    started = "started"
    completed = "completed"
    cancelled = "cancelled"


T = TokenStatus
# Still in the queue or being served: counts for duplicates and max_tokens_per_user (§10).
ACTIVE = (T.waiting, T.called, T.no_response, T.recalled, T.in_service)
_active_sql = ", ".join(f"'{s.value}'" for s in ACTIVE)


def _enum(e: type[StrEnum], name: str) -> Enum:
    return Enum(e, native_enum=False, create_constraint=True, length=20, name=name)


class Token(Base):
    __tablename__ = "tokens"
    __table_args__ = (
        UniqueConstraint("service_id", "queue_date", "token_number"),
        Index("ix_tokens_service_day_status", "service_id", "queue_date", "status"),
        # §10: one active token per user per service (per day, since queues are daily).
        Index(
            "uq_tokens_active_user_service_day",
            "user_id",
            "service_id",
            "queue_date",
            unique=True,
            postgresql_where=text(f"status IN ({_active_sql})"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    token_number: Mapped[str] = mapped_column(String(10))  # e.g. "A-027"
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    queue_date: Mapped[date]  # department-local day of the queue
    source: Mapped[TokenSource] = mapped_column(_enum(TokenSource, "source"))
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"))
    status: Mapped[TokenStatus] = mapped_column(_enum(TokenStatus, "status"))
    priority: Mapped[bool] = mapped_column(default=False)
    recall_count: Mapped[int] = mapped_column(default=0)
    # Snapshot from the last recalculation; reads recompute them live.
    queue_position: Mapped[int | None]
    estimated_wait_min: Mapped[int | None]
    counter_id: Mapped[int | None] = mapped_column(ForeignKey("counters.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    service_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    service: Mapped[Service] = relationship(lazy="selectin")
    user: Mapped[User | None] = relationship(lazy="selectin")
    appointment: Mapped["Appointment | None"] = relationship(lazy="selectin")  # noqa: F821

    current_token = None  # str | None, set by queue_manager before responding

    @property
    def people_ahead(self) -> int | None:
        if self.status != T.waiting or self.queue_position is None:
            return None
        return self.queue_position - 1

    @property
    def customer_name(self) -> str | None:
        return self.user.name if self.user else None

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


class TokenSequence(Base):
    """§7: last token number handed out per service per day."""

    __tablename__ = "token_sequences"

    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), primary_key=True)
    day: Mapped[date] = mapped_column("date", primary_key=True)
    last_number: Mapped[int]


class QueueEvent(Base):
    """Token history (§6): what analytics and the AI features learn from."""

    __tablename__ = "queue_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id", ondelete="CASCADE"), index=True)
    event: Mapped[QueueEventType] = mapped_column(_enum(QueueEventType, "event"))
    counter_id: Mapped[int | None] = mapped_column(ForeignKey("counters.id", ondelete="SET NULL"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
