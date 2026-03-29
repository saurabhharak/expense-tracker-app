# Sprint 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fully Dockerized dev environment with FastAPI backend, complete database schema (13 tables, RLS on all data tables), and verified tenant isolation.

**Architecture:** Bottom-up — Docker infrastructure first, then FastAPI backend scaffolding, then Alembic migrations with RLS. Every step verifiable against running services. Dual DB engines (async for FastAPI, sync for Celery). All tables in `expense_tracker` schema.

**Tech Stack:** FastAPI 0.115, SQLAlchemy 2.0 (async), Alembic, PostgreSQL 16, PgBouncer, Redis 7, MinIO (S3), Celery 5.4, Docker Compose, Python 3.12

**Spec:** `docs/superpowers/specs/2026-03-29-sprint1-foundation-design.md`
**Schema Reference:** `docs/architecture.md` sections 5.1–5.14 (canonical SQL definitions)

**Note on migration count:** Spec listed 11 migrations with a separate 010 for functions. This plan consolidates to 10 migrations by embedding functions where they're first needed: `update_updated_at()` in 001 (users), `update_account_balance()` in 004 (transactions), `get_fy_year()`/`get_fy_range()` in 006 (budgets). This keeps each migration self-contained.

---

## File Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # App factory, lifespan, health endpoint
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # Pydantic Settings
│   │   ├── database.py            # Async + sync engines, RLS context
│   │   ├── redis.py               # Redis async client
│   │   ├── storage.py             # S3/MinIO client
│   │   ├── middleware.py          # Request ID, timing, security headers
│   │   └── exceptions.py         # Custom exceptions + handlers
│   └── tasks/
│       ├── __init__.py
│       └── celery_app.py          # Celery factory (placeholder)
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   └── test_health.py
│   └── integration/
│       ├── __init__.py
│       └── test_rls_isolation.py
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 001_users.py
│       ├── 002_categories.py
│       ├── 003_accounts.py
│       ├── 004_transactions.py
│       ├── 005_recurring.py
│       ├── 006_budgets.py
│       ├── 007_investments.py
│       ├── 008_screenshots.py
│       ├── 009_audit.py
│       └── 010_seed_categories.py
├── alembic.ini
├── pyproject.toml
├── Dockerfile
├── scripts/
│   └── entrypoint.sh
└── requirements/
    ├── base.txt
    ├── dev.txt
    └── prod.txt

docker/
├── docker-compose.yml
├── docker-compose.prod.yml
├── postgres/
│   └── init.sql
├── pgbouncer/
│   └── pgbouncer.ini
├── redis/
│   └── redis.conf
└── caddy/
    └── Caddyfile

.env.example
```

---

## Phase A: Infrastructure

### Task 1: Docker Compose Dev Stack

**Files:**
- Create: `docker/docker-compose.yml`
- Create: `docker/postgres/init.sql`
- Create: `docker/redis/redis.conf`
- Create: `docker/pgbouncer/pgbouncer.ini`

- [ ] **Step 1: Create Postgres init script**

Create `docker/postgres/init.sql`:

```sql
-- Create application database (Docker entrypoint handles this via POSTGRES_DB,
-- but we need the schema, extensions, and roles)

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Application schema
CREATE SCHEMA IF NOT EXISTS expense_tracker;

-- Application role (used at runtime, RLS applies)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user LOGIN PASSWORD 'app_password_dev';
    END IF;
END
$$;

-- Grant schema access
GRANT USAGE, CREATE ON SCHEMA expense_tracker TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA expense_tracker GRANT ALL ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA expense_tracker GRANT ALL ON SEQUENCES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA expense_tracker GRANT EXECUTE ON FUNCTIONS TO app_user;

-- Set default search_path for app_user
ALTER ROLE app_user SET search_path TO expense_tracker, public;

-- RLS helper function
CREATE OR REPLACE FUNCTION expense_tracker.current_app_user_id()
RETURNS uuid AS $$
BEGIN
    RETURN current_setting('app.current_user_id', true)::uuid;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- Grant execute on the function
GRANT EXECUTE ON FUNCTION expense_tracker.current_app_user_id() TO app_user;
```

- [ ] **Step 2: Create Redis config**

Create `docker/redis/redis.conf`:

```
# Redis 7 configuration for expense tracker dev
bind 0.0.0.0
port 6379
maxmemory 256mb
maxmemory-policy allkeys-lru

# AOF persistence
appendonly yes
appendfsync everysec
appendfilename "appendonly.aof"

# Logging
loglevel notice
```

- [ ] **Step 3: Create PgBouncer config**

Create `docker/pgbouncer/pgbouncer.ini`:

```ini
[databases]
expense_tracker = host=postgres port=5432 dbname=expense_tracker

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 200
default_pool_size = 20
min_pool_size = 5
reserve_pool_size = 5
server_reset_query = DISCARD ALL
log_connections = 0
log_disconnections = 0
```

- [ ] **Step 4: Create Docker Compose dev file**

Create `docker/docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: expense_tracker
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres_dev
    ports:
      - "5433:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/01-init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d expense_tracker"]
      interval: 5s
      timeout: 5s
      retries: 5

  pgbouncer:
    image: bitnami/pgbouncer:latest
    environment:
      POSTGRESQL_HOST: postgres
      POSTGRESQL_PORT: 5432
      POSTGRESQL_DATABASE: expense_tracker
      POSTGRESQL_USERNAME: postgres
      POSTGRESQL_PASSWORD: postgres_dev
      PGBOUNCER_PORT: 6432
      PGBOUNCER_POOL_MODE: transaction
      PGBOUNCER_MAX_CLIENT_CONN: 200
      PGBOUNCER_DEFAULT_POOL_SIZE: 20
    ports:
      - "6432:6432"
    depends_on:
      postgres:
        condition: service_healthy

  redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"
    volumes:
      - redis_data:/data
      - ./redis/redis.conf:/usr/local/etc/redis/redis.conf
    command: redis-server /usr/local/etc/redis/redis.conf
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  minio:
    image: minio/minio:latest
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin123
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ../backend
      dockerfile: Dockerfile
      target: dev
    environment:
      - APP_NAME=Expense Tracker
      - DEBUG=true
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres_dev@postgres:5432/expense_tracker
      - SYNC_DATABASE_URL=postgresql://postgres:postgres_dev@postgres:5432/expense_tracker
      - REDIS_URL=redis://redis:6379/0
      - S3_ENDPOINT_URL=http://minio:9000
      - S3_ACCESS_KEY=minioadmin
      - S3_SECRET_KEY=minioadmin123
      - S3_BUCKET_NAME=expense-tracker
      - S3_REGION=us-east-1
    ports:
      - "8000:8000"
    volumes:
      - ../backend/app:/app/app
      - ../backend/alembic:/app/alembic
      - ../backend/alembic.ini:/app/alembic.ini
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  celery-worker:
    build:
      context: ../backend
      dockerfile: Dockerfile
      target: dev
    environment:
      - SYNC_DATABASE_URL=postgresql://postgres:postgres_dev@postgres:5432/expense_tracker
      - REDIS_URL=redis://redis:6379/0
      - S3_ENDPOINT_URL=http://minio:9000
      - S3_ACCESS_KEY=minioadmin
      - S3_SECRET_KEY=minioadmin123
      - S3_BUCKET_NAME=expense-tracker
    volumes:
      - ../backend/app:/app/app
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: celery -A app.tasks.celery_app worker --loglevel=info -Q default,screenshots

  celery-beat:
    build:
      context: ../backend
      dockerfile: Dockerfile
      target: dev
    environment:
      - SYNC_DATABASE_URL=postgresql://postgres:postgres_dev@postgres:5432/expense_tracker
      - REDIS_URL=redis://redis:6379/0
    volumes:
      - ../backend/app:/app/app
    depends_on:
      redis:
        condition: service_healthy
    command: celery -A app.tasks.celery_app beat --loglevel=info

  flower:
    image: mher/flower:latest
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
    ports:
      - "5555:5555"
    depends_on:
      redis:
        condition: service_healthy

volumes:
  postgres_data:
  redis_data:
  minio_data:
```

- [ ] **Step 5: Verify compose file is valid**

Run: `cd docker && docker compose config --quiet`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add docker/
git commit -m "feat: add Docker Compose dev stack with Postgres, Redis, MinIO, PgBouncer"
```

---

### Task 2: Environment Configuration

**Files:**
- Create: `.env.example`

- [ ] **Step 1: Create .env.example**

Create `.env.example` at project root:

