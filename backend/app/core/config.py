from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/queue"
    jwt_secret: str = "dev-only-secret-change-me-in-production-0123456789"
    access_token_minutes: int = 30
    refresh_token_days: int = 7

    @field_validator("database_url")
    @classmethod
    def use_asyncpg(cls, v: str) -> str:
        # Render/Railway hand out postgres:// URLs; SQLAlchemy async needs the asyncpg driver.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                v = "postgresql+asyncpg://" + v.removeprefix(prefix)
        return v.replace("sslmode=", "ssl=")  # asyncpg spells it "ssl"


settings = Settings()
