from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import now
from app.models.base import Base


class Role(StrEnum):
    customer = "customer"
    staff = "staff"
    manager = "manager"
    admin = "admin"


class AccountStatus(StrEnum):
    active = "active"
    suspended = "suspended"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)  # stored lowercase
    phone: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, create_constraint=True, length=20, name="role")
    )
    # Staff and managers belong to one department; customers and admins have none.
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    account_status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, native_enum=False, create_constraint=True, length=20, name="status"),
        default=AccountStatus.active,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
