from datetime import time

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class StaffShift(Base):
    __tablename__ = "staff_shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    counter_id: Mapped[int] = mapped_column(ForeignKey("counters.id", ondelete="CASCADE"))
    weekday: Mapped[str] = mapped_column(String(3))  # "mon".."sun"
    start_time: Mapped[time]
    end_time: Mapped[time]
