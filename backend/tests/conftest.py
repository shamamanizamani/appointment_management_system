import os
from datetime import UTC, datetime

# Point the app at the test database before anything imports app.core.db.
TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/queue_test"
)
assert "test" in TEST_DB.rsplit("/", 1)[-1], "Refusing to run tests against a non-test database"
os.environ["DATABASE_URL"] = TEST_DB
os.environ["BCRYPT_ROUNDS"] = "4"  # minimum cost; hashing dominates test time otherwise

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core import time  # noqa: E402
from app.core.db import SessionLocal, engine  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Department, Role, Service, SlotConfig, User  # noqa: E402
from app.schemas.org import DEFAULT_BREAKS, DEFAULT_WORKING_HOURS  # noqa: E402

PASSWORD = "Secret@123"


async def _create_test_db_if_missing() -> None:
    server, name = TEST_DB.replace("+asyncpg", "").rsplit("/", 1)
    conn = await asyncpg.connect(f"{server}/postgres")
    try:
        if not await conn.fetchval("select 1 from pg_database where datname = $1", name):
            await conn.execute(f'create database "{name}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
async def schema():
    await _create_test_db_if_missing()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_db():
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    time._frozen = None


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def make_user():
    async def _make(role: Role = Role.customer, email: str | None = None, **fields) -> User:
        async with SessionLocal() as db:
            user = User(
                name=f"Test {role}",
                email=email or f"{role}@example.com",
                role=role,
                password_hash=hash_password(PASSWORD),
                **fields,
            )
            db.add(user)
            await db.commit()
            return user

    return _make


@pytest.fixture
def login(client: AsyncClient):
    """login(email) -> Authorization headers for that user."""

    async def _login(email: str, password: str = PASSWORD) -> dict:
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login


# --- booking fixtures (Phase 3+) ---

# Monday 2026-10-05, 06:00 in Asia/Karachi (UTC+5): before opening, so the whole day is bookable.
MONDAY_6AM = datetime(2026, 10, 5, 1, 0, tzinfo=UTC)


@pytest.fixture
def frozen():
    """Freeze core.time.now() at MONDAY_6AM. clean_db unfreezes after each test."""
    time._frozen = MONDAY_6AM
    return MONDAY_6AM


def bearer(user: User) -> dict:
    """Auth headers without a login round-trip (fast for many users)."""
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


@pytest.fixture
def make_service():
    """A service (in a new 9-17 Mon-Fri department with a 13-14 break unless department_id
    is given) with 30-minute slots."""

    async def _make(
        code: str = "A",
        max_per_slot: int = 6,
        daily_limit: int | None = None,
        slot_length_min: int = 30,
        department_id: int | None = None,
    ) -> Service:
        async with SessionLocal() as db:
            if department_id is None:
                dept = Department(
                    name=f"Dept {code}",
                    code=f"D{code}",
                    working_hours=DEFAULT_WORKING_HOURS.model_dump(mode="json"),
                    break_windows=[b.model_dump(mode="json") for b in DEFAULT_BREAKS],
                )
                db.add(dept)
                await db.flush()
                department_id = dept.id
            service = Service(
                department_id=department_id,
                name=f"Service {code}",
                code=code,
                average_duration_min=10,
                slot_config=SlotConfig(
                    slot_length_min=slot_length_min,
                    max_per_slot=max_per_slot,
                    daily_limit=daily_limit,
                ),
            )
            db.add(service)
            await db.commit()
            return service

    return _make
