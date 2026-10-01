from datetime import datetime, time
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.models import AccountStatus, CounterStatus, Role
from app.schemas.auth import Password, RegisterIn
from app.schemas.user import Name, Phone

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAYS: tuple[Weekday, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _upper(v):
    return v.strip().upper() if isinstance(v, str) else v


# Uppercase first: StringConstraints checks the pattern before its own to_upper.
DeptCode = Annotated[str, BeforeValidator(_upper), StringConstraints(pattern=r"^[A-Z0-9]{2,10}$")]
ServiceCode = Annotated[str, BeforeValidator(_upper), StringConstraints(pattern=r"^[A-Z]{1,3}$")]


def _valid_tz(v: str) -> str:
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Unknown timezone") from None
    return v


Timezone = Annotated[str, AfterValidator(_valid_tz)]


class TimeRange(BaseModel):
    start: time
    end: time

    @model_validator(mode="after")
    def _ordered(self):
        if self.start >= self.end:
            raise ValueError("start must be before end")
        return self


class BreakWindow(TimeRange):
    days: list[Weekday] | None = None  # None = every working day


class WorkingHours(BaseModel):
    """Per weekday opening hours; null = closed that day."""

    mon: TimeRange | None = None
    tue: TimeRange | None = None
    wed: TimeRange | None = None
    thu: TimeRange | None = None
    fri: TimeRange | None = None
    sat: TimeRange | None = None
    sun: TimeRange | None = None


_NINE_TO_FIVE = TimeRange(start=time(9), end=time(17))
DEFAULT_WORKING_HOURS = WorkingHours(**{d: _NINE_TO_FIVE for d in WEEKDAYS[:5]})
DEFAULT_BREAKS = [BreakWindow(start=time(13), end=time(14))]


# --- departments ---


class DepartmentCreate(BaseModel):
    name: Name
    code: DeptCode
    timezone: Timezone = "Asia/Karachi"
    working_hours: WorkingHours = DEFAULT_WORKING_HOURS
    break_windows: list[BreakWindow] = DEFAULT_BREAKS


class DepartmentUpdate(BaseModel):
    name: Name | None = None
    code: DeptCode | None = None
    timezone: Timezone | None = None
    working_hours: WorkingHours | None = None
    break_windows: list[BreakWindow] | None = None
    active: bool | None = None


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    timezone: str
    working_hours: WorkingHours
    break_windows: list[BreakWindow]
    active: bool
    created_at: datetime


# --- services ---


class SlotConfigIn(BaseModel):
    slot_length_min: int = Field(30, ge=5, le=240)
    max_per_slot: int = Field(6, ge=1, le=100)
    daily_limit: int | None = Field(None, ge=1)


class SlotConfigUpdate(BaseModel):
    slot_length_min: int | None = Field(None, ge=5, le=240)
    max_per_slot: int | None = Field(None, ge=1, le=100)
    daily_limit: int | None = Field(None, ge=1)  # send null to remove the cap


class SlotConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slot_length_min: int
    max_per_slot: int
    daily_limit: int | None


class ServiceCreate(BaseModel):
    name: Name
    code: ServiceCode
    description: Annotated[str, StringConstraints(max_length=500)] | None = None
    average_duration_min: int = Field(ge=1, le=480)
    is_priority: bool = False
    slot_config: SlotConfigIn = SlotConfigIn()


class ServiceUpdate(BaseModel):
    name: Name | None = None
    code: ServiceCode | None = None
    description: Annotated[str, StringConstraints(max_length=500)] | None = None
    average_duration_min: int | None = Field(None, ge=1, le=480)
    is_priority: bool | None = None
    active_status: bool | None = None
    slot_config: SlotConfigUpdate | None = None


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    department_id: int
    name: str
    code: str
    description: str | None
    average_duration_min: int
    is_priority: bool
    active_status: bool
    slot_config: SlotConfigOut


# --- counters ---


class CounterCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    service_ids: list[int] = []
    assigned_staff_id: int | None = None


class CounterUpdate(BaseModel):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)] | None
    ) = None
    service_ids: list[int] | None = None
    assigned_staff_id: int | None = None  # send null to unassign


class CounterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    department_id: int
    name: str
    service_ids: list[int]
    assigned_staff_id: int | None
    status: CounterStatus


# --- staff, shifts, users ---


class StaffCreate(RegisterIn):
    pass


class StaffUpdate(BaseModel):
    name: Name | None = None
    phone: Phone | None = None
    account_status: AccountStatus | None = None


class AdminUserCreate(RegisterIn):
    role: Role
    department_id: int | None = None


class AdminUserUpdate(BaseModel):
    name: Name | None = None
    phone: Phone | None = None
    role: Role | None = None
    department_id: int | None = None
    account_status: AccountStatus | None = None
    password: Password | None = None


class ShiftCreate(BaseModel):
    staff_id: int
    counter_id: int
    weekday: Weekday
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def _ordered(self):
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class ShiftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    staff_id: int
    counter_id: int
    weekday: Weekday
    start_time: time
    end_time: time


# --- rules ---


class RuleOut(BaseModel):
    key: str
    value: Any
    source: Literal["default", "org", "department"]


class RulePut(BaseModel):
    department_id: int | None = None  # null = org-wide (admin only)
    value: Any
