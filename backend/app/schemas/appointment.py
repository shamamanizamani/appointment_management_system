from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.models import AppointmentStatus


class Slot(BaseModel):
    start: datetime
    end: datetime
    local_start: str
    local_end: str
    max: int
    booked: int
    status: Literal["available", "full", "past"]


class SlotGrid(BaseModel):
    service_id: int
    date: date
    timezone: str
    slot_length_min: int
    daily_limit: int | None
    booked_total: int
    slots: list[Slot]


class AvailableDate(BaseModel):
    date: date
    available_slots: int
    status: Literal["available", "full", "closed"]


class BookIn(BaseModel):
    service_id: int
    start: AwareDatetime  # a slot's `start` exactly as returned by /slots


class RescheduleIn(BaseModel):
    start: AwareDatetime


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    appointment_number: str
    user_id: int
    customer_name: str
    customer_phone: str | None
    service_id: int
    service_name: str
    service_code: str
    department_id: int
    department_name: str
    appointment_date: date
    start_time: datetime
    end_time: datetime
    status: AppointmentStatus
    check_in_time: datetime | None
    cancelled_at: datetime | None
    rescheduled_from_id: int | None
    created_at: datetime
