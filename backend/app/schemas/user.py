from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.models import AccountStatus, Role

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+?[0-9]{7,15}$")]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    phone: str | None
    role: Role
    department_id: int | None
    account_status: AccountStatus
    created_at: datetime


class UserUpdate(BaseModel):
    name: Name | None = None
    phone: Phone | None = None  # send null to clear
