# Sprint 1: Foundation Design Spec

> **Date:** 2026-03-29
> **Status:** Approved
> **Scope:** US-1.1 (Backend Scaffolding) + US-1.3 (Infrastructure) + US-1.4 (Database Schema + RLS)
> **Approach:** Bottom-Up — Infra first, then backend, then DB schema

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Dev environment | Fully Dockerized | Consistent environment, `docker compose up` runs everything |
| Hot-reload | Volume mount `./backend/app` + `uvicorn --reload` | Instant reload inside container |
| Postgres | Docker on port 5433 | Isolated from local Postgres install |
| Database name | `expense_tracker` | Dedicated database |
| Schema name | `expense_tracker` | All application tables in this schema |
| Redis | Docker on port 6380 | Isolated from local Redis |
| S3 local | MinIO on port 9000 | S3-compatible, no AWS dependency in dev |
| Implementation order | Infra → Backend → DB schema | Every step verifiable immediately |

---

## Section 1: Infrastructure (Docker Compose + Configs)

### Services

| Service | Image | Host Port | Notes |
|---------|-------|-----------|-------|
| `postgres` | `postgres:16-alpine` | 5433 | DB: `expense_tracker`, schema: `expense_tracker` |
| `pgbouncer` | `bitnami/pgbouncer` | 6432 | Transaction mode, connects to postgres |
| `redis` | `redis:7-alpine` | 6380 | AOF persistence, 256MB memory limit |
| `minio` | `minio/minio` | 9000 (API) / 9001 (console) | S3-compatible local storage |
| `backend` | Built from `backend/Dockerfile` | 8000 | Volume mount for hot-reload |
| `celery-worker` | Same image as backend | — | `celery -A app.tasks.celery_app worker` |
| `celery-beat` | Same image as backend | — | `celery -A app.tasks.celery_app beat` |
| `flower` | `mher/flower` | 5555 | Celery monitoring UI |

### Files

- `docker/docker-compose.yml` — Dev: all services, volume mounts, debug mode
- `docker/docker-compose.prod.yml` — Prod overrides: Gunicorn, Caddy, no volumes, no debug
- `docker/caddy/Caddyfile` — Static files, API reverse proxy, SPA fallback, security headers
- `docker/pgbouncer/pgbouncer.ini` — Transaction mode pooling
- `docker/redis/redis.conf` — AOF persistence, 256MB maxmemory, allkeys-lru eviction
- `docker/postgres/init.sql` — Create `expense_tracker` schema, enable extensions (uuid-ossp, pgcrypto)
- `.env.example` — All env vars documented with safe dev defaults

### Port Allocation (Dev)

Non-standard ports to avoid conflicts with locally installed services:

- Postgres: 5433 (not 5432)
- PgBouncer: 6432
- Redis: 6380 (not 6379)
- MinIO API: 9000, Console: 9001
- Backend: 8000
- Flower: 5555

---

## Section 2: Backend Scaffolding (FastAPI App)

### Directory Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # create_app() factory, lifespan, middleware registration
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py         # Pydantic Settings (all env vars, validated)
│   │   ├── database.py       # Async + sync engines, session factories, RLS context
│   │   ├── redis.py          # Redis client singleton (redis.asyncio)
│   │   ├── storage.py        # S3/MinIO client (boto3, presigned URLs)
│   │   ├── middleware.py      # Request ID, timing, security headers
│   │   └── exceptions.py     # Custom exceptions + global exception handlers
│   └── tasks/
│       └── celery_app.py     # Celery factory (placeholder for Sprint 1)
├── tests/
│   ├── conftest.py           # Fixtures: test DB, async client, factories
│   └── unit/
│       └── test_health.py    # Health endpoint tests
├── alembic/
│   ├── env.py                # Async-aware Alembic env
│   └── versions/             # Migration files
├── alembic.ini
├── pyproject.toml            # Dependencies, ruff, mypy, pytest config
├── Dockerfile                # Multi-stage, python:3.12-slim, non-root
└── requirements/
    ├── base.txt              # Core runtime dependencies
    ├── dev.txt               # Testing, linting, debugging
    └── prod.txt              # Gunicorn, Sentry SDK
```

### App Factory (`main.py`)

- `create_app()` returns a configured FastAPI instance
- Lifespan context manager handles startup/shutdown:
  - Startup: verify DB connection, init Redis pool, ensure MinIO bucket exists
  - Shutdown: close DB engines, close Redis pool
- Middleware registration: request ID, timing, security headers, CORS
- Exception handlers for custom exceptions (400, 401, 403, 404, 422, 500)
- API prefix: `/api/v1`

### Configuration (`core/config.py`)

Pydantic Settings class with env var groups:

- **App:** `APP_NAME`, `DEBUG`, `API_V1_PREFIX`, `ALLOWED_ORIGINS`
- **Database:** `DATABASE_URL`, `SYNC_DATABASE_URL`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`
- **Redis:** `REDIS_URL`
- **S3/MinIO:** `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME`, `S3_REGION`
- **JWT:** `JWT_PRIVATE_KEY_PATH`, `JWT_PUBLIC_KEY_PATH`, `JWT_ALGORITHM` (RS256), `ACCESS_TOKEN_EXPIRE_MINUTES`
- **Auth:** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `MSG91_AUTH_KEY`, `MSG91_TEMPLATE_ID`
- **Anthropic:** `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `CLAUDE_DAILY_LIMIT_PER_USER`
- **Sentry:** `SENTRY_DSN`

### Database (`core/database.py`)

- Async engine (`asyncpg`) for FastAPI routes
- Sync engine (`psycopg2`) for Celery tasks
- `get_db_session(user_id)` — async context manager, sets `SET LOCAL app.current_user_id`
- `sync_db_session(user_id)` — sync context manager for Celery
- PgBouncer-compatible: `prepared_statement_cache_size=0`

### Redis (`core/redis.py`)

- `redis.asyncio` client singleton
- Init on app startup, close on shutdown
- Helper methods: `get`, `set`, `delete`, `incr` with TTL support

### Storage (`core/storage.py`)

- `boto3` S3 client configured for MinIO in dev (custom endpoint URL)
- Methods: `upload_file()`, `generate_presigned_url()`, `delete_file()`
- Bucket auto-creation on startup

### Health Endpoint

- `GET /api/v1/health`
- Checks: DB query (`SELECT 1`), Redis ping, S3 bucket head
- Response: `{"status": "healthy"|"degraded"|"unhealthy", "checks": {"db": true, "redis": true, "s3": true}}`

### Middleware (`core/middleware.py`)

- **Request ID:** Generate UUID, add to `X-Request-ID` response header, inject into structlog context
- **Timing:** Measure request duration, add `X-Response-Time` header
- **Security headers:** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 0`, `Referrer-Policy: strict-origin-when-cross-origin`

