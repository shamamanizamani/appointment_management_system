# Import every model here so Base.metadata (Alembic, tests) sees all tables.
from app.models.activity_log import ActivityLog
from app.models.appointment import Appointment, AppointmentStatus
from app.models.base import Base
from app.models.counter import Counter, CounterStatus, counter_services
from app.models.department import Department
from app.models.rule import Rule
from app.models.service import Service, SlotConfig
from app.models.staff_shift import StaffShift
from app.models.token import (
    QueueEvent,
    QueueEventType,
    Token,
    TokenSequence,
    TokenSource,
    TokenStatus,
)
from app.models.user import AccountStatus, Role, User

__all__ = [
    "AccountStatus",
    "ActivityLog",
    "Appointment",
    "AppointmentStatus",
    "Base",
    "Counter",
    "CounterStatus",
    "Department",
    "QueueEvent",
    "QueueEventType",
    "Role",
    "Rule",
    "Service",
    "SlotConfig",
    "StaffShift",
    "Token",
    "TokenSequence",
    "TokenSource",
    "TokenStatus",
    "User",
    "counter_services",
]