```bash
# ============================================================
# Expense Tracker — Environment Variables
# Copy to .env and fill in actual values
# ============================================================

# ── App ──
APP_NAME="Expense Tracker"
DEBUG=true
API_V1_PREFIX=/api/v1
ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:5173"]

# ── Database (async for FastAPI) ──
DATABASE_URL=postgresql+asyncpg://postgres:postgres_dev@localhost:5433/expense_tracker
# ── Database (sync for Celery) ──
SYNC_DATABASE_URL=postgresql://postgres:postgres_dev@localhost:5433/expense_tracker
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10

# ── Redis ──
REDIS_URL=redis://localhost:6380/0

# ── S3 / MinIO ──
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin123
S3_BUCKET_NAME=expense-tracker
S3_REGION=us-east-1

# ── JWT (generate with: openssl genrsa -out jwt_private.pem 2048) ──
JWT_PRIVATE_KEY_PATH=./keys/jwt_private.pem
JWT_PUBLIC_KEY_PATH=./keys/jwt_public.pem
JWT_ALGORITHM=RS256
ACCESS_TOKEN_EXPIRE_MINUTES=15

# ── Google OAuth2 ──
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# ── MSG91 (Phone OTP) ──
MSG91_AUTH_KEY=your-msg91-auth-key
MSG91_TEMPLATE_ID=your-template-id

# ── Anthropic (Claude Vision) ──
ANTHROPIC_API_KEY=your-anthropic-api-key
CLAUDE_MODEL=claude-sonnet-4-20250514
CLAUDE_DAILY_LIMIT_PER_USER=10

# ── Sentry ──
SENTRY_DSN=

# ── Celery ──
CELERY_BROKER_URL=redis://localhost:6380/0
CELERY_RESULT_BACKEND=redis://localhost:6380/1
```

- [ ] **Step 2: Create .gitignore additions**

Append to `.gitignore` at project root (create if doesn't exist):

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.eggs/
*.egg
.venv/
venv/

# Environment
.env
*.pem

# Keys
keys/

# Docker volumes
postgres_data/
redis_data/
minio_data/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Test
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.ruff_cache/
```

- [ ] **Step 3: Commit**

```bash
git add .env.example .gitignore
git commit -m "feat: add .env.example and .gitignore"
```

---

### Task 3: Backend Dockerfile + Entrypoint

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/scripts/entrypoint.sh`

- [ ] **Step 1: Create entrypoint script**

Create `backend/scripts/entrypoint.sh`:

```bash
#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec "$@"
```

- [ ] **Step 2: Create Dockerfile**

Create `backend/Dockerfile`:

```dockerfile
# ── Builder stage ──
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
RUN pip install --no-cache-dir --prefix=/install -r requirements/base.txt

# ── Dev stage (used by docker-compose.yml) ──
FROM python:3.12-slim AS dev

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/dev.txt

COPY . .
RUN chmod +x scripts/entrypoint.sh

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Production stage ──
FROM python:3.12-slim AS prod

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY --from=builder /install /usr/local

COPY requirements/prod.txt requirements/prod.txt
RUN pip install --no-cache-dir -r requirements/prod.txt

COPY . .
RUN chmod +x scripts/entrypoint.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["./scripts/entrypoint.sh"]
CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
```

- [ ] **Step 3: Commit**

```bash
git add backend/Dockerfile backend/scripts/
git commit -m "feat: add multi-stage Dockerfile with dev and prod targets"
```

---

### Task 4: Docker Compose Prod + Caddyfile

**Files:**
- Create: `docker/docker-compose.prod.yml`
- Create: `docker/caddy/Caddyfile`

- [ ] **Step 1: Create Caddyfile**

Create `docker/caddy/Caddyfile`:

```
{$DOMAIN:localhost} {
    # API reverse proxy
    handle /api/* {
        reverse_proxy backend:8000
    }

    # Health check (no auth)
    handle /api/v1/health {
        reverse_proxy backend:8000
    }

    # SPA fallback — serve frontend, fallback to index.html
    handle {
        root * /srv
        try_files {path} /index.html
        file_server
    }

    # Security headers
    header {
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        X-XSS-Protection "0"
        Referrer-Policy strict-origin-when-cross-origin
        -Server
    }

    # Compression
    encode gzip zstd
}
```

- [ ] **Step 2: Create prod compose overrides**

Create `docker/docker-compose.prod.yml`:

```yaml
services:
  backend:
    build:
      target: prod
    command: ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
    volumes: []
    environment:
      - DEBUG=false
    restart: unless-stopped

  celery-worker:
    build:
      target: prod
    volumes: []
    restart: unless-stopped

  celery-beat:
    build:
      target: prod
    volumes: []
    restart: unless-stopped

  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./caddy/Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - backend
    restart: unless-stopped

  postgres:
    restart: unless-stopped

  redis:
    restart: unless-stopped

volumes:
  caddy_data:
  caddy_config:
```

- [ ] **Step 3: Commit**

```bash
git add docker/docker-compose.prod.yml docker/caddy/
git commit -m "feat: add production Docker Compose with Caddy reverse proxy"
```

---

## Phase B: Backend Core

### Task 5: Python Project Setup

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/requirements/base.txt`
- Create: `backend/requirements/dev.txt`
- Create: `backend/requirements/prod.txt`

- [ ] **Step 1: Create requirements/base.txt**

Create `backend/requirements/base.txt`:

```
fastapi==0.115.*
uvicorn[standard]==0.34.*
sqlalchemy[asyncio]==2.0.*
asyncpg==0.30.*
psycopg2-binary==2.9.*
alembic==1.14.*
pydantic==2.10.*
pydantic-settings==2.*
celery[redis]==5.4.*
redis==5.*
boto3==1.36.*
httpx==0.28.*
python-jose[cryptography]==3.3.*
passlib[bcrypt]==1.7.*
anthropic==0.42.*
pillow==11.*
structlog==24.*
python-multipart==0.0.*
```

- [ ] **Step 2: Create requirements/dev.txt**

Create `backend/requirements/dev.txt`:

```
-r base.txt
pytest==8.*
pytest-asyncio==0.24.*
pytest-cov==5.*
httpx==0.28.*
ruff==0.8.*
mypy==1.13.*
factory-boy==3.*
```

- [ ] **Step 3: Create requirements/prod.txt**

Create `backend/requirements/prod.txt`:

```
-r base.txt
gunicorn==23.*
sentry-sdk[fastapi,sqlalchemy,celery]==2.*
prometheus-fastapi-instrumentator==7.*
```

- [ ] **Step 4: Create pyproject.toml**

Create `backend/pyproject.toml`:

```toml
[project]
name = "expense-tracker-backend"
version = "0.1.0"
description = "Personal Expense Tracker API"
requires-python = ">=3.12"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
filterwarnings = ["ignore::DeprecationWarning"]
```

- [ ] **Step 5: Create package __init__.py files**

Create these empty files:
- `backend/app/__init__.py`
- `backend/app/core/__init__.py`
- `backend/app/tasks/__init__.py`
- `backend/tests/__init__.py`
- `backend/tests/unit/__init__.py`
- `backend/tests/integration/__init__.py`

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/requirements/ backend/app/__init__.py backend/app/core/__init__.py backend/app/tasks/__init__.py backend/tests/
git commit -m "feat: add Python project config with dependencies and package structure"
```

---

### Task 6: Pydantic Settings

**Files:**
- Create: `backend/app/core/config.py`

- [ ] **Step 1: Create config.py**

Create `backend/app/core/config.py`:

```python
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

    # ── Google OAuth2 ──
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # ── MSG91 ──
    MSG91_AUTH_KEY: str = ""
    MSG91_TEMPLATE_ID: str = ""

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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/config.py
git commit -m "feat: add Pydantic settings with all env var groups"
```

---

### Task 7: Database Module

**Files:**
- Create: `backend/app/core/database.py`

- [ ] **Step 1: Create database.py**

Create `backend/app/core/database.py`:

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

# ── Async engine (FastAPI routes) ──
async_engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    connect_args={"prepared_statement_cache_size": 0},  # PgBouncer compatibility
)
async_session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

# ── Sync engine (Celery tasks) ──
sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
)
sync_session_factory = sessionmaker(sync_engine, expire_on_commit=False)

# ── Base for models ──
Base = declarative_base()


@asynccontextmanager
async def get_db_session(user_id: str | None = None) -> AsyncGenerator[AsyncSession, None]:
    """Async session with RLS context. Used by FastAPI routes."""
    async with async_session_factory() as session:
        async with session.begin():
            if user_id:
                await session.execute(
                    text("SET LOCAL app.current_user_id = :uid"),
                    {"uid": user_id},
                )
            yield session


@contextmanager
def sync_db_session(user_id: str | None = None):
    """Sync session with RLS context. Used by Celery tasks."""
    session: Session = sync_session_factory()
    try:
        session.begin()
        if user_id:
            session.execute(
                text("SET LOCAL app.current_user_id = :uid"),
                {"uid": user_id},
            )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/database.py
git commit -m "feat: add dual DB engine setup with RLS context managers"
```

---

### Task 8: Redis Module

**Files:**
- Create: `backend/app/core/redis.py`

- [ ] **Step 1: Create redis.py**

Create `backend/app/core/redis.py`:

```python
from redis.asyncio import Redis

from app.core.config import settings

redis_client: Redis | None = None


async def init_redis() -> Redis:
    """Initialize Redis connection. Call on app startup."""
    global redis_client
    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return redis_client


async def close_redis() -> None:
    """Close Redis connection. Call on app shutdown."""
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None


def get_redis() -> Redis:
    """Get the Redis client. Raises if not initialized."""
    if redis_client is None:
        raise RuntimeError("Redis client not initialized. Call init_redis() first.")
    return redis_client
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/redis.py
git commit -m "feat: add Redis async client singleton"
```

---

### Task 9: S3 Storage Module

**Files:**
- Create: `backend/app/core/storage.py`

- [ ] **Step 1: Create storage.py**

Create `backend/app/core/storage.py`:

```python
import boto3
from botocore.exceptions import ClientError

