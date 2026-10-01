# Import every model here so Base.metadata (Alembic, tests) sees all tables.
from app.models.activity_log import ActivityLog
from app.models.base import Base
from app.models.counter import Counter, CounterStatus, counter_services
from app.models.department import Department
from app.models.rule import Rule
from app.models.service import Service, SlotConfig
from app.models.staff_shift import StaffShift
from app.models.user import AccountStatus, Role, User

__all__ = [
    "AccountStatus",
    "ActivityLog",
    "Base",
    "Counter",
    "CounterStatus",
    "Department",
    "Role",
    "Rule",
    "Service",
    "SlotConfig",
    "StaffShift",
    "User",
    "counter_services",
]
