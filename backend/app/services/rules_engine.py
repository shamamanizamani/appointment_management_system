"""§10 organisation rules. Lookup order: department override → org-wide value → default."""

import copy
from typing import Annotated, Any

from pydantic import Field, Strict, TypeAdapter, ValidationError
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Rule, User
from app.services import activity

_Int = Annotated[int, Strict()]
_Count = Annotated[int, Strict(), Field(ge=0)]
_Positive = Annotated[int, Strict(), Field(ge=1)]

# key -> (validator, default)
RULES: dict[str, tuple[TypeAdapter, Any]] = {
    "max_appointments_per_user_per_day": (TypeAdapter(_Positive), 2),
    "max_tokens_per_user": (TypeAdapter(_Positive), 2),
    "cancellation_limit": (TypeAdapter(_Count), 3),  # per customer per 7 days
    "early_checkin_minutes": (TypeAdapter(_Count), 10),
    "late_checkin_minutes": (TypeAdapter(_Count), 10),
    "max_recalls": (TypeAdapter(_Count), 2),
    "priority_services": (TypeAdapter(list[_Int]), []),
    "booking_window_days": (TypeAdapter(_Positive), 14),
}


def _check_key(key: str) -> None:
    if key not in RULES:
        raise AppError(404, "UNKNOWN_RULE", f"There is no rule called '{key}'.")


async def _rows(db: AsyncSession, department_id: int | None, key: str | None = None) -> dict:
    """{(key, is_department_row): value} for org rows plus this department's rows."""
    stmt = select(Rule).where(
        or_(Rule.department_id.is_(None), Rule.department_id == department_id)
    )
    if key:
        stmt = stmt.where(Rule.key == key)
    return {(r.key, r.department_id is not None): r.value for r in await db.scalars(stmt)}


def _resolve(rows: dict, key: str) -> tuple[Any, str]:
    if (key, True) in rows:
        return rows[(key, True)], "department"
    if (key, False) in rows:
        return rows[(key, False)], "org"
    return copy.deepcopy(RULES[key][1]), "default"


async def get(db: AsyncSession, key: str, department_id: int | None = None) -> Any:
    """The effective value of one rule. Use this everywhere a rule is enforced."""
    _check_key(key)
    return _resolve(await _rows(db, department_id, key), key)[0]


async def effective(db: AsyncSession, department_id: int | None) -> list[dict]:
    rows = await _rows(db, department_id)
    out = []
    for key in RULES:
        value, source = _resolve(rows, key)
        out.append({"key": key, "value": value, "source": source})
    return out


async def set_rule(
    db: AsyncSession, actor: User, key: str, department_id: int | None, value: Any
) -> dict:
    _check_key(key)
    try:
        value = RULES[key][0].validate_python(value)
    except ValidationError:
        raise AppError(
            422, "INVALID_RULE_VALUE", f"That isn't a valid value for '{key}'."
        ) from None
    rule = await db.scalar(
        select(Rule).where(Rule.key == key, Rule.department_id.is_not_distinct_from(department_id))
    )
    if rule:
        rule.value = value
    else:
        db.add(Rule(key=key, department_id=department_id, value=value))
    activity.log(db, actor, "update", "rule", department_id, {"key": key, "value": value})
    await db.commit()
    return {"key": key, "value": value, "source": "department" if department_id else "org"}


async def delete_rule(db: AsyncSession, actor: User, key: str, department_id: int | None) -> None:
    _check_key(key)
    await db.execute(
        delete(Rule).where(Rule.key == key, Rule.department_id.is_not_distinct_from(department_id))
    )
    activity.log(db, actor, "delete", "rule", department_id, {"key": key})
    await db.commit()