from app.core.config import settings


def get_s3_client():
    """Create boto3 S3 client configured for MinIO in dev."""
    kwargs = {
        "aws_access_key_id": settings.S3_ACCESS_KEY,
        "aws_secret_access_key": settings.S3_SECRET_KEY,
        "region_name": settings.S3_REGION,
    }
    if settings.S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
    return boto3.client("s3", **kwargs)


def ensure_bucket_exists(client=None) -> None:
    """Create the S3 bucket if it doesn't exist."""
    client = client or get_s3_client()
    try:
        client.head_bucket(Bucket=settings.S3_BUCKET_NAME)
    except ClientError:
        client.create_bucket(Bucket=settings.S3_BUCKET_NAME)


def upload_file(file_bytes: bytes, key: str, content_type: str, client=None) -> str:
    """Upload file to S3. Returns the key."""
    client = client or get_s3_client()
    client.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )
    return key


def generate_presigned_url(key: str, expires_in: int = 3600, client=None) -> str:
    """Generate a presigned download URL."""
    client = client or get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )


def delete_file(key: str, client=None) -> None:
    """Delete a file from S3."""
    client = client or get_s3_client()
    client.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/storage.py
git commit -m "feat: add S3/MinIO storage client"
```

---

### Task 10: Exceptions + Middleware

**Files:**
- Create: `backend/app/core/exceptions.py`
- Create: `backend/app/core/middleware.py`

- [ ] **Step 1: Create exceptions.py**

Create `backend/app/core/exceptions.py`:

```python
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


class NotFoundError(AppException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(404, detail)


class ForbiddenError(AppException):
    def __init__(self, detail: str = "Forbidden"):
        super().__init__(403, detail)


class ConflictError(AppException):
    def __init__(self, detail: str = "Conflict"):
        super().__init__(409, detail)


class RateLimitError(AppException):
    def __init__(self, detail: str = "Rate limit exceeded"):
        super().__init__(429, detail)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {"code": exc.status_code, "message": exc.detail},
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {"code": exc.status_code, "message": exc.detail},
        },
    )
```

- [ ] **Step 2: Create middleware.py**

Create `backend/app/core/middleware.py`:

```python
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger()


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        await logger.ainfo(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/exceptions.py backend/app/core/middleware.py
git commit -m "feat: add custom exceptions and middleware (request ID, timing, security headers)"
```

---

### Task 11: Celery Placeholder

**Files:**
- Create: `backend/app/tasks/celery_app.py`

- [ ] **Step 1: Create celery_app.py**

Create `backend/app/tasks/celery_app.py`:

```python
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "expense_tracker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_routes={
        "app.tasks.screenshot_tasks.*": {"queue": "screenshots"},
        "app.tasks.*": {"queue": "default"},
    },
)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/tasks/celery_app.py
git commit -m "feat: add Celery app factory placeholder"
```

---

### Task 12: FastAPI App Factory + Health Endpoint (TDD)

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/unit/test_health.py`

- [ ] **Step 1: Write health endpoint test**

Create `backend/tests/conftest.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

Create `backend/tests/unit/test_health.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded", "unhealthy")
    assert "checks" in data


@pytest.mark.asyncio
async def test_health_endpoint_has_check_keys(client):
    response = await client.get("/api/v1/health")
    data = response.json()
    checks = data["checks"]
    assert "db" in checks
    assert "redis" in checks
    assert "s3" in checks
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/unit/test_health.py -v`
Expected: FAIL (ModuleNotFoundError — app.main doesn't exist yet)

- [ ] **Step 3: Create app factory (main.py)**

Create `backend/app/main.py`:

```python
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_engine
from app.core.exceptions import AppException, app_exception_handler, http_exception_handler
from app.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware, TimingMiddleware
from app.core.redis import close_redis, get_redis, init_redis
from app.core.storage import ensure_bucket_exists, get_s3_client

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if settings.DEBUG else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    await init_redis()
    try:
        ensure_bucket_exists()
    except Exception as e:
        await logger.awarning("s3_init_failed", error=str(e))
    await logger.ainfo("app_started", app_name=settings.APP_NAME)

    yield

    # ── Shutdown ──
    await close_redis()
    await async_engine.dispose()
    await logger.ainfo("app_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        lifespan=lifespan,
        docs_url="/api/v1/docs" if settings.DEBUG else None,
        redoc_url="/api/v1/redoc" if settings.DEBUG else None,
    )

    # ── Exception handlers ──
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)

    # ── Middleware (order matters: outermost first) ──
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Health endpoint ──
    @app.get(f"{settings.API_V1_PREFIX}/health")
    async def health_check():
        checks = {"db": False, "redis": False, "s3": False}
        try:
            async with async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["db"] = True
        except Exception:
            pass

        try:
            redis = get_redis()
            await redis.ping()
            checks["redis"] = True
        except Exception:
            pass

        try:
            client = get_s3_client()
            client.head_bucket(Bucket=settings.S3_BUCKET_NAME)
            checks["s3"] = True
        except Exception:
            pass

        all_healthy = all(checks.values())
        any_healthy = any(checks.values())
        status = "healthy" if all_healthy else ("degraded" if any_healthy else "unhealthy")
        return {"status": status, "checks": checks}

    return app


app = create_app()
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/unit/test_health.py -v`
Expected: PASS (health endpoint returns correct shape, services may be down in test)

Note: In unit tests without running services, the health check will return `unhealthy` — that's correct behavior. The test only validates response shape.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/conftest.py backend/tests/unit/test_health.py
git commit -m "feat: add FastAPI app factory with health endpoint (TDD)"
```

---

## Phase C: Alembic + Migrations

### Task 13: Alembic Configuration

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/.gitkeep`

- [ ] **Step 1: Create alembic.ini**

Create `backend/alembic.ini`:

```ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql://postgres:postgres_dev@localhost:5433/expense_tracker

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Create env.py**

Create `backend/alembic/env.py`:

```python
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL from environment if available
db_url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
# Ensure async driver for online migrations
if db_url and "asyncpg" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

target_metadata = None


def run_migrations_offline() -> None:
    context.configure(url=db_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    # Set search_path to expense_tracker schema
    connection.execute(text("SET search_path TO expense_tracker, public"))
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = create_async_engine(db_url, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Create script template**

Create `backend/alembic/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Create versions directory**

Create `backend/alembic/versions/.gitkeep` (empty file).

- [ ] **Step 5: Commit**

```bash
git add backend/alembic.ini backend/alembic/
git commit -m "feat: configure Alembic for async PostgreSQL migrations"
```

---

### Task 14: Migration 001 — Users + Refresh Tokens

**Files:**
- Create: `backend/alembic/versions/001_users.py`

- [ ] **Step 1: Create migration file**

Create `backend/alembic/versions/001_users.py`:

```python
"""Create users and refresh_tokens tables

Revision ID: 001
Revises: None
Create Date: 2026-03-29
"""
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    -- updated_at trigger function (reused by all tables)
    CREATE OR REPLACE FUNCTION expense_tracker.update_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = now();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    -- ── USERS ──
    CREATE TABLE expense_tracker.users (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        email           VARCHAR(255) UNIQUE,
        phone           VARCHAR(15) UNIQUE,
        google_id       VARCHAR(255) UNIQUE,
        password_hash   VARCHAR(255),
        full_name       VARCHAR(255) NOT NULL,
        avatar_url      VARCHAR(1024),
        preferences     JSONB NOT NULL DEFAULT '{
            "currency": "INR",
            "fy_start_month": 4,
            "default_account_id": null,
            "screenshot_auto_confirm": false,
            "budget_alert_threshold": 80,
            "theme": "light"
        }'::jsonb,
        is_active       BOOLEAN NOT NULL DEFAULT true,
        email_verified  BOOLEAN NOT NULL DEFAULT false,
        phone_verified  BOOLEAN NOT NULL DEFAULT false,
        daily_api_cost_limit_paise INTEGER NOT NULL DEFAULT 500,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    ALTER TABLE expense_tracker.users ADD CONSTRAINT chk_auth_method
        CHECK (email IS NOT NULL OR phone IS NOT NULL OR google_id IS NOT NULL);

    CREATE INDEX idx_users_email ON expense_tracker.users (email) WHERE email IS NOT NULL;
    CREATE INDEX idx_users_phone ON expense_tracker.users (phone) WHERE phone IS NOT NULL;
    CREATE INDEX idx_users_google_id ON expense_tracker.users (google_id) WHERE google_id IS NOT NULL;

    CREATE TRIGGER trg_users_updated_at
        BEFORE UPDATE ON expense_tracker.users
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at();

    -- ── REFRESH TOKENS ──
    CREATE TABLE expense_tracker.refresh_tokens (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        token_hash      VARCHAR(128) NOT NULL UNIQUE,
        expires_at      TIMESTAMPTZ NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        revoked_at      TIMESTAMPTZ,
        replaced_by     UUID REFERENCES expense_tracker.refresh_tokens(id),
        user_agent      VARCHAR(512),
        ip_address      INET
    );

    CREATE INDEX idx_refresh_tokens_user_id ON expense_tracker.refresh_tokens (user_id);
    CREATE INDEX idx_refresh_tokens_token_hash ON expense_tracker.refresh_tokens (token_hash) WHERE revoked_at IS NULL;
    CREATE INDEX idx_refresh_tokens_expires ON expense_tracker.refresh_tokens (expires_at) WHERE revoked_at IS NULL;
    """)

def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS expense_tracker.refresh_tokens CASCADE;
    DROP TABLE IF EXISTS expense_tracker.users CASCADE;
    DROP FUNCTION IF EXISTS expense_tracker.update_updated_at();
    """)
```

