"""Demo accounts, one per role. Idempotent: existing accounts are left untouched.

Run: python -m scripts.seed
"""

import asyncio

from sqlalchemy import select

from app.core.db import SessionLocal, engine
from app.core.security import hash_password
from app.models import Role, User

DEMO_PASSWORD = "Demo@1234"
DEMO_USERS = [
    ("Demo Customer", "customer@demo.com", Role.customer),
    ("Demo Staff", "staff@demo.com", Role.staff),
    ("Demo Manager", "manager@demo.com", Role.manager),
    ("Demo Admin", "admin@demo.com", Role.admin),
]


async def seed() -> None:
    async with SessionLocal() as db:
        existing = set(await db.scalars(select(User.email)))
        for name, email, role in DEMO_USERS:
            if email in existing:
                print(f"exists   {email}")
                continue
            db.add(
                User(name=name, email=email, role=role, password_hash=hash_password(DEMO_PASSWORD))
            )
            print(f"created  {email} ({role})")
        await db.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
