from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models import TokenSource, TokenStatus


class JoinIn(BaseModel):
    service_id: int


class TokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    token_number: str
    service_id: int
    service_name: str
    service_code: str
    department_id: int
    department_name: str
    user_id: int | None
    customer_name: str | None
    source: TokenSource
    appointment_id: int | None
    status: TokenStatus
    priority: bool
    recall_count: int
    counter_id: int | None
    queue_date: date
    queue_position: int | None
    people_ahead: int | None
    estimated_wait_min: int | None
    current_token: str | None
    created_at: datetime
    called_at: datetime | None
    service_started_at: datetime | None
    completed_at: datetime | None
