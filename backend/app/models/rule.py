from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Rule(Base):
    """§10 org rules. department_id NULL = org-wide; otherwise a department override."""

    __tablename__ = "rules"
    __table_args__ = (UniqueConstraint("key", "department_id", postgresql_nulls_not_distinct=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String(50))
    value: Mapped[Any] = mapped_column(JSONB)