### Dockerfile

- Multi-stage: `builder` (install deps) → `runtime` (copy installed packages)
- Base: `python:3.12-slim`
- Non-root user (`appuser`)
- Read-only filesystem compatible
- Entrypoint: `uvicorn app.main:app` (dev) / `gunicorn` (prod)

---

## Section 3: Database Schema + RLS

### Schema

All tables live in the `expense_tracker` schema. The `public` schema is not used for application tables.

### Migration Plan

| # | File | Tables Created | RLS | Key Details |
|---|------|---------------|-----|-------------|
| 001 | `001_users.py` | `users`, `refresh_tokens` | No | UUID PK, email unique, phone unique nullable, google_id, created_at/updated_at |
| 002 | `002_categories.py` | `categories` | Yes | Hierarchical (parent_id FK to self), `is_system` boolean, type enum (income/expense) |
| 003 | `003_accounts.py` | `accounts` | Yes | Type enum (savings, current, credit_card, wallet, cash, loan), DECIMAL(12,2) balance |
| 004 | `004_transactions.py` | `transactions` | Yes | Composite indexes (user_id+transaction_date, user_id+category_id), GIN index on tags[], amount DECIMAL(12,2) |
| 005 | `005_recurring.py` | `recurring_transactions` | Yes | Frequency enum (daily, weekly, monthly, yearly), next_due_date, is_active |
| 006 | `006_budgets.py` | `budgets` | Yes | fy_year integer, category_id FK, amount DECIMAL(12,2), unique(user_id, category_id, fy_year) |
| 007 | `007_investments.py` | `investment_holdings`, `investment_transactions`, `bond_details` | Yes | Type enum (stock, mf, etf, fd, rd, ppf, nps, bond, gold), quantities DECIMAL(10,4) |
| 008 | `008_screenshots.py` | `screenshot_parse_logs`, `api_usage` | Yes | Status enum (pending, processing, completed, failed), cost_inr DECIMAL(8,4) |
| 009 | `009_audit.py` | `audit_logs` | No | BIGSERIAL PK, INSERT-only (no UPDATE/DELETE policy), action enum, JSONB changes column |
| 010 | `010_functions.py` | — | — | `get_fy_year(date)` returns integer, `get_fy_range(fy_year)` returns start/end dates, balance update trigger on transactions, `updated_at` trigger |
| 011 | `011_seed_categories.py` | — | — | Default Indian categories: Income (Salary, Freelance, Interest, Dividends, Rent, Gift, Refund, Other) and Expense (Food, Transport, Shopping, Bills, Health, Education, Entertainment, Travel, Housing, Insurance, Tax, Donation, Other) |

### RLS Pattern

Applied to all data tables (categories, accounts, transactions, recurring_transactions, budgets, investment_holdings, investment_transactions, bond_details, screenshot_parse_logs, api_usage):

```sql
-- Enable and force RLS (even for table owner)
ALTER TABLE expense_tracker.<table> ENABLE ROW LEVEL SECURITY;
ALTER TABLE expense_tracker.<table> FORCE ROW LEVEL SECURITY;

-- Single policy: user can only see/modify their own rows
CREATE POLICY user_isolation ON expense_tracker.<table>
  USING (user_id = current_setting('app.current_user_id')::uuid)
  WITH CHECK (user_id = current_setting('app.current_user_id')::uuid);
```

The application DB user is NOT a superuser, so `FORCE ROW LEVEL SECURITY` ensures RLS applies even if someone changes the user's role.

### Money Fields

All monetary values use `DECIMAL(12,2)`. Supports up to 9,99,99,99,999.99 INR (99.99 billion). No float, no integer-cents. INR only — no currency column.

### RLS Integration Test (T-1.4.12)

Critical test that validates tenant isolation:

1. Create 2 users (user_A, user_B)
2. Insert test data for each user across all RLS-enabled tables
3. Set RLS context to user_A → query each table → assert only user_A's data returned
4. Set RLS context to user_B → query each table → assert only user_B's data returned
5. Attempt INSERT with mismatched user_id → assert blocked by WITH CHECK
6. Test with no RLS context set → assert no rows returned (fail-closed)

---

## Verification Criteria

Sprint 1 is complete when:

1. `docker compose up` starts all services successfully
2. `GET /api/v1/health` returns `{"status": "healthy"}` with all checks passing
3. All 11 Alembic migrations run cleanly
4. RLS integration test passes (T-1.4.12)
5. `pytest` passes with no failures
6. `ruff check` and `mypy` pass with no errors
