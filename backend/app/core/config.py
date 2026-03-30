from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # ── App ──
    APP_NAME: str = "Expense Tracker"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── Database ──
    DATABASE_URL: str
    SYNC_DATABASE_URL: str
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # ── Redis ──
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── S3 / MinIO ──
    S3_ENDPOINT_URL: str | None = None
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET_NAME: str = "expense-tracker"
    S3_REGION: str = "ap-south-1"

    # ── JWT ──
    JWT_PRIVATE_KEY_PATH: str = "./keys/jwt_private.pem"
    JWT_PUBLIC_KEY_PATH: str = "./keys/jwt_public.pem"
    JWT_ALGORITHM: str = "RS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Google OAuth2 ──
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # ── MSG91 ──
    MSG91_AUTH_KEY: str = ""
    MSG91_TEMPLATE_ID: str = ""

    # ── Frontend ──
    FRONTEND_URL: str = "http://localhost:5173"

    # ── Anthropic ──
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
    CLAUDE_DAILY_LIMIT_PER_USER: int = 10

    # ── Sentry ──
    SENTRY_DSN: str = ""

    # ── Celery ──
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