- [ ] **Step 2: Run migration**

Run: `docker compose -f docker/docker-compose.yml exec backend alembic upgrade head`
(Or from host: `cd backend && DATABASE_URL=postgresql+asyncpg://postgres:postgres_dev@localhost:5433/expense_tracker alembic upgrade head`)

Expected: "Running upgrade  -> 001, Create users and refresh_tokens tables"

- [ ] **Step 3: Verify tables exist**

Run: `docker compose -f docker/docker-compose.yml exec postgres psql -U postgres -d expense_tracker -c "\dt expense_tracker.*"`

Expected: users and refresh_tokens tables listed

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/001_users.py
git commit -m "feat: migration 001 — users and refresh_tokens tables"
```

---

### Task 15: Migration 002 — Categories + RLS

**Files:**
- Create: `backend/alembic/versions/002_categories.py`

- [ ] **Step 1: Create migration file**

Create `backend/alembic/versions/002_categories.py`:

```python
"""Create categories table with RLS

Revision ID: 002
Revises: 001
Create Date: 2026-03-29
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TYPE expense_tracker.category_type AS ENUM ('income', 'expense');

    CREATE TABLE expense_tracker.categories (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        parent_id       UUID REFERENCES expense_tracker.categories(id) ON DELETE CASCADE,
        name            VARCHAR(100) NOT NULL,
        type            expense_tracker.category_type NOT NULL,
        icon            VARCHAR(50),
        color           VARCHAR(7),
        is_system       BOOLEAN NOT NULL DEFAULT false,
        sort_order      INTEGER NOT NULL DEFAULT 0,
        is_active       BOOLEAN NOT NULL DEFAULT true,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE UNIQUE INDEX idx_categories_unique_name
        ON expense_tracker.categories (
            COALESCE(user_id, '00000000-0000-0000-0000-000000000000'),
            COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'),
            type, lower(name)
        );

    CREATE INDEX idx_categories_user_id ON expense_tracker.categories (user_id);
    CREATE INDEX idx_categories_parent_id ON expense_tracker.categories (parent_id);

    -- RLS: users see system categories (user_id IS NULL) + their own
    ALTER TABLE expense_tracker.categories ENABLE ROW LEVEL SECURITY;
    ALTER TABLE expense_tracker.categories FORCE ROW LEVEL SECURITY;

    CREATE POLICY categories_select ON expense_tracker.categories FOR SELECT TO app_user
        USING (user_id IS NULL OR user_id = expense_tracker.current_app_user_id());
    CREATE POLICY categories_insert ON expense_tracker.categories FOR INSERT TO app_user
        WITH CHECK (user_id = expense_tracker.current_app_user_id());
    CREATE POLICY categories_update ON expense_tracker.categories FOR UPDATE TO app_user
        USING (user_id = expense_tracker.current_app_user_id() AND is_system = false);
    CREATE POLICY categories_delete ON expense_tracker.categories FOR DELETE TO app_user
        USING (user_id = expense_tracker.current_app_user_id() AND is_system = false);

    CREATE TRIGGER trg_categories_updated_at
        BEFORE UPDATE ON expense_tracker.categories
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at();
    """)

def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS expense_tracker.categories CASCADE;
    DROP TYPE IF EXISTS expense_tracker.category_type;
    """)
```

- [ ] **Step 2: Run migration and verify**

Run: `cd backend && alembic upgrade head`
Expected: "Running upgrade 001 -> 002"

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/002_categories.py
git commit -m "feat: migration 002 — categories table with hierarchical RLS"
```

---

### Task 16: Migration 003 — Accounts + RLS

**Files:**
- Create: `backend/alembic/versions/003_accounts.py`

- [ ] **Step 1: Create migration file**

Create `backend/alembic/versions/003_accounts.py`:

```python
"""Create accounts table with RLS

Revision ID: 003
Revises: 002
Create Date: 2026-03-29
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TYPE expense_tracker.account_type AS ENUM (
        'savings', 'current', 'credit_card', 'wallet', 'cash', 'loan'
    );

    CREATE TABLE expense_tracker.accounts (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        name            VARCHAR(100) NOT NULL,
        type            expense_tracker.account_type NOT NULL,
        bank_name       VARCHAR(100),
        balance         DECIMAL(14,2) NOT NULL DEFAULT 0,
        credit_limit    DECIMAL(14,2),
        billing_day     SMALLINT CHECK (billing_day BETWEEN 1 AND 31),
        icon            VARCHAR(50),
        color           VARCHAR(7),
        is_active       BOOLEAN NOT NULL DEFAULT true,
        is_default      BOOLEAN NOT NULL DEFAULT false,
        sort_order      INTEGER NOT NULL DEFAULT 0,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX idx_accounts_user_id ON expense_tracker.accounts (user_id);
    CREATE UNIQUE INDEX idx_accounts_default
        ON expense_tracker.accounts (user_id) WHERE is_default = true AND is_active = true;

    ALTER TABLE expense_tracker.accounts ENABLE ROW LEVEL SECURITY;
    ALTER TABLE expense_tracker.accounts FORCE ROW LEVEL SECURITY;

    CREATE POLICY accounts_all ON expense_tracker.accounts FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id());

    CREATE TRIGGER trg_accounts_updated_at
        BEFORE UPDATE ON expense_tracker.accounts
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at();
    """)

def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS expense_tracker.accounts CASCADE;
    DROP TYPE IF EXISTS expense_tracker.account_type;
    """)
```

- [ ] **Step 2: Run migration and verify**

Run: `cd backend && alembic upgrade head`
Expected: "Running upgrade 002 -> 003"

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/003_accounts.py
git commit -m "feat: migration 003 — accounts table with RLS"
```

---

### Task 17: Migration 004 — Transactions + Balance Trigger + RLS

**Files:**
- Create: `backend/alembic/versions/004_transactions.py`

Note: `screenshot_parse_log_id` and `recurring_transaction_id` columns are created here but FK constraints are deferred to migrations 005 and 010 (after the referenced tables exist).

- [ ] **Step 1: Create migration file**

Create `backend/alembic/versions/004_transactions.py`:

```python
"""Create transactions table with balance trigger and RLS

Revision ID: 004
Revises: 003
Create Date: 2026-03-29
"""
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TYPE expense_tracker.transaction_type AS ENUM ('income', 'expense', 'transfer');

    CREATE TABLE expense_tracker.transactions (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        account_id      UUID NOT NULL REFERENCES expense_tracker.accounts(id) ON DELETE RESTRICT,
        category_id     UUID REFERENCES expense_tracker.categories(id) ON DELETE SET NULL,
        type            expense_tracker.transaction_type NOT NULL,
        amount          DECIMAL(12,2) NOT NULL CHECK (amount > 0),
        to_account_id   UUID REFERENCES expense_tracker.accounts(id) ON DELETE RESTRICT,
        description     VARCHAR(500),
        notes           TEXT,
        tags            TEXT[] DEFAULT '{}',
        transaction_date TIMESTAMPTZ NOT NULL DEFAULT now(),
        -- FK columns without constraints (referenced tables don't exist yet)
        screenshot_parse_log_id UUID,
        recurring_transaction_id UUID,
        is_deleted      BOOLEAN NOT NULL DEFAULT false,
        deleted_at      TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    -- Indexes
    CREATE INDEX idx_txn_user_date ON expense_tracker.transactions
        (user_id, transaction_date DESC, id DESC) WHERE is_deleted = false;
    CREATE INDEX idx_txn_user_account ON expense_tracker.transactions
        (user_id, account_id, transaction_date DESC) WHERE is_deleted = false;
    CREATE INDEX idx_txn_user_category ON expense_tracker.transactions
        (user_id, category_id, transaction_date DESC) WHERE is_deleted = false;
    CREATE INDEX idx_txn_user_type ON expense_tracker.transactions
        (user_id, type, transaction_date DESC) WHERE is_deleted = false;
    CREATE INDEX idx_txn_user_type_date ON expense_tracker.transactions
        (user_id, type, transaction_date) WHERE is_deleted = false;
    CREATE INDEX idx_txn_tags ON expense_tracker.transactions
        USING GIN (tags) WHERE is_deleted = false;

    -- RLS
    ALTER TABLE expense_tracker.transactions ENABLE ROW LEVEL SECURITY;
    ALTER TABLE expense_tracker.transactions FORCE ROW LEVEL SECURITY;

    CREATE POLICY transactions_all ON expense_tracker.transactions FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id());

    CREATE TRIGGER trg_transactions_updated_at
        BEFORE UPDATE ON expense_tracker.transactions
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at();

    -- Balance trigger (incremental account balance updates)
    CREATE OR REPLACE FUNCTION expense_tracker.update_account_balance()
    RETURNS TRIGGER AS $$
    DECLARE
        v_delta DECIMAL(14,2);
    BEGIN
        IF TG_OP = 'DELETE' THEN
            IF OLD.is_deleted = false THEN
                v_delta := CASE
                    WHEN OLD.type = 'income'   THEN -OLD.amount
                    WHEN OLD.type = 'expense'  THEN  OLD.amount
                    WHEN OLD.type = 'transfer' THEN  OLD.amount
                    ELSE 0
                END;
                UPDATE expense_tracker.accounts SET balance = balance + v_delta WHERE id = OLD.account_id;
                IF OLD.type = 'transfer' AND OLD.to_account_id IS NOT NULL THEN
                    UPDATE expense_tracker.accounts SET balance = balance - OLD.amount WHERE id = OLD.to_account_id;
                END IF;
            END IF;
            RETURN OLD;
        END IF;

        IF TG_OP = 'INSERT' THEN
            IF NEW.is_deleted = false THEN
                v_delta := CASE
                    WHEN NEW.type = 'income'   THEN  NEW.amount
                    WHEN NEW.type = 'expense'  THEN -NEW.amount
                    WHEN NEW.type = 'transfer' THEN -NEW.amount
                    ELSE 0
                END;
                UPDATE expense_tracker.accounts SET balance = balance + v_delta WHERE id = NEW.account_id;
                IF NEW.type = 'transfer' AND NEW.to_account_id IS NOT NULL THEN
                    UPDATE expense_tracker.accounts SET balance = balance + NEW.amount WHERE id = NEW.to_account_id;
                END IF;
            END IF;
            RETURN NEW;
        END IF;

        IF TG_OP = 'UPDATE' THEN
            IF OLD.is_deleted = false THEN
                v_delta := CASE
                    WHEN OLD.type = 'income'   THEN -OLD.amount
                    WHEN OLD.type = 'expense'  THEN  OLD.amount
                    WHEN OLD.type = 'transfer' THEN  OLD.amount
                    ELSE 0
                END;
                UPDATE expense_tracker.accounts SET balance = balance + v_delta WHERE id = OLD.account_id;
                IF OLD.type = 'transfer' AND OLD.to_account_id IS NOT NULL THEN
                    UPDATE expense_tracker.accounts SET balance = balance - OLD.amount WHERE id = OLD.to_account_id;
                END IF;
            END IF;
            IF NEW.is_deleted = false THEN
                v_delta := CASE
                    WHEN NEW.type = 'income'   THEN  NEW.amount
                    WHEN NEW.type = 'expense'  THEN -NEW.amount
                    WHEN NEW.type = 'transfer' THEN -NEW.amount
                    ELSE 0
                END;
                UPDATE expense_tracker.accounts SET balance = balance + v_delta WHERE id = NEW.account_id;
                IF NEW.type = 'transfer' AND NEW.to_account_id IS NOT NULL THEN
                    UPDATE expense_tracker.accounts SET balance = balance + NEW.amount WHERE id = NEW.to_account_id;
                END IF;
            END IF;
            RETURN NEW;
        END IF;

        RETURN COALESCE(NEW, OLD);
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER trg_update_account_balance
        AFTER INSERT OR UPDATE OR DELETE ON expense_tracker.transactions
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_account_balance();
    """)

def downgrade() -> None:
    op.execute("""
    DROP TRIGGER IF EXISTS trg_update_account_balance ON expense_tracker.transactions;
    DROP FUNCTION IF EXISTS expense_tracker.update_account_balance();
    DROP TABLE IF EXISTS expense_tracker.transactions CASCADE;
    DROP TYPE IF EXISTS expense_tracker.transaction_type;
    """)
```

- [ ] **Step 2: Run migration and verify**

Run: `cd backend && alembic upgrade head`
Expected: "Running upgrade 003 -> 004"

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/004_transactions.py
git commit -m "feat: migration 004 — transactions with balance trigger and RLS"
```

---

### Task 18: Migration 005 — Recurring Transactions + RLS

**Files:**
- Create: `backend/alembic/versions/005_recurring.py`

- [ ] **Step 1: Create migration file**

Create `backend/alembic/versions/005_recurring.py`:

```python
"""Create recurring_transactions table with RLS

Revision ID: 005
Revises: 004
Create Date: 2026-03-29
"""
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TYPE expense_tracker.recurrence_frequency AS ENUM (
        'daily', 'weekly', 'biweekly', 'monthly', 'quarterly', 'yearly'
    );

    CREATE TABLE expense_tracker.recurring_transactions (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        account_id      UUID NOT NULL REFERENCES expense_tracker.accounts(id) ON DELETE RESTRICT,
        category_id     UUID REFERENCES expense_tracker.categories(id) ON DELETE SET NULL,
        type            expense_tracker.transaction_type NOT NULL,
        amount          DECIMAL(12,2) NOT NULL CHECK (amount > 0),
        description     VARCHAR(500),
        tags            TEXT[] DEFAULT '{}',
        frequency       expense_tracker.recurrence_frequency NOT NULL,
        schedule_day    SMALLINT,
        start_date      DATE NOT NULL,
        end_date        DATE,
        next_due_date   DATE NOT NULL,
        last_generated  TIMESTAMPTZ,
        is_active       BOOLEAN NOT NULL DEFAULT true,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX idx_recurring_user ON expense_tracker.recurring_transactions (user_id);
    CREATE INDEX idx_recurring_next_due ON expense_tracker.recurring_transactions (next_due_date)
        WHERE is_active = true;

    ALTER TABLE expense_tracker.recurring_transactions ENABLE ROW LEVEL SECURITY;
    ALTER TABLE expense_tracker.recurring_transactions FORCE ROW LEVEL SECURITY;

    CREATE POLICY recurring_all ON expense_tracker.recurring_transactions FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id());

    CREATE TRIGGER trg_recurring_updated_at
        BEFORE UPDATE ON expense_tracker.recurring_transactions
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at();

    -- Add deferred FK from transactions to recurring_transactions
    ALTER TABLE expense_tracker.transactions
        ADD CONSTRAINT fk_txn_recurring
        FOREIGN KEY (recurring_transaction_id) REFERENCES expense_tracker.recurring_transactions(id) ON DELETE SET NULL;
    """)

def downgrade() -> None:
    op.execute("""
    ALTER TABLE expense_tracker.transactions DROP CONSTRAINT IF EXISTS fk_txn_recurring;
    DROP TABLE IF EXISTS expense_tracker.recurring_transactions CASCADE;
    DROP TYPE IF EXISTS expense_tracker.recurrence_frequency;
    """)
```

- [ ] **Step 2: Run migration and verify**

Run: `cd backend && alembic upgrade head`

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/005_recurring.py
git commit -m "feat: migration 005 — recurring_transactions with RLS"
```

---

### Task 19: Migration 006 — Budgets + FY Functions + RLS

**Files:**
- Create: `backend/alembic/versions/006_budgets.py`

- [ ] **Step 1: Create migration file**

Create `backend/alembic/versions/006_budgets.py`:

```python
"""Create budgets table with FY functions and RLS

Revision ID: 006
Revises: 005
Create Date: 2026-03-29
"""
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TYPE expense_tracker.budget_period AS ENUM ('monthly', 'quarterly', 'yearly');

    CREATE TABLE expense_tracker.budgets (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        category_id     UUID REFERENCES expense_tracker.categories(id) ON DELETE CASCADE,
        amount          DECIMAL(12,2) NOT NULL CHECK (amount > 0),
        period          expense_tracker.budget_period NOT NULL DEFAULT 'monthly',
        fy_year         SMALLINT NOT NULL,
        alert_threshold SMALLINT NOT NULL DEFAULT 80 CHECK (alert_threshold BETWEEN 1 AND 100),
        alert_sent      BOOLEAN NOT NULL DEFAULT false,
        is_active       BOOLEAN NOT NULL DEFAULT true,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE UNIQUE INDEX idx_budgets_unique
        ON expense_tracker.budgets (user_id, COALESCE(category_id, '00000000-0000-0000-0000-000000000000'), fy_year)
        WHERE is_active = true;
    CREATE INDEX idx_budgets_user_fy ON expense_tracker.budgets (user_id, fy_year);

    ALTER TABLE expense_tracker.budgets ENABLE ROW LEVEL SECURITY;
    ALTER TABLE expense_tracker.budgets FORCE ROW LEVEL SECURITY;

    CREATE POLICY budgets_all ON expense_tracker.budgets FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id());

    CREATE TRIGGER trg_budgets_updated_at
        BEFORE UPDATE ON expense_tracker.budgets
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at();

    -- FY helper functions
    CREATE OR REPLACE FUNCTION expense_tracker.get_fy_year(d DATE)
    RETURNS SMALLINT AS $$
    BEGIN
        IF EXTRACT(MONTH FROM d) >= 4 THEN
            RETURN EXTRACT(YEAR FROM d)::SMALLINT;
        ELSE
            RETURN (EXTRACT(YEAR FROM d) - 1)::SMALLINT;
        END IF;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;

    CREATE OR REPLACE FUNCTION expense_tracker.get_fy_range(fy SMALLINT)
    RETURNS TABLE(fy_start DATE, fy_end DATE) AS $$
    BEGIN
        RETURN QUERY SELECT make_date(fy, 4, 1), make_date(fy + 1, 3, 31);
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;

    GRANT EXECUTE ON FUNCTION expense_tracker.get_fy_year(DATE) TO app_user;
    GRANT EXECUTE ON FUNCTION expense_tracker.get_fy_range(SMALLINT) TO app_user;
    """)

