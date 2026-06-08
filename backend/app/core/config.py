"""Application settings — loaded from .env via Pydantic Settings."""

from functools import lru_cache
from typing import List

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    PROJECT_NAME: str = "BakeriQ"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    ALGORITHM: str = "HS256"

    # Database
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379

    # Celery uses Redis as both broker and result backend. Separate DB
    # numbers from the main Redis cache (DB 0) so a celery flush doesn't
    # nuke conversation state. DB 1 = broker, DB 2 = results.
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # Ollama runs natively on the host, reached via the Docker bridge
    # gateway IP from inside containers. See .env for full reasoning.
    OLLAMA_BASE_URL: str = "http://172.17.0.1:11434"

    # Pinned model. Bump this deliberately when we want to upgrade —
    # silent version drift would change parsing behavior without
    # anyone noticing.
    OLLAMA_MODEL: str = "llama3.2:3b"

    # Twilio (WhatsApp via sandbox in dev, real Sender in prod)
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"  # Sandbox default

    # Public base URL Twilio uses
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # Customer web app URL (for links in messages)
    CUSTOMER_WEB_BASE_URL: str = "http://localhost:5174"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = Field(default_factory=list)

    # Test database (separate from production db)
    POSTGRES_TEST_HOST: str = "db_test"
    POSTGRES_TEST_PORT: int = 5432
    POSTGRES_TEST_USER: str = "bakeriq_test"
    POSTGRES_TEST_PASSWORD: str = "bakeriq_test_password"
    POSTGRES_TEST_DB: str = "bakeriq_test"

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field
    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @computed_field
    @property
    def TEST_DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_TEST_USER}:{self.POSTGRES_TEST_PASSWORD}"
            f"@{self.POSTGRES_TEST_HOST}:{self.POSTGRES_TEST_PORT}/{self.POSTGRES_TEST_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return the singleton Settings instance.

    @lru_cache memoises so we read .env once per process, not on every call.
    Callers do `from app.core.config import settings` (module-level singleton
    via the assignment below) — get_settings() exists for tests that want
    to clear the cache and re-load with different env vars.
    """
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
