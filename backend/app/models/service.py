from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("department_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(3))  # token prefix, e.g. "A" → A-027
    description: Mapped[str | None] = mapped_column(String(500))
    average_duration_min: Mapped[int]
    is_priority: Mapped[bool] = mapped_column(default=False)
    active_status: Mapped[bool] = mapped_column(default=True)

    slot_config: Mapped["SlotConfig"] = relationship(lazy="selectin", cascade="all, delete-orphan")


class SlotConfig(Base):
    __tablename__ = "slot_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), unique=True
    )
    slot_length_min: Mapped[int] = mapped_column(default=30)
    max_per_slot: Mapped[int] = mapped_column(default=6)
    daily_limit: Mapped[int | None]
