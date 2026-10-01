from enum import StrEnum

from sqlalchemy import Column, Enum, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.service import Service


class CounterStatus(StrEnum):
    available = "available"
    busy = "busy"
    break_ = "break"
    closed = "closed"


counter_services = Table(
    "counter_services",
    Base.metadata,
    Column("counter_id", ForeignKey("counters.id", ondelete="CASCADE"), primary_key=True),
    Column("service_id", ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
)


class Counter(Base):
    __tablename__ = "counters"

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    # One staff member works one counter at a time (§6).
    assigned_staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True
    )
    status: Mapped[CounterStatus] = mapped_column(
        Enum(
            CounterStatus,
            native_enum=False,
            create_constraint=True,
            length=20,
            name="status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=CounterStatus.closed,
    )

    services: Mapped[list[Service]] = relationship(secondary=counter_services, lazy="selectin")

    @property
    def service_ids(self) -> list[int]:
        return sorted(s.id for s in self.services)
