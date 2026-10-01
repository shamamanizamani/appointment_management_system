import os

# Point the app at the test database before anything imports app.core.db.
TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/queue_test"
)
assert "test" in TEST_DB.rsplit("/", 1)[-1], "Refusing to run tests against a non-test database"
os.environ["DATABASE_URL"] = TEST_DB

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core import time  # noqa: E402
from app.core.db import SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Role, User  # noqa: E402

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