def downgrade() -> None:
    op.execute("""
    DROP FUNCTION IF EXISTS expense_tracker.get_fy_range(SMALLINT);
    DROP FUNCTION IF EXISTS expense_tracker.get_fy_year(DATE);
    DROP TABLE IF EXISTS expense_tracker.budgets CASCADE;
    DROP TYPE IF EXISTS expense_tracker.budget_period;
    """)
```

- [ ] **Step 2: Run migration, commit**

```bash
cd backend && alembic upgrade head
git add backend/alembic/versions/006_budgets.py
git commit -m "feat: migration 006 — budgets with FY functions and RLS"
```

---

### Task 20: Migration 007 — Investments + RLS

**Files:**
- Create: `backend/alembic/versions/007_investments.py`

- [ ] **Step 1: Create migration file**

Create `backend/alembic/versions/007_investments.py`:

```python
"""Create investment tables with RLS

Revision ID: 007
Revises: 006
Create Date: 2026-03-29
"""
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TYPE expense_tracker.investment_type AS ENUM (
        'equity', 'mutual_fund', 'etf', 'fd', 'rd', 'ppf', 'nps', 'bond', 'gold'
    );

    CREATE TABLE expense_tracker.investment_holdings (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        type            expense_tracker.investment_type NOT NULL,
        name            VARCHAR(255) NOT NULL,
        symbol          VARCHAR(50),
        quantity        DECIMAL(14,4) NOT NULL DEFAULT 0,
        avg_buy_price   DECIMAL(14,4) NOT NULL DEFAULT 0,
        current_price   DECIMAL(14,4),
        current_value   DECIMAL(14,2) GENERATED ALWAYS AS (quantity * COALESCE(current_price, avg_buy_price)) STORED,
        invested_amount DECIMAL(14,2),
        maturity_amount DECIMAL(14,2),
        interest_rate   DECIMAL(5,2),
        maturity_date   DATE,
        broker          VARCHAR(100),
        demat_account   VARCHAR(50),
        notes           TEXT,
        price_updated_at TIMESTAMPTZ,
        is_active       BOOLEAN NOT NULL DEFAULT true,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX idx_holdings_user ON expense_tracker.investment_holdings (user_id);
    CREATE INDEX idx_holdings_user_type ON expense_tracker.investment_holdings (user_id, type);
    CREATE INDEX idx_holdings_symbol ON expense_tracker.investment_holdings (symbol) WHERE symbol IS NOT NULL;

    ALTER TABLE expense_tracker.investment_holdings ENABLE ROW LEVEL SECURITY;
    ALTER TABLE expense_tracker.investment_holdings FORCE ROW LEVEL SECURITY;
    CREATE POLICY holdings_all ON expense_tracker.investment_holdings FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id());
    CREATE TRIGGER trg_holdings_updated_at
        BEFORE UPDATE ON expense_tracker.investment_holdings
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at();

    -- Investment Transactions
    CREATE TYPE expense_tracker.investment_txn_type AS ENUM (
        'buy', 'sell', 'dividend', 'interest', 'split', 'bonus', 'sip'
    );

    CREATE TABLE expense_tracker.investment_transactions (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        holding_id      UUID NOT NULL REFERENCES expense_tracker.investment_holdings(id) ON DELETE CASCADE,
        type            expense_tracker.investment_txn_type NOT NULL,
        quantity        DECIMAL(14,4),
        price_per_unit  DECIMAL(14,4),
        amount          DECIMAL(14,2) NOT NULL,
        ratio_from      SMALLINT,
        ratio_to        SMALLINT,
        brokerage       DECIMAL(10,2) DEFAULT 0,
        stt             DECIMAL(10,2) DEFAULT 0,
        gst             DECIMAL(10,2) DEFAULT 0,
        stamp_duty      DECIMAL(10,2) DEFAULT 0,
        other_charges   DECIMAL(10,2) DEFAULT 0,
        transaction_date DATE NOT NULL,
        settlement_date  DATE,
        notes           TEXT,
        is_deleted      BOOLEAN NOT NULL DEFAULT false,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX idx_inv_txn_user ON expense_tracker.investment_transactions (user_id);
    CREATE INDEX idx_inv_txn_holding ON expense_tracker.investment_transactions (holding_id, transaction_date DESC);
    CREATE INDEX idx_inv_txn_user_date ON expense_tracker.investment_transactions (user_id, transaction_date DESC)
        WHERE is_deleted = false;

    ALTER TABLE expense_tracker.investment_transactions ENABLE ROW LEVEL SECURITY;
    ALTER TABLE expense_tracker.investment_transactions FORCE ROW LEVEL SECURITY;
    CREATE POLICY inv_txn_all ON expense_tracker.investment_transactions FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id());
    CREATE TRIGGER trg_inv_txn_updated_at
        BEFORE UPDATE ON expense_tracker.investment_transactions
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at();

    -- Bond Details
    CREATE TYPE expense_tracker.coupon_frequency AS ENUM ('monthly', 'quarterly', 'semi_annual', 'annual', 'zero_coupon');
    CREATE TYPE expense_tracker.credit_rating AS ENUM (
        'AAA', 'AA+', 'AA', 'AA-', 'A+', 'A', 'A-',
        'BBB+', 'BBB', 'BBB-', 'BB+', 'BB', 'BB-', 'B+', 'B', 'B-',
        'C', 'D', 'unrated', 'sovereign'
    );

    CREATE TABLE expense_tracker.bond_details (
        id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        holding_id          UUID NOT NULL UNIQUE REFERENCES expense_tracker.investment_holdings(id) ON DELETE CASCADE,
        user_id             UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        isin                VARCHAR(12),
        face_value          DECIMAL(12,2) NOT NULL DEFAULT 1000,
        coupon_rate         DECIMAL(5,2),
        coupon_frequency    expense_tracker.coupon_frequency NOT NULL DEFAULT 'semi_annual',
        issue_date          DATE,
        maturity_date       DATE NOT NULL,
        next_coupon_date    DATE,
        credit_rating       expense_tracker.credit_rating DEFAULT 'unrated',
        rating_agency       VARCHAR(50),
        issuer_name         VARCHAR(255),
        is_tax_free         BOOLEAN NOT NULL DEFAULT false,
        is_callable         BOOLEAN NOT NULL DEFAULT false,
        call_date           DATE,
        ytm                 DECIMAL(5,2),
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX idx_bond_details_holding ON expense_tracker.bond_details (holding_id);

    ALTER TABLE expense_tracker.bond_details ENABLE ROW LEVEL SECURITY;
    ALTER TABLE expense_tracker.bond_details FORCE ROW LEVEL SECURITY;
    CREATE POLICY bond_details_all ON expense_tracker.bond_details FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id());
    CREATE TRIGGER trg_bond_details_updated_at
        BEFORE UPDATE ON expense_tracker.bond_details
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at();
    """)

def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS expense_tracker.bond_details CASCADE;
    DROP TABLE IF EXISTS expense_tracker.investment_transactions CASCADE;
    DROP TABLE IF EXISTS expense_tracker.investment_holdings CASCADE;
    DROP TYPE IF EXISTS expense_tracker.credit_rating;
    DROP TYPE IF EXISTS expense_tracker.coupon_frequency;
    DROP TYPE IF EXISTS expense_tracker.investment_txn_type;
    DROP TYPE IF EXISTS expense_tracker.investment_type;
    """)
