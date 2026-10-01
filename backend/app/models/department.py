from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import now
from app.models.base import Base


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(10), unique=True)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Karachi")
    # {"mon": {"start": "09:00:00", "end": "17:00:00"} | null, ...} — local time (§5)
    working_hours: Mapped[dict] = mapped_column(JSONB)
    # [{"start": "13:00:00", "end": "14:00:00", "days": null | ["fri", ...]}]
    break_windows: Mapped[list] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
