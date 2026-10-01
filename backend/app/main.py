from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import admin, auth
from app.core.deps import get_db
from app.core.errors import register_error_handlers
from app.core.time import now

app = FastAPI(title="Digital Queue & Appointment API", version="0.1.0")

# A native Android app doesn't use CORS; this only lets /docs and test pages work from browsers.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
register_error_handlers(app)

for module in (auth, admin):
    app.include_router(module.router, prefix="/api/v1")


@app.get("/health", summary="Health check (also checks the database)", tags=["system"])
async def health(db: AsyncSession = Depends(get_db)):
    await db.execute(text("select 1"))
    return {"status": "ok", "time": now()}