```

- [ ] **Step 2: Run migration, commit**

```bash
cd backend && alembic upgrade head
git add backend/alembic/versions/007_investments.py
git commit -m "feat: migration 007 — investment holdings, transactions, bond details with RLS"
```

---

### Task 21: Migration 008 — Screenshots + API Usage + RLS

**Files:**
- Create: `backend/alembic/versions/008_screenshots.py`

- [ ] **Step 1: Create migration file**

Create `backend/alembic/versions/008_screenshots.py`:

```python
"""Create screenshot_parse_logs and api_usage tables with RLS

Revision ID: 008
Revises: 007
Create Date: 2026-03-29
"""
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TYPE expense_tracker.parse_status AS ENUM (
        'uploaded', 'processing', 'parsed', 'confirmed', 'rejected', 'failed'
    );

    CREATE TABLE expense_tracker.screenshot_parse_logs (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        s3_key          VARCHAR(1024) NOT NULL,
        original_filename VARCHAR(255),
        file_size_bytes INTEGER NOT NULL,
        mime_type       VARCHAR(50) NOT NULL,
        status          expense_tracker.parse_status NOT NULL DEFAULT 'uploaded',
        provider        VARCHAR(20),
        model_used      VARCHAR(50),
        claude_request_id VARCHAR(100),
        input_tokens    INTEGER,
        output_tokens   INTEGER,
        cost_usd        DECIMAL(8,6),
        api_latency_ms  INTEGER,
        parsed_data     JSONB,
        error_message   TEXT,
        error_code      VARCHAR(50),
        transaction_id  UUID REFERENCES expense_tracker.transactions(id) ON DELETE SET NULL,
        queued_at       TIMESTAMPTZ,
        processing_started_at TIMESTAMPTZ,
        parsed_at       TIMESTAMPTZ,
        confirmed_at    TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX idx_parse_logs_user ON expense_tracker.screenshot_parse_logs (user_id, created_at DESC);
    CREATE INDEX idx_parse_logs_status ON expense_tracker.screenshot_parse_logs (status)
        WHERE status IN ('uploaded', 'processing');

    ALTER TABLE expense_tracker.screenshot_parse_logs ENABLE ROW LEVEL SECURITY;
    ALTER TABLE expense_tracker.screenshot_parse_logs FORCE ROW LEVEL SECURITY;
    CREATE POLICY parse_logs_all ON expense_tracker.screenshot_parse_logs FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id());
    CREATE TRIGGER trg_parse_logs_updated_at
        BEFORE UPDATE ON expense_tracker.screenshot_parse_logs
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at();

    -- Add deferred FK from transactions to screenshot_parse_logs
    ALTER TABLE expense_tracker.transactions
        ADD CONSTRAINT fk_txn_screenshot
        FOREIGN KEY (screenshot_parse_log_id) REFERENCES expense_tracker.screenshot_parse_logs(id) ON DELETE SET NULL;

    -- API Usage
    CREATE TABLE expense_tracker.api_usage (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        date            DATE NOT NULL DEFAULT CURRENT_DATE,
        screenshot_count INTEGER NOT NULL DEFAULT 0,
        total_input_tokens BIGINT NOT NULL DEFAULT 0,
        total_output_tokens BIGINT NOT NULL DEFAULT 0,
        total_cost_usd  DECIMAL(10,6) NOT NULL DEFAULT 0,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE UNIQUE INDEX idx_api_usage_user_date ON expense_tracker.api_usage (user_id, date);

    ALTER TABLE expense_tracker.api_usage ENABLE ROW LEVEL SECURITY;
    ALTER TABLE expense_tracker.api_usage FORCE ROW LEVEL SECURITY;
    CREATE POLICY api_usage_select ON expense_tracker.api_usage FOR SELECT TO app_user
        USING (user_id = expense_tracker.current_app_user_id());
    CREATE TRIGGER trg_api_usage_updated_at
        BEFORE UPDATE ON expense_tracker.api_usage
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at();
    """)

def downgrade() -> None:
    op.execute("""
    ALTER TABLE expense_tracker.transactions DROP CONSTRAINT IF EXISTS fk_txn_screenshot;
    DROP TABLE IF EXISTS expense_tracker.api_usage CASCADE;
    DROP TABLE IF EXISTS expense_tracker.screenshot_parse_logs CASCADE;
    DROP TYPE IF EXISTS expense_tracker.parse_status;
    """)
```

- [ ] **Step 2: Run migration, commit**

```bash
cd backend && alembic upgrade head
git add backend/alembic/versions/008_screenshots.py
git commit -m "feat: migration 008 — screenshot_parse_logs and api_usage with RLS"
```

---

### Task 22: Migration 009 — Audit Logs

**Files:**
- Create: `backend/alembic/versions/009_audit.py`

- [ ] **Step 1: Create migration file**

Create `backend/alembic/versions/009_audit.py`:

```python
"""Create audit_logs table

Revision ID: 009
Revises: 008
Create Date: 2026-03-29
"""
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TABLE expense_tracker.audit_logs (
        id              BIGSERIAL PRIMARY KEY,
        user_id         UUID REFERENCES expense_tracker.users(id) ON DELETE SET NULL,
        action          VARCHAR(50) NOT NULL,
        entity_type     VARCHAR(50) NOT NULL,
        entity_id       UUID NOT NULL,
        old_values      JSONB,
        new_values      JSONB,
        ip_address      INET,
        user_agent      VARCHAR(512),
        metadata        JSONB,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX idx_audit_user_date ON expense_tracker.audit_logs (user_id, created_at DESC);
    CREATE INDEX idx_audit_entity ON expense_tracker.audit_logs (entity_type, entity_id);

    ALTER TABLE expense_tracker.audit_logs ENABLE ROW LEVEL SECURITY;
    ALTER TABLE expense_tracker.audit_logs FORCE ROW LEVEL SECURITY;

    CREATE POLICY audit_logs_select ON expense_tracker.audit_logs FOR SELECT TO app_user
        USING (user_id = expense_tracker.current_app_user_id());
    CREATE POLICY audit_logs_insert ON expense_tracker.audit_logs FOR INSERT TO app_user
        WITH CHECK (user_id = expense_tracker.current_app_user_id());

    REVOKE UPDATE, DELETE ON expense_tracker.audit_logs FROM app_user;
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS expense_tracker.audit_logs CASCADE;")
```

- [ ] **Step 2: Run migration, commit**

```bash
cd backend && alembic upgrade head
git add backend/alembic/versions/009_audit.py
git commit -m "feat: migration 009 — immutable audit_logs with RLS"
```

---

### Task 23: Migration 010 — Seed Indian Categories

**Files:**
- Create: `backend/alembic/versions/010_seed_categories.py`

- [ ] **Step 1: Create seed migration**

Create `backend/alembic/versions/010_seed_categories.py`:

```python
"""Seed default Indian categories

Revision ID: 010
Revises: 009
Create Date: 2026-03-29
"""
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # System categories have user_id = NULL, is_system = true
    op.execute("""
    -- ── EXPENSE categories ──
    INSERT INTO expense_tracker.categories (user_id, parent_id, name, type, icon, is_system, sort_order) VALUES
    (NULL, NULL, 'Food & Dining', 'expense', '🍽️', true, 1),
    (NULL, NULL, 'Transport', 'expense', '🚗', true, 2),
    (NULL, NULL, 'Shopping', 'expense', '🛍️', true, 3),
    (NULL, NULL, 'Bills & Utilities', 'expense', '💡', true, 4),
    (NULL, NULL, 'Housing', 'expense', '🏠', true, 5),
    (NULL, NULL, 'Health', 'expense', '🏥', true, 6),
    (NULL, NULL, 'Education', 'expense', '📚', true, 7),
    (NULL, NULL, 'Entertainment', 'expense', '🎬', true, 8),
    (NULL, NULL, 'Personal Care', 'expense', '💇', true, 9),
    (NULL, NULL, 'Travel / Holiday', 'expense', '✈️', true, 10),
    (NULL, NULL, 'Gifts & Donations', 'expense', '🎁', true, 11),
    (NULL, NULL, 'EMI & Loans', 'expense', '🏦', true, 12),
    (NULL, NULL, 'Taxes', 'expense', '📋', true, 13),
    (NULL, NULL, 'Insurance', 'expense', '🛡️', true, 14),
    (NULL, NULL, 'Domestic Help', 'expense', '🏠', true, 15),
    (NULL, NULL, 'Miscellaneous', 'expense', '📦', true, 16);

    -- Subcategories for Food & Dining
    INSERT INTO expense_tracker.categories (user_id, parent_id, name, type, icon, is_system, sort_order)
    SELECT NULL, id, sub.name, 'expense', sub.icon, true, sub.sort_order
    FROM expense_tracker.categories parent,
    (VALUES
        ('Groceries', '🛒', 1), ('Restaurants', '🍴', 2),
        ('Swiggy / Zomato', '📱', 3), ('Chai / Snacks', '☕', 4)
    ) AS sub(name, icon, sort_order)
    WHERE parent.name = 'Food & Dining' AND parent.parent_id IS NULL AND parent.is_system = true;

    -- Subcategories for Transport
    INSERT INTO expense_tracker.categories (user_id, parent_id, name, type, icon, is_system, sort_order)
    SELECT NULL, id, sub.name, 'expense', sub.icon, true, sub.sort_order
    FROM expense_tracker.categories parent,
    (VALUES
        ('Petrol / Diesel', '⛽', 1), ('Ola / Uber', '🚕', 2),
        ('Metro / Bus', '🚇', 3), ('Auto', '🛺', 4)
    ) AS sub(name, icon, sort_order)
    WHERE parent.name = 'Transport' AND parent.parent_id IS NULL AND parent.is_system = true;

    -- Subcategories for Bills & Utilities
    INSERT INTO expense_tracker.categories (user_id, parent_id, name, type, icon, is_system, sort_order)
    SELECT NULL, id, sub.name, 'expense', sub.icon, true, sub.sort_order
    FROM expense_tracker.categories parent,
    (VALUES
        ('Electricity', '⚡', 1), ('Mobile Recharge', '📱', 2),
        ('Internet / WiFi', '🌐', 3), ('Gas', '🔥', 4),
        ('Water', '💧', 5), ('DTH', '📡', 6)
    ) AS sub(name, icon, sort_order)
    WHERE parent.name = 'Bills & Utilities' AND parent.parent_id IS NULL AND parent.is_system = true;

    -- ── INCOME categories ──
    INSERT INTO expense_tracker.categories (user_id, parent_id, name, type, icon, is_system, sort_order) VALUES
    (NULL, NULL, 'Salary', 'income', '💰', true, 1),
    (NULL, NULL, 'Freelance / Consulting', 'income', '💻', true, 2),
    (NULL, NULL, 'Business Income', 'income', '🏢', true, 3),
    (NULL, NULL, 'Interest Income', 'income', '🏦', true, 4),
    (NULL, NULL, 'Dividend Income', 'income', '📈', true, 5),
    (NULL, NULL, 'Rental Income', 'income', '🏠', true, 6),
    (NULL, NULL, 'Capital Gains', 'income', '📊', true, 7),
    (NULL, NULL, 'Cashback / Rewards', 'income', '🎯', true, 8),
    (NULL, NULL, 'Other Income', 'income', '💵', true, 9);
    """)

def downgrade() -> None:
    op.execute("DELETE FROM expense_tracker.categories WHERE is_system = true;")
```

- [ ] **Step 2: Run migration, commit**

```bash
cd backend && alembic upgrade head
git add backend/alembic/versions/010_seed_categories.py
git commit -m "feat: migration 010 — seed default Indian categories"
```

---

## Phase D: Verification

### Task 24: RLS Integration Test (CRITICAL)

**Files:**
- Create: `backend/tests/integration/test_rls_isolation.py`

- [ ] **Step 1: Write RLS integration test**

Create `backend/tests/integration/test_rls_isolation.py`:

```python
"""
RLS Isolation Integration Test (T-1.4.12)

Validates that Row-Level Security enforces tenant isolation across all data tables.
Requires running PostgreSQL with migrations applied.
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Use sync engine for integration tests
DATABASE_URL = os.getenv(
    "SYNC_DATABASE_URL",
    "postgresql://postgres:postgres_dev@localhost:5433/expense_tracker",
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(engine)

# Two test user IDs
USER_A_ID = str(uuid.uuid4())
USER_B_ID = str(uuid.uuid4())


@pytest.fixture(scope="module", autouse=True)
def setup_test_users():
    """Create two test users and insert test data for each."""
    with SessionLocal() as session:
        session.execute(text("SET search_path TO expense_tracker, public"))

        # Create users
        session.execute(text("""
            INSERT INTO users (id, email, full_name)
            VALUES (:id_a, :email_a, 'User A'), (:id_b, :email_b, 'User B')
        """), {
            "id_a": USER_A_ID, "email_a": f"usera_{USER_A_ID[:8]}@test.com",
            "id_b": USER_B_ID, "email_b": f"userb_{USER_B_ID[:8]}@test.com",
        })

        # Create accounts for each user
        for user_id, name in [(USER_A_ID, "A Savings"), (USER_B_ID, "B Savings")]:
            session.execute(text("""
                INSERT INTO accounts (id, user_id, name, type, balance)
                VALUES (uuid_generate_v4(), :uid, :name, 'savings', 10000)
            """), {"uid": user_id, "name": name})

        # Create categories for each user
        for user_id, name in [(USER_A_ID, "A Food"), (USER_B_ID, "B Food")]:
            session.execute(text("""
                INSERT INTO categories (id, user_id, name, type)
                VALUES (uuid_generate_v4(), :uid, :name, 'expense')
            """), {"uid": user_id, "name": name})

        # Create budgets for each user
        for user_id in [USER_A_ID, USER_B_ID]:
            session.execute(text("""
                INSERT INTO budgets (user_id, amount, fy_year)
                VALUES (:uid, 50000, 2026)
            """), {"uid": user_id})

        # Create investment holdings for each user
        for user_id, name in [(USER_A_ID, "A HDFC"), (USER_B_ID, "B SBI")]:
            session.execute(text("""
                INSERT INTO investment_holdings (user_id, type, name, quantity, avg_buy_price)
                VALUES (:uid, 'equity', :name, 10, 1500)
            """), {"uid": user_id, "name": name})

        session.commit()

    yield

    # Cleanup
    with SessionLocal() as session:
        session.execute(text("SET search_path TO expense_tracker, public"))
        session.execute(text("DELETE FROM budgets WHERE user_id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.execute(text("DELETE FROM investment_holdings WHERE user_id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.execute(text("DELETE FROM categories WHERE user_id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.execute(text("DELETE FROM accounts WHERE user_id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.execute(text("DELETE FROM users WHERE id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.commit()


def _query_as_user(user_id: str, table: str) -> list:
    """Query a table with RLS context set to user_id. Uses app_user role."""
    with SessionLocal() as session:
        session.execute(text("SET search_path TO expense_tracker, public"))
        session.execute(text("SET LOCAL ROLE app_user"))
        session.execute(text("SET LOCAL app.current_user_id = :uid"), {"uid": user_id})
        rows = session.execute(text(f"SELECT user_id FROM {table}")).fetchall()
        session.rollback()  # rollback to reset role
    return rows


def _query_without_context(table: str) -> list:
    """Query a table as app_user WITHOUT setting RLS context (fail-closed test)."""
    with SessionLocal() as session:
        session.execute(text("SET search_path TO expense_tracker, public"))
        session.execute(text("SET LOCAL ROLE app_user"))
        # Do NOT set app.current_user_id
        rows = session.execute(text(f"SELECT user_id FROM {table}")).fetchall()
        session.rollback()
    return rows


RLS_TABLES = ["accounts", "categories", "budgets", "investment_holdings"]


@pytest.mark.parametrize("table", RLS_TABLES)
def test_user_a_sees_only_own_data(table):
    rows = _query_as_user(USER_A_ID, table)
    user_ids = {str(r[0]) for r in rows}
    assert USER_A_ID in user_ids or len(rows) == 0, f"User A should see own data in {table}"
    assert USER_B_ID not in user_ids, f"User A must NOT see User B's data in {table}"


@pytest.mark.parametrize("table", RLS_TABLES)
def test_user_b_sees_only_own_data(table):
    rows = _query_as_user(USER_B_ID, table)
    user_ids = {str(r[0]) for r in rows}
    assert USER_B_ID in user_ids or len(rows) == 0, f"User B should see own data in {table}"
    assert USER_A_ID not in user_ids, f"User B must NOT see User A's data in {table}"


@pytest.mark.parametrize("table", ["accounts", "budgets", "investment_holdings"])
def test_no_context_returns_no_rows(table):
    """Without RLS context, no rows should be visible (fail-closed)."""
    rows = _query_without_context(table)
    assert len(rows) == 0, f"No context should return 0 rows for {table}, got {len(rows)}"


def test_categories_show_system_defaults_without_user_context():
    """Categories with user_id IS NULL (system) should be visible to any user."""
    rows = _query_as_user(USER_A_ID, "categories")
    # Should see own categories + system categories (user_id IS NULL)
    assert len(rows) > 0, "User A should see at least system categories"


def test_insert_with_wrong_user_id_blocked():
    """Attempting to INSERT a row with a different user_id should be blocked by RLS WITH CHECK."""
    with SessionLocal() as session:
        session.execute(text("SET search_path TO expense_tracker, public"))
        session.execute(text("SET LOCAL ROLE app_user"))
        session.execute(text("SET LOCAL app.current_user_id = :uid"), {"uid": USER_A_ID})
        with pytest.raises(Exception):
            session.execute(text("""
                INSERT INTO accounts (user_id, name, type, balance)
                VALUES (:uid, 'Hacked Account', 'savings', 0)
            """), {"uid": USER_B_ID})
        session.rollback()
```

- [ ] **Step 2: Run the RLS integration test**

Run: `cd backend && python -m pytest tests/integration/test_rls_isolation.py -v`

Expected: All tests PASS. Key assertions:
- User A only sees User A data
- User B only sees User B data
- No RLS context = 0 rows (fail-closed)
- Cross-tenant INSERT blocked

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_rls_isolation.py
git commit -m "test: add RLS isolation integration test (T-1.4.12)"
```

---

### Task 25: Full Stack Verification

**Files:** None (verification only)

- [ ] **Step 1: Start the full Docker stack**

Run: `cd docker && docker compose up -d --build`

Expected: All services start (postgres, pgbouncer, redis, minio, backend, celery-worker, celery-beat, flower)

- [ ] **Step 2: Run all migrations inside the container**

Run: `docker compose -f docker/docker-compose.yml exec backend alembic upgrade head`

Expected: All 10 migrations applied successfully

- [ ] **Step 3: Verify health endpoint**

Run: `curl http://localhost:8000/api/v1/health`

Expected:
```json
{"status": "healthy", "checks": {"db": true, "redis": true, "s3": true}}
```

- [ ] **Step 4: Verify all tables exist**

Run: `docker compose -f docker/docker-compose.yml exec postgres psql -U postgres -d expense_tracker -c "\dt expense_tracker.*"`

Expected: 13 tables listed (users, refresh_tokens, categories, accounts, transactions, recurring_transactions, budgets, investment_holdings, investment_transactions, bond_details, screenshot_parse_logs, api_usage, audit_logs)

- [ ] **Step 5: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`

Expected: All tests pass

- [ ] **Step 6: Run linting**

Run: `cd backend && ruff check app/ tests/`

Expected: No errors

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "feat: Sprint 1 complete — Docker, FastAPI, 13 tables, RLS verified"
```

---

## Verification Checklist

- [ ] `docker compose up` starts all services
- [ ] `GET /api/v1/health` returns `{"status": "healthy"}`
- [ ] All Alembic migrations (001–010) run cleanly
- [ ] 13 tables exist in `expense_tracker` schema
- [ ] RLS integration test passes (tenant isolation verified)
- [ ] `pytest` passes with no failures
- [ ] `ruff check` passes with no errors
