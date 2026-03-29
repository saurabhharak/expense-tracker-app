# Personal Finance Tracker -- Architecture Document

> **Version:** 1.0
> **Date:** 2026-03-29
> **Status:** Reference specification for implementation
> **Audience:** Engineering team, DevOps, QA

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Tech Stack](#2-tech-stack)
3. [Directory Structure](#3-directory-structure)
4. [Authentication & Authorization](#4-authentication--authorization)
5. [Complete Database Schema](#5-complete-database-schema)
6. [API Endpoints](#6-api-endpoints)
7. [Screenshot Parsing Pipeline](#7-screenshot-parsing-pipeline)
8. [Background Jobs (Celery)](#8-background-jobs-celery)
9. [Caching (Redis)](#9-caching-redis)
10. [Frontend Architecture](#10-frontend-architecture)
11. [Deployment](#11-deployment)
12. [Monitoring](#12-monitoring)
13. [Cost Projections](#13-cost-projections)
14. [Scaling Strategy](#14-scaling-strategy)

---

## 1. Executive Summary

This document defines the complete architecture for a **production-grade, multi-tenant Personal Finance Tracker** built for thousands of Indian users.

### Core Capabilities

- **Income & Expense Tracking** -- Manual entry and automatic parsing from UPI/bank screenshots via Claude Vision.
- **Investment Portfolio** -- Stocks, mutual funds, ETFs, fixed deposits, recurring deposits, PPF, NPS, bonds, and gold.
- **Budget Management** -- Category-level budgets aligned to the Indian Financial Year (April--March), with configurable alert thresholds.
- **Dashboard & Analytics** -- Real-time spending trends, category breakdowns, net-worth tracking, and budget health indicators.
- **Multi-Account Support** -- Savings, current, credit card, wallet, cash, and loan accounts, each with independent balances.

### Design Principles

| Principle | Implementation |
|-----------|---------------|
| **INR-first** | All monetary values stored as `DECIMAL(12,2)` in INR. No multi-currency abstraction. |
| **Indian Financial Year** | FY runs April 1 -- March 31. All budgets, reports, and summaries are FY-aware. FY 2026-27 means April 2026 -- March 2027. |
| **Data Residency** | All user data (database, file storage, backups) resides in AWS `ap-south-1` (Mumbai) to comply with RBI data localization guidelines. |
| **Tenant Isolation** | PostgreSQL Row-Level Security (RLS) enforces hard isolation at the database layer. No application-level filtering alone -- every query is governed by RLS policy. |
| **Cost Awareness** | Claude API is the dominant variable cost. Per-user daily limits, cost tracking, and queuing prevent runaway spend. |
| **Single-VM Start** | Architecture targets a single VM deployment (Docker Compose) for the first 5,000 users, with a clear scaling path beyond. |

### Target Scale

| Phase | Users | Infrastructure |
|-------|-------|---------------|
| Phase 1 (Launch) | 0 -- 5,000 | Single VM, Docker Compose |
| Phase 2 (Growth) | 5,000 -- 20,000 | Managed database, separate workers |
| Phase 3 (Scale) | 20,000+ | Kubernetes, read replicas, CDN |

---

## 2. Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| **Backend** | FastAPI (Python 3.12) + Gunicorn/Uvicorn (4 workers) | Async-native, first-class Pydantic integration for request/response validation, excellent for Claude API calls (async HTTP), strong typing with Python 3.12 features. |
| **Frontend** | Vite + React 18 SPA | No SSR needed (dashboard app, not content site). Vite provides sub-second HMR. React ecosystem is mature for complex interactive UIs. |
| **Database** | PostgreSQL 16 + PgBouncer (transaction mode) | RLS for tenant isolation, JSONB for flexible user preferences, excellent indexing (GIN for arrays, B-tree composites), mature ecosystem. PgBouncer keeps connection count manageable under Gunicorn workers. |
| **Auth** | JWT + Google OAuth2 + Phone OTP (MSG91) | Google OAuth covers the majority of Indian smartphone users. Phone OTP via MSG91 serves users without Google accounts (affordable Indian SMS gateway with DLT compliance). JWT enables stateless API auth. |
| **Background Jobs** | Celery 5.4 + Redis (broker) | Distributed task execution with retries, rate limiting per queue, priority queues, Celery Beat for cron-like scheduling, dead-letter handling. |
| **File Storage** | AWS S3 (`ap-south-1` Mumbai) | RBI data localization compliance. Pre-signed URLs for direct upload/download. Lifecycle rules for cost management. |
| **Cache** | Redis 7 (single instance, shared with Celery broker) | Rate limiting (sliding window via sorted sets), dashboard cache, OTP storage with TTL, session blacklist. |
| **Monitoring** | Sentry + Prometheus + structlog | Sentry for real-time error tracking with context (user, request). Prometheus for metrics (latency histograms, queue depth, API cost counters). structlog for structured JSON logs. |
| **Reverse Proxy** | Caddy 2 | Automatic HTTPS via Let's Encrypt (zero-config TLS), HTTP/2, clean Caddyfile syntax, built-in compression. |
| **Charts** | Recharts | Declarative React-native charting API, composable components, responsive, good TypeScript support. |
| **UI Framework** | Tailwind CSS 3 | Utility-first, tree-shaken in production, consistent design without custom CSS sprawl. |
| **Form Handling** | react-hook-form + zod | Performant (uncontrolled inputs), schema-based validation that mirrors backend Pydantic schemas. |
| **State Management** | Zustand (client) + TanStack Query (server) | Zustand for auth/UI state (minimal boilerplate). TanStack Query for server state (caching, background refetch, optimistic updates). |

### Key Library Versions

```
# Backend
fastapi==0.115.*
uvicorn[standard]==0.34.*
gunicorn==23.*
sqlalchemy==2.0.*
alembic==1.14.*
asyncpg==0.30.*
celery[redis]==5.4.*
anthropic==0.42.*
pydantic==2.10.*
python-jose[cryptography]==3.3.*
passlib[bcrypt]==1.7.*
httpx==0.28.*
boto3==1.36.*
pillow==11.*
sentry-sdk[fastapi,sqlalchemy,celery]==2.*
prometheus-fastapi-instrumentator==7.*
structlog==24.*

# Frontend
react@18, react-dom@18
react-router-dom@6
@tanstack/react-query@5
zustand@4
axios@1
recharts@2
date-fns@3
react-hook-form@7
zod@3
react-dropzone@14
tailwindcss@3
```

---

## 3. Directory Structure

```
expense-tracker/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                          # FastAPI app factory, middleware registration, lifespan
│   │   │
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   ├── router.py                    # /auth/* endpoints
│   │   │   ├── service.py                   # Business logic: register, login, token refresh
│   │   │   ├── models.py                    # SQLAlchemy: User, RefreshToken
│   │   │   ├── schemas.py                   # Pydantic: RegisterRequest, LoginRequest, TokenResponse
│   │   │   ├── dependencies.py              # get_current_user, get_current_user_optional
│   │   │   ├── oauth.py                     # Google OAuth2 flow (authorization URL, callback, token exchange)
│   │   │   └── otp.py                       # MSG91 OTP request/verify, Redis OTP storage
│   │   │
│   │   ├── transactions/
│   │   │   ├── __init__.py
│   │   │   ├── router.py                    # /transactions/* CRUD + cursor pagination
│   │   │   ├── service.py                   # Transaction CRUD, balance recalculation
│   │   │   ├── models.py                    # SQLAlchemy: Transaction, RecurringTransaction
│   │   │   └── schemas.py                   # Pydantic: TransactionCreate, TransactionResponse, CursorPage
│   │   │
│   │   ├── categories/
│   │   │   ├── __init__.py
│   │   │   ├── router.py                    # /categories/* CRUD
│   │   │   ├── service.py                   # Category CRUD, system default seeding
│   │   │   ├── models.py                    # SQLAlchemy: Category (hierarchical, self-referencing)
│   │   │   └── schemas.py                   # Pydantic: CategoryCreate, CategoryTree
│   │   │
│   │   ├── accounts/
│   │   │   ├── __init__.py
│   │   │   ├── router.py                    # /accounts/* CRUD
│   │   │   ├── service.py                   # Account CRUD, balance queries
│   │   │   ├── models.py                    # SQLAlchemy: Account
│   │   │   └── schemas.py                   # Pydantic: AccountCreate, AccountResponse
│   │   │
│   │   ├── investments/
│   │   │   ├── __init__.py
│   │   │   ├── router.py                    # /investments/* holdings, transactions, summary
│   │   │   ├── service.py                   # Portfolio logic, XIRR calculations, gain/loss
│   │   │   ├── models.py                    # SQLAlchemy: InvestmentHolding, InvestmentTransaction, BondDetail
│   │   │   └── schemas.py                   # Pydantic: HoldingCreate, InvestmentSummary
│   │   │
│   │   ├── budgets/
│   │   │   ├── __init__.py
│   │   │   ├── router.py                    # /budgets/* CRUD
│   │   │   ├── service.py                   # Budget CRUD, spend tracking, alerts
│   │   │   ├── models.py                    # SQLAlchemy: Budget
│   │   │   └── schemas.py                   # Pydantic: BudgetCreate, BudgetStatus
│   │   │
│   │   ├── screenshots/
│   │   │   ├── __init__.py
│   │   │   ├── router.py                    # /screenshots/* upload, status, result, confirm
│   │   │   ├── service.py                   # Upload orchestration, status tracking
│   │   │   ├── parser.py                    # Claude Vision API integration, prompt template, response parsing
│   │   │   ├── models.py                    # SQLAlchemy: ScreenshotParseLog
│   │   │   └── schemas.py                   # Pydantic: UploadResponse, ParseResult, ConfirmRequest
│   │   │
│   │   ├── dashboard/
│   │   │   ├── __init__.py
│   │   │   ├── router.py                    # /dashboard/* summary, breakdown, trend, budget-status, net-worth
│   │   │   ├── service.py                   # Aggregation queries, caching
│   │   │   └── schemas.py                   # Pydantic: DashboardSummary, CategoryBreakdown, Trend
│   │   │
│   │   ├── export/
│   │   │   ├── __init__.py
│   │   │   ├── router.py                    # /users/me/export
│   │   │   └── service.py                   # CSV/JSON export, S3 upload, signed URL
│   │   │
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py                    # Pydantic Settings: all env vars, validation
│   │   │   ├── database.py                  # Async SQLAlchemy engine, session factory, RLS context manager
│   │   │   ├── redis.py                     # Redis connection pool, helper methods
│   │   │   ├── storage.py                   # S3 client wrapper: upload, download, presigned URLs
│   │   │   ├── security.py                  # JWT encode/decode, password hashing, token generation
│   │   │   ├── rate_limit.py                # Redis sliding window rate limiter
│   │   │   ├── pagination.py                # Cursor-based pagination utilities
│   │   │   ├── exceptions.py                # Custom exceptions + global exception handlers
│   │   │   └── middleware.py                # RLS middleware, request logging, CORS, timing
│   │   │
│   │   └── tasks/
│   │       ├── __init__.py
│   │       ├── celery_app.py                # Celery app factory, queue routing, Beat schedule
│   │       ├── screenshot_tasks.py          # parse_screenshot task (calls Claude Vision)
│   │       ├── recurring_tasks.py           # generate_recurring_transactions (daily)
│   │       ├── price_tasks.py               # fetch_investment_prices (BSE/NSE APIs, gold price)
│   │       ├── export_tasks.py              # generate_export (CSV/JSON → S3)
│   │       └── cleanup_tasks.py             # soft_delete_cleanup, expired_token_cleanup
│   │
│   ├── tests/
│   │   ├── conftest.py                      # Fixtures: test DB, async client, auth headers, factories
│   │   ├── unit/
│   │   │   ├── test_auth_service.py
│   │   │   ├── test_transaction_service.py
│   │   │   ├── test_screenshot_parser.py
│   │   │   ├── test_budget_service.py
│   │   │   └── test_investment_service.py
│   │   ├── integration/
│   │   │   ├── test_auth_flow.py
│   │   │   ├── test_transaction_crud.py
│   │   │   ├── test_screenshot_pipeline.py
│   │   │   ├── test_rls_isolation.py
│   │   │   └── test_dashboard.py
│   │   └── factories.py                     # Factory Boy factories for all models
│   │
│   ├── alembic/
│   │   ├── alembic.ini
│   │   ├── env.py
│   │   └── versions/                        # Migration files
│   │
│   ├── pyproject.toml                       # Project metadata, tool configs (ruff, mypy, pytest)
│   ├── Dockerfile
│   └── requirements/
│       ├── base.txt                         # Core dependencies
│       ├── dev.txt                          # Testing, linting, debugging
│       └── prod.txt                         # Gunicorn, Sentry SDK
│
├── frontend/
│   ├── src/
│   │   ├── main.tsx                         # React DOM root, QueryClientProvider, RouterProvider
│   │   ├── App.tsx                          # Root layout, auth guard
│   │   ├── router.tsx                       # react-router-dom route definitions
│   │   │
│   │   ├── api/
│   │   │   ├── client.ts                    # Axios instance with interceptor (auto-refresh)
│   │   │   ├── auth.ts                      # Login, register, OAuth, OTP, refresh, logout
│   │   │   ├── transactions.ts              # CRUD + pagination
│   │   │   ├── categories.ts
│   │   │   ├── accounts.ts
│   │   │   ├── budgets.ts
│   │   │   ├── investments.ts
│   │   │   ├── screenshots.ts
│   │   │   └── dashboard.ts
│   │   │
│   │   ├── components/
│   │   │   ├── ui/                          # Button, Input, Select, Modal, Card, Badge, Spinner, Toast
│   │   │   ├── layout/                      # Sidebar, Header, MobileNav, PageContainer
│   │   │   ├── auth/                        # LoginForm, RegisterForm, GoogleButton, OtpInput
│   │   │   ├── transactions/                # TransactionList, TransactionForm, TransactionFilters
│   │   │   ├── categories/                  # CategoryPicker, CategoryManager
│   │   │   ├── accounts/                    # AccountCard, AccountForm
│   │   │   ├── budgets/                     # BudgetCard, BudgetForm, BudgetProgressBar
│   │   │   ├── investments/                 # HoldingCard, InvestmentForm, PortfolioSummary
│   │   │   ├── screenshots/                 # DropZone, ParsePreview, ConfirmForm
│   │   │   └── dashboard/                   # SummaryCards, CategoryPieChart, TrendLineChart, NetWorthChart
│   │   │
│   │   ├── hooks/
│   │   │   ├── useAuth.ts                   # Auth state + actions (wraps Zustand store)
│   │   │   ├── useTransactions.ts           # TanStack Query hooks for transactions
│   │   │   ├── useDashboard.ts              # TanStack Query hooks for dashboard data
│   │   │   └── useInfiniteScroll.ts         # Intersection observer + cursor pagination
│   │   │
│   │   ├── stores/
│   │   │   ├── authStore.ts                 # Zustand: user, accessToken, isAuthenticated, actions
│   │   │   └── uiStore.ts                   # Zustand: sidebar open, theme, toasts
│   │   │
│   │   ├── lib/
│   │   │   ├── format.ts                    # formatINR(), formatDate(), formatFY()
│   │   │   ├── validation.ts                # Zod schemas (mirrors backend Pydantic)
│   │   │   └── constants.ts                 # Category icons, account types, investment types
│   │   │
│   │   ├── types/
│   │   │   └── index.ts                     # TypeScript interfaces matching API response shapes
│   │   │
│   │   └── styles/
│   │       └── globals.css                  # Tailwind base + custom utility classes
│   │
│   ├── public/
│   │   └── favicon.ico
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── Dockerfile                           # Multi-stage: build → nginx
│   └── package.json
│
├── docker/
│   ├── docker-compose.yml                   # Development: all services
│   ├── docker-compose.prod.yml              # Production overrides
│   ├── caddy/
│   │   └── Caddyfile
│   ├── pgbouncer/
│   │   └── pgbouncer.ini
│   └── redis/
│       └── redis.conf
│
├── scripts/
│   ├── seed_categories.py                   # Seed system default categories for Indian context
│   ├── create_test_user.py                  # Create a test user with sample data
│   └── backup_db.sh                         # pg_dump → gzip → S3 upload
│
├── docs/
│   ├── architecture.md                      # This document
│   ├── security.md                          # Security policies, threat model
│   ├── api.md                               # OpenAPI supplement (usage examples, auth flow)
│   └── epics-and-stories.md                 # Product backlog with story points
│
├── .env.example                             # All environment variables with documentation
├── .gitignore
└── README.md
```

---

## 4. Authentication & Authorization

### 4.1 Authentication Methods

| Method | Priority | Use Case |
|--------|----------|----------|
| **Google OAuth2** | Primary | Majority of Indian smartphone users have Google accounts. Lowest friction. |
| **Phone OTP (MSG91)** | Secondary | Users without Google accounts, or preferring phone-based auth. MSG91 is an Indian SMS gateway with DLT registration compliance. |
| **Email + Password** | Tertiary | Fallback for users who want traditional credentials. |

### 4.2 Token Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                      TOKEN ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Access Token (JWT)              Refresh Token (Opaque)      │
│  ─────────────────               ──────────────────────      │
│  Stored: In-memory (Zustand)     Stored: httpOnly cookie     │
│  Lifetime: 15 minutes            Lifetime: 30 days           │
│  Payload: {user_id, email}       Stored in DB: yes           │
│  Signed: HS256                   Format: 64-char hex         │
│  Sent: Authorization header      Sent: Cookie (auto)         │
│                                                              │
│  On 401 → POST /auth/refresh → New access token             │
│  On refresh fail → Redirect to /login                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Access Token JWT Payload:**

```json
{
  "sub": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "iat": 1711700000,
  "exp": 1711700900,
  "type": "access"
}
```

**Why this split:**

- Access tokens in memory are immune to XSS-based token theft (no localStorage).
- Refresh tokens as httpOnly cookies are immune to JavaScript access.
- Short access token lifetime limits blast radius of token compromise.
- Refresh token rotation: each use issues a new refresh token and invalidates the old one (detect token reuse = compromise).

### 4.3 Google OAuth2 Flow

```
User clicks "Sign in with Google"
  → Frontend redirects to: GET /auth/google
  → Backend generates Google authorization URL with state parameter
  → User authenticates with Google
  → Google redirects to: GET /auth/google/callback?code=...&state=...
  → Backend exchanges code for Google tokens
  → Backend extracts email, name, google_id from ID token
  → Backend finds or creates User record
  → Backend issues access token + refresh token
  → Backend redirects to frontend with tokens set
```

### 4.4 Phone OTP Flow

```
POST /auth/otp/request  { phone: "+919876543210" }
  → Rate limit: 3 requests per phone per hour
  → Generate 6-digit OTP
  → Store in Redis: otp:{phone} = {otp, attempts: 0} TTL 300s
  → Send via MSG91 Transactional SMS API
  → Response: { message: "OTP sent", expires_in: 300 }

POST /auth/otp/verify   { phone: "+919876543210", otp: "482901" }
  → Fetch from Redis: otp:{phone}
  → If attempts >= 5: delete key, return 429
  → If OTP matches: find/create user, issue tokens
  → If OTP wrong: increment attempts, return 401
```

### 4.5 Row-Level Security (RLS) for Tenant Isolation

RLS is the **primary** isolation mechanism. Even if application code has a bug that omits a `WHERE user_id = ...` clause, the database will enforce isolation.

**How it works:**

1. Every data table has a `user_id UUID NOT NULL` column.
2. RLS is enabled on every data table.
3. Policies check `user_id = current_setting('app.current_user_id')::uuid`.
4. The FastAPI middleware sets this variable at the start of every database transaction.

**Middleware implementation pattern:**

```python
# core/database.py

from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

@asynccontextmanager
async def get_db_session(user_id: str | None = None):
    """
    Yields an AsyncSession with RLS context set.
    Every query within this session is automatically filtered
    by the user's ID at the database level.
    """
    async with async_session_factory() as session:
        async with session.begin():
            if user_id:
                # SET LOCAL scopes to this transaction only.
                # Even if connection is reused via PgBouncer,
                # the setting does not leak to the next transaction.
                await session.execute(
                    text("SET LOCAL app.current_user_id = :uid"),
                    {"uid": user_id}
                )
            yield session
```

**Dependency injection in routes:**

```python
# auth/dependencies.py

from fastapi import Depends, Request
from app.core.database import get_db_session

async def get_current_user(request: Request):
    """Extract and validate JWT, return user_id."""
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    payload = decode_access_token(token)  # raises 401 on failure
    return payload["sub"]  # user_id (UUID string)

async def get_db(user_id: str = Depends(get_current_user)):
    """Provide a database session with RLS context for the authenticated user."""
    async with get_db_session(user_id=user_id) as session:
        yield session
```

### 4.6 Rate Limiting

| Endpoint Pattern | Limit | Window | Key |
|-----------------|-------|--------|-----|
| `POST /auth/register` | 5 | per hour | IP |
| `POST /auth/login` | 10 | per minute | IP |
| `POST /auth/otp/request` | 3 | per hour | phone number |
| `POST /auth/otp/verify` | 5 attempts | per OTP | phone number |
| `POST /auth/refresh` | 30 | per minute | user_id |
| `POST /screenshots/upload` | 50 | per day | user_id |
| All other authenticated | 200 | per minute | user_id |

**Implementation:** Redis sliding window (sorted set with timestamps).

```python
# core/rate_limit.py

import time
from app.core.redis import redis_client

async def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """
    Sliding window rate limiter using Redis sorted sets.
    Returns True if request is allowed, False if rate limited.
    """
    now = time.time()
    pipe = redis_client.pipeline()

    # Remove entries outside the window
    pipe.zremrangebyscore(key, 0, now - window_seconds)
    # Add current request
    pipe.zadd(key, {f"{now}": now})
    # Count entries in window
    pipe.zcard(key)
    # Set expiry on the key itself
    pipe.expire(key, window_seconds)

    results = await pipe.execute()
    count = results[2]

    return count <= limit
```

---

## 5. Complete Database Schema

### 5.1 Initialization and RLS Setup

```sql
-- ============================================================
-- EXTENSIONS
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";      -- UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";        -- Cryptographic functions

-- ============================================================
-- APPLICATION ROLE
-- ============================================================
-- The application connects as this role. RLS policies apply to it.
-- The migration/admin role is a superuser that bypasses RLS.
CREATE ROLE app_user LOGIN PASSWORD 'changeme';

-- ============================================================
-- HELPER: RLS POLICY FUNCTION
-- ============================================================
-- Returns the current user_id set by the application middleware.
-- Used in all RLS policies for consistency.
CREATE OR REPLACE FUNCTION current_app_user_id()
RETURNS uuid AS $$
BEGIN
    RETURN current_setting('app.current_user_id', true)::uuid;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;
```

### 5.2 Users Table

```sql
-- ============================================================
-- USERS
-- ============================================================
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) UNIQUE,
    phone           VARCHAR(15) UNIQUE,               -- E.164 format: +919876543210
    google_id       VARCHAR(255) UNIQUE,
    password_hash   VARCHAR(255),                      -- bcrypt, NULL for OAuth/OTP-only users
    full_name       VARCHAR(255) NOT NULL,
    avatar_url      VARCHAR(1024),

    -- User preferences stored as JSONB for flexibility
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

    daily_api_cost_limit_paise  INTEGER NOT NULL DEFAULT 500,  -- 500 paise = Rs 5/day

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Users table does NOT have RLS -- it is accessed via direct lookup (login, profile).
-- All other tables reference users.id and have RLS.

CREATE INDEX idx_users_email ON users (email) WHERE email IS NOT NULL;
CREATE INDEX idx_users_phone ON users (phone) WHERE phone IS NOT NULL;
CREATE INDEX idx_users_google_id ON users (google_id) WHERE google_id IS NOT NULL;

-- Ensure at least one auth method exists
ALTER TABLE users ADD CONSTRAINT chk_auth_method
    CHECK (email IS NOT NULL OR phone IS NOT NULL OR google_id IS NOT NULL);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### 5.3 Refresh Tokens

```sql
-- ============================================================
-- REFRESH TOKENS
-- ============================================================
CREATE TABLE refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      VARCHAR(128) NOT NULL UNIQUE,      -- SHA-256 of the opaque token
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at      TIMESTAMPTZ,                       -- NULL = active, set = revoked
    replaced_by     UUID REFERENCES refresh_tokens(id), -- Token rotation chain
    user_agent      VARCHAR(512),
    ip_address      INET
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens (user_id);
CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens (token_hash) WHERE revoked_at IS NULL;
CREATE INDEX idx_refresh_tokens_expires ON refresh_tokens (expires_at) WHERE revoked_at IS NULL;

-- No RLS on refresh_tokens: accessed by token_hash lookup during refresh flow,
-- and by user_id during logout/revoke-all.
```

### 5.4 Categories (Hierarchical)

```sql
-- ============================================================
-- CATEGORIES (hierarchical, self-referencing)
-- ============================================================
CREATE TYPE category_type AS ENUM ('income', 'expense');

CREATE TABLE categories (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,  -- NULL = system default
    parent_id       UUID REFERENCES categories(id) ON DELETE CASCADE,
    name            VARCHAR(100) NOT NULL,
    type            category_type NOT NULL,
    icon            VARCHAR(50),                       -- emoji or icon identifier
    color           VARCHAR(7),                        -- hex color code
    is_system       BOOLEAN NOT NULL DEFAULT false,    -- system defaults cannot be deleted
    sort_order      INTEGER NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Unique constraint: no duplicate names within same user+parent+type
CREATE UNIQUE INDEX idx_categories_unique_name
    ON categories (COALESCE(user_id, '00000000-0000-0000-0000-000000000000'),
                   COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'),
                   type, lower(name));

CREATE INDEX idx_categories_user_id ON categories (user_id);
CREATE INDEX idx_categories_parent_id ON categories (parent_id);

-- RLS: users see system categories (user_id IS NULL) + their own
ALTER TABLE categories ENABLE ROW LEVEL SECURITY;

CREATE POLICY categories_select ON categories FOR SELECT TO app_user
    USING (user_id IS NULL OR user_id = current_app_user_id());

CREATE POLICY categories_insert ON categories FOR INSERT TO app_user
    WITH CHECK (user_id = current_app_user_id());

CREATE POLICY categories_update ON categories FOR UPDATE TO app_user
    USING (user_id = current_app_user_id() AND is_system = false);

CREATE POLICY categories_delete ON categories FOR DELETE TO app_user
    USING (user_id = current_app_user_id() AND is_system = false);

CREATE TRIGGER trg_categories_updated_at
    BEFORE UPDATE ON categories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

**System Default Categories (India-contextual):**

```
EXPENSE:
├── Food & Dining
│   ├── Groceries (Kirana, BigBasket, Zepto)
│   ├── Restaurants
│   ├── Swiggy / Zomato
│   └── Chai / Snacks
├── Transport
│   ├── Petrol / Diesel
│   ├── Ola / Uber
│   ├── Metro / Bus
│   └── Auto
├── Shopping
│   ├── Amazon / Flipkart
│   ├── Clothing
│   └── Electronics
├── Bills & Utilities
│   ├── Electricity
│   ├── Mobile Recharge
│   ├── Internet / WiFi
│   ├── Gas (Piped / Cylinder)
│   ├── Water
│   └── DTH
├── Housing
│   ├── Rent
│   ├── Maintenance (Society)
│   └── Home Repairs
├── Health
│   ├── Medicines (Apollo / 1mg)
│   ├── Doctor Consultation
│   ├── Lab Tests
│   └── Insurance Premium
├── Education
│   ├── School / College Fees
│   ├── Books / Stationery
│   └── Courses (Udemy, etc.)
├── Entertainment
│   ├── Movies / Netflix
│   ├── Games
│   └── Outings
├── Personal Care
├── Travel / Holiday
├── Gifts & Donations
│   ├── Gifts
│   └── Donations / Temple
├── EMI & Loans
│   ├── Home Loan EMI
│   ├── Car Loan EMI
│   ├── Personal Loan EMI
│   └── Credit Card Payment
├── Taxes
│   ├── Income Tax
│   └── Property Tax
├── Insurance
│   ├── Life Insurance
│   ├── Health Insurance
│   └── Vehicle Insurance
├── Domestic Help (Maid, Cook, Driver)
└── Miscellaneous

INCOME:
├── Salary
├── Freelance / Consulting
├── Business Income
├── Interest Income
├── Dividend Income
├── Rental Income
├── Capital Gains
├── Cashback / Rewards
└── Other Income
```

### 5.5 Accounts

```sql
-- ============================================================
-- ACCOUNTS
-- ============================================================
CREATE TYPE account_type AS ENUM (
    'savings', 'current', 'credit_card', 'wallet', 'cash', 'loan'
);

CREATE TABLE accounts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(100) NOT NULL,
    type            account_type NOT NULL,
    bank_name       VARCHAR(100),                      -- e.g., SBI, HDFC, Paytm
    balance         DECIMAL(14,2) NOT NULL DEFAULT 0,  -- Current balance
    -- For credit cards:
    credit_limit    DECIMAL(14,2),
    billing_day     SMALLINT CHECK (billing_day BETWEEN 1 AND 31),
    -- Metadata
    icon            VARCHAR(50),
    color           VARCHAR(7),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    is_default      BOOLEAN NOT NULL DEFAULT false,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_accounts_user_id ON accounts (user_id);

-- Only one default account per user
CREATE UNIQUE INDEX idx_accounts_default
    ON accounts (user_id) WHERE is_default = true AND is_active = true;

ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;

CREATE POLICY accounts_all ON accounts FOR ALL TO app_user
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());

CREATE TRIGGER trg_accounts_updated_at
    BEFORE UPDATE ON accounts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### 5.6 Transactions

```sql
-- ============================================================
-- TRANSACTIONS
-- ============================================================
CREATE TYPE transaction_type AS ENUM ('income', 'expense', 'transfer');

CREATE TABLE transactions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id      UUID NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    category_id     UUID REFERENCES categories(id) ON DELETE SET NULL,

    type            transaction_type NOT NULL,
    amount          DECIMAL(12,2) NOT NULL CHECK (amount > 0),

    -- For transfers between accounts
    to_account_id   UUID REFERENCES accounts(id) ON DELETE RESTRICT,

    description     VARCHAR(500),
    notes           TEXT,
    tags            TEXT[] DEFAULT '{}',                -- e.g., {'reimbursable', 'tax-deductible'}

    transaction_date TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Screenshot reference (if created via screenshot parsing)
    screenshot_parse_log_id UUID REFERENCES screenshot_parse_logs(id) ON DELETE SET NULL,

    -- Recurring transaction reference
    recurring_transaction_id UUID REFERENCES recurring_transactions(id) ON DELETE SET NULL,

    -- Soft delete
    is_deleted      BOOLEAN NOT NULL DEFAULT false,
    deleted_at      TIMESTAMPTZ,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- TRANSACTION INDEXES
-- ============================================================

-- Primary query pattern: user's transactions by date (cursor pagination)
CREATE INDEX idx_txn_user_date ON transactions (user_id, transaction_date DESC, id DESC)
    WHERE is_deleted = false;

-- Filter by account
CREATE INDEX idx_txn_user_account ON transactions (user_id, account_id, transaction_date DESC)
    WHERE is_deleted = false;

-- Filter by category
CREATE INDEX idx_txn_user_category ON transactions (user_id, category_id, transaction_date DESC)
    WHERE is_deleted = false;

-- Filter by type
CREATE INDEX idx_txn_user_type ON transactions (user_id, type, transaction_date DESC)
    WHERE is_deleted = false;

-- Dashboard: monthly aggregations
CREATE INDEX idx_txn_user_type_date ON transactions (user_id, type, transaction_date)
    WHERE is_deleted = false;

-- Tag-based search (GIN index on array column)
CREATE INDEX idx_txn_tags ON transactions USING GIN (tags)
    WHERE is_deleted = false;

-- ============================================================
-- TRANSACTION RLS
-- ============================================================
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY transactions_all ON transactions FOR ALL TO app_user
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());

CREATE TRIGGER trg_transactions_updated_at
    BEFORE UPDATE ON transactions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- ACCOUNT BALANCE TRIGGER
-- ============================================================
-- Automatically update account balance when transactions are inserted/updated/deleted.
CREATE OR REPLACE FUNCTION update_account_balance()
RETURNS TRIGGER AS $$
BEGIN
    -- Recalculate balance for the affected account(s)
    IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
        UPDATE accounts SET balance = (
            SELECT COALESCE(SUM(
                CASE
                    WHEN t.type = 'income' THEN t.amount
                    WHEN t.type = 'expense' THEN -t.amount
                    WHEN t.type = 'transfer' AND t.account_id = NEW.account_id THEN -t.amount
                    WHEN t.type = 'transfer' AND t.to_account_id = NEW.account_id THEN t.amount
                    ELSE 0
                END
            ), 0)
            FROM transactions t
            WHERE t.account_id = NEW.account_id OR t.to_account_id = NEW.account_id
            AND t.is_deleted = false
        )
        WHERE id = NEW.account_id;

        -- Handle transfer destination account
        IF NEW.type = 'transfer' AND NEW.to_account_id IS NOT NULL THEN
            UPDATE accounts SET balance = (
                SELECT COALESCE(SUM(
                    CASE
                        WHEN t.type = 'income' THEN t.amount
                        WHEN t.type = 'expense' THEN -t.amount
                        WHEN t.type = 'transfer' AND t.account_id = NEW.to_account_id THEN -t.amount
                        WHEN t.type = 'transfer' AND t.to_account_id = NEW.to_account_id THEN t.amount
                        ELSE 0
                    END
                ), 0)
                FROM transactions t
                WHERE t.account_id = NEW.to_account_id OR t.to_account_id = NEW.to_account_id
                AND t.is_deleted = false
            )
            WHERE id = NEW.to_account_id;
        END IF;
    END IF;

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_account_balance
    AFTER INSERT OR UPDATE OR DELETE ON transactions
    FOR EACH ROW EXECUTE FUNCTION update_account_balance();
```

### 5.7 Recurring Transactions

```sql
-- ============================================================
-- RECURRING TRANSACTIONS
-- ============================================================
CREATE TYPE recurrence_frequency AS ENUM (
    'daily', 'weekly', 'biweekly', 'monthly', 'quarterly', 'yearly'
);

CREATE TABLE recurring_transactions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id      UUID NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    category_id     UUID REFERENCES categories(id) ON DELETE SET NULL,

    type            transaction_type NOT NULL,
    amount          DECIMAL(12,2) NOT NULL CHECK (amount > 0),
    description     VARCHAR(500),
    tags            TEXT[] DEFAULT '{}',

    frequency       recurrence_frequency NOT NULL,

    -- For weekly: day of week (0=Mon, 6=Sun)
    -- For monthly: day of month (1-31, 28+ will use last day of month)
    -- For yearly: stored as MMDD
    schedule_day    SMALLINT,

    start_date      DATE NOT NULL,
    end_date        DATE,                              -- NULL = no end
    next_due_date   DATE NOT NULL,
    last_generated  TIMESTAMPTZ,

    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_recurring_user ON recurring_transactions (user_id);
CREATE INDEX idx_recurring_next_due ON recurring_transactions (next_due_date)
    WHERE is_active = true;

ALTER TABLE recurring_transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY recurring_all ON recurring_transactions FOR ALL TO app_user
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());

CREATE TRIGGER trg_recurring_updated_at
    BEFORE UPDATE ON recurring_transactions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### 5.8 Budgets

```sql
-- ============================================================
-- BUDGETS (Financial Year aware)
-- ============================================================
CREATE TYPE budget_period AS ENUM ('monthly', 'quarterly', 'yearly');

CREATE TABLE budgets (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id     UUID REFERENCES categories(id) ON DELETE CASCADE,  -- NULL = overall budget

    amount          DECIMAL(12,2) NOT NULL CHECK (amount > 0),
    period          budget_period NOT NULL DEFAULT 'monthly',

    -- Financial Year: e.g., 2026 means FY 2026-27 (April 2026 - March 2027)
    fy_year         SMALLINT NOT NULL,

    -- Alert when spend reaches this % of budget
    alert_threshold SMALLINT NOT NULL DEFAULT 80 CHECK (alert_threshold BETWEEN 1 AND 100),
    alert_sent      BOOLEAN NOT NULL DEFAULT false,

    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One budget per category per FY per user
CREATE UNIQUE INDEX idx_budgets_unique
    ON budgets (user_id, COALESCE(category_id, '00000000-0000-0000-0000-000000000000'), fy_year)
    WHERE is_active = true;

CREATE INDEX idx_budgets_user_fy ON budgets (user_id, fy_year);

ALTER TABLE budgets ENABLE ROW LEVEL SECURITY;

CREATE POLICY budgets_all ON budgets FOR ALL TO app_user
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());

CREATE TRIGGER trg_budgets_updated_at
    BEFORE UPDATE ON budgets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- FY HELPER FUNCTION
-- ============================================================
-- Given a date, returns the FY year (e.g., 2026-01-15 → 2025, 2026-04-15 → 2026).
-- FY 2026 = April 2026 to March 2027.
CREATE OR REPLACE FUNCTION get_fy_year(d DATE)
RETURNS SMALLINT AS $$
BEGIN
    IF EXTRACT(MONTH FROM d) >= 4 THEN
        RETURN EXTRACT(YEAR FROM d)::SMALLINT;
    ELSE
        RETURN (EXTRACT(YEAR FROM d) - 1)::SMALLINT;
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- FY date range helper
CREATE OR REPLACE FUNCTION get_fy_range(fy SMALLINT)
RETURNS TABLE(fy_start DATE, fy_end DATE) AS $$
BEGIN
    RETURN QUERY SELECT
        make_date(fy, 4, 1),
        make_date(fy + 1, 3, 31);
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

### 5.9 Investment Holdings

```sql
-- ============================================================
-- INVESTMENT HOLDINGS
-- ============================================================
CREATE TYPE investment_type AS ENUM (
    'equity',        -- Direct stocks (BSE/NSE)
    'mutual_fund',   -- Mutual funds (AMFI codes)
    'etf',           -- Exchange-traded funds
    'fd',            -- Fixed Deposit
    'rd',            -- Recurring Deposit
    'ppf',           -- Public Provident Fund
    'nps',           -- National Pension System
    'bond',          -- Government/corporate bonds
    'gold'           -- Digital gold, sovereign gold bonds, physical
);

CREATE TABLE investment_holdings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    type            investment_type NOT NULL,
    name            VARCHAR(255) NOT NULL,             -- e.g., "HDFC Bank", "SBI Bluechip Fund"
    symbol          VARCHAR(50),                       -- BSE/NSE code, AMFI code

    -- Quantity and pricing
    quantity        DECIMAL(14,4) NOT NULL DEFAULT 0,  -- Fractional for MF/gold
    avg_buy_price   DECIMAL(14,4) NOT NULL DEFAULT 0,  -- Weighted average
    current_price   DECIMAL(14,4),                     -- Last fetched price
    current_value   DECIMAL(14,2) GENERATED ALWAYS AS (quantity * COALESCE(current_price, avg_buy_price)) STORED,

    -- For FD/RD/PPF
    invested_amount DECIMAL(14,2),                     -- Principal
    maturity_amount DECIMAL(14,2),
    interest_rate   DECIMAL(5,2),                      -- Annual %
    maturity_date   DATE,

    -- Metadata
    broker          VARCHAR(100),                      -- Zerodha, Groww, etc.
    demat_account   VARCHAR(50),
    notes           TEXT,

    price_updated_at TIMESTAMPTZ,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_holdings_user ON investment_holdings (user_id);
CREATE INDEX idx_holdings_user_type ON investment_holdings (user_id, type);
CREATE INDEX idx_holdings_symbol ON investment_holdings (symbol) WHERE symbol IS NOT NULL;

ALTER TABLE investment_holdings ENABLE ROW LEVEL SECURITY;

CREATE POLICY holdings_all ON investment_holdings FOR ALL TO app_user
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());

CREATE TRIGGER trg_holdings_updated_at
    BEFORE UPDATE ON investment_holdings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### 5.10 Investment Transactions

```sql
-- ============================================================
-- INVESTMENT TRANSACTIONS
-- ============================================================
CREATE TYPE investment_txn_type AS ENUM (
    'buy', 'sell', 'dividend', 'interest', 'split', 'bonus', 'sip'
);

CREATE TABLE investment_transactions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    holding_id      UUID NOT NULL REFERENCES investment_holdings(id) ON DELETE CASCADE,

    type            investment_txn_type NOT NULL,
    quantity        DECIMAL(14,4),                     -- NULL for dividend/interest
    price_per_unit  DECIMAL(14,4),                     -- NULL for dividend/interest/split/bonus
    amount          DECIMAL(14,2) NOT NULL,            -- Total amount (quantity * price, or dividend amount)

    -- For splits/bonus
    ratio_from      SMALLINT,                          -- e.g., 1 (from 1:2 split)
    ratio_to        SMALLINT,                          -- e.g., 2

    -- Charges
    brokerage       DECIMAL(10,2) DEFAULT 0,
    stt             DECIMAL(10,2) DEFAULT 0,           -- Securities Transaction Tax
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

CREATE INDEX idx_inv_txn_user ON investment_transactions (user_id);
CREATE INDEX idx_inv_txn_holding ON investment_transactions (holding_id, transaction_date DESC);
CREATE INDEX idx_inv_txn_user_date ON investment_transactions (user_id, transaction_date DESC)
    WHERE is_deleted = false;

ALTER TABLE investment_transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY inv_txn_all ON investment_transactions FOR ALL TO app_user
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());

CREATE TRIGGER trg_inv_txn_updated_at
    BEFORE UPDATE ON investment_transactions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### 5.11 Bond Details (1:1 Extension)

```sql
-- ============================================================
-- BOND DETAILS (1:1 extension for bonds)
-- ============================================================
CREATE TYPE coupon_frequency AS ENUM ('monthly', 'quarterly', 'semi_annual', 'annual', 'zero_coupon');
CREATE TYPE credit_rating AS ENUM (
    'AAA', 'AA+', 'AA', 'AA-', 'A+', 'A', 'A-',
    'BBB+', 'BBB', 'BBB-',
    'BB+', 'BB', 'BB-', 'B+', 'B', 'B-',
    'C', 'D', 'unrated', 'sovereign'
);

CREATE TABLE bond_details (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    holding_id          UUID NOT NULL UNIQUE REFERENCES investment_holdings(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    isin                VARCHAR(12),                   -- ISIN code
    face_value          DECIMAL(12,2) NOT NULL DEFAULT 1000,
    coupon_rate         DECIMAL(5,2),                  -- Annual coupon rate %
    coupon_frequency    coupon_frequency NOT NULL DEFAULT 'semi_annual',

    issue_date          DATE,
    maturity_date       DATE NOT NULL,
    next_coupon_date    DATE,

    credit_rating       credit_rating DEFAULT 'unrated',
    rating_agency       VARCHAR(50),                   -- CRISIL, ICRA, CARE, India Ratings

    issuer_name         VARCHAR(255),                  -- e.g., "Government of India", "HDFC Ltd"
    is_tax_free         BOOLEAN NOT NULL DEFAULT false,
    is_callable         BOOLEAN NOT NULL DEFAULT false,
    call_date           DATE,

    ytm                 DECIMAL(5,2),                  -- Yield to Maturity %

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_bond_details_holding ON bond_details (holding_id);

ALTER TABLE bond_details ENABLE ROW LEVEL SECURITY;

CREATE POLICY bond_details_all ON bond_details FOR ALL TO app_user
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());

CREATE TRIGGER trg_bond_details_updated_at
    BEFORE UPDATE ON bond_details
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### 5.12 Screenshot Parse Logs

```sql
-- ============================================================
-- SCREENSHOT PARSE LOGS (full audit trail)
-- ============================================================
CREATE TYPE parse_status AS ENUM (
    'uploaded',        -- File received, queued
    'processing',      -- Celery task picked up
    'parsed',          -- Claude returned structured data
    'confirmed',       -- User confirmed and transaction created
    'rejected',        -- User rejected the parsed result
    'failed'           -- Parsing failed (Claude error, validation error, etc.)
);

CREATE TABLE screenshot_parse_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- File info
    s3_key          VARCHAR(1024) NOT NULL,
    original_filename VARCHAR(255),
    file_size_bytes INTEGER NOT NULL,
    mime_type       VARCHAR(50) NOT NULL,

    -- Processing
    status          parse_status NOT NULL DEFAULT 'uploaded',

    -- Claude API details
    claude_model    VARCHAR(50),                       -- e.g., "claude-sonnet-4-20250514"
    claude_request_id VARCHAR(100),
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_usd        DECIMAL(8,6),                      -- Actual API cost for this call
    api_latency_ms  INTEGER,                           -- Response time

    -- Parsed result
    parsed_data     JSONB,                             -- Structured output from Claude
    -- parsed_data schema:
    -- {
    --   "transaction_type": "expense",
    --   "amount": 499.00,
    --   "description": "Swiggy order",
    --   "merchant": "Swiggy",
    --   "category_suggestion": "Food & Dining > Swiggy / Zomato",
    --   "transaction_date": "2026-03-28T19:30:00",
    --   "payment_method": "UPI",
    --   "upi_id": "user@okicici",
    --   "reference_number": "408123456789",
    --   "confidence": 0.95
    -- }

    -- Error info (if failed)
    error_message   TEXT,
    error_code      VARCHAR(50),

    -- Result
    transaction_id  UUID REFERENCES transactions(id) ON DELETE SET NULL,  -- Set when confirmed

    -- Timestamps
    queued_at       TIMESTAMPTZ,
    processing_started_at TIMESTAMPTZ,
    parsed_at       TIMESTAMPTZ,
    confirmed_at    TIMESTAMPTZ,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_parse_logs_user ON screenshot_parse_logs (user_id, created_at DESC);
CREATE INDEX idx_parse_logs_status ON screenshot_parse_logs (status) WHERE status IN ('uploaded', 'processing');

ALTER TABLE screenshot_parse_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY parse_logs_all ON screenshot_parse_logs FOR ALL TO app_user
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());

CREATE TRIGGER trg_parse_logs_updated_at
    BEFORE UPDATE ON screenshot_parse_logs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### 5.13 API Usage Tracking

```sql
-- ============================================================
-- API USAGE (per-user daily cost tracking)
-- ============================================================
CREATE TABLE api_usage (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date            DATE NOT NULL DEFAULT CURRENT_DATE,

    -- Counters
    screenshot_count INTEGER NOT NULL DEFAULT 0,
    total_input_tokens BIGINT NOT NULL DEFAULT 0,
    total_output_tokens BIGINT NOT NULL DEFAULT 0,
    total_cost_usd  DECIMAL(10,6) NOT NULL DEFAULT 0,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per user per day
CREATE UNIQUE INDEX idx_api_usage_user_date ON api_usage (user_id, date);

ALTER TABLE api_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY api_usage_select ON api_usage FOR SELECT TO app_user
    USING (user_id = current_app_user_id());

-- Only backend (via service role or direct insert) modifies this table.
-- Users can only read their own usage.

CREATE TRIGGER trg_api_usage_updated_at
    BEFORE UPDATE ON api_usage
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### 5.14 Audit Logs

```sql
-- ============================================================
-- AUDIT LOGS (immutable, INSERT-only)
-- ============================================================
CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    action          VARCHAR(50) NOT NULL,              -- e.g., 'transaction.create', 'budget.update'
    entity_type     VARCHAR(50) NOT NULL,              -- e.g., 'transaction', 'account'
    entity_id       UUID NOT NULL,

    -- What changed
    old_values      JSONB,                             -- Previous state (NULL for creates)
    new_values      JSONB,                             -- New state (NULL for deletes)

    -- Context
    ip_address      INET,
    user_agent      VARCHAR(512),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    -- No updated_at: audit logs are immutable
);

-- Primary query: user's audit trail by time
CREATE INDEX idx_audit_user_date ON audit_logs (user_id, created_at DESC);

-- Search by entity
CREATE INDEX idx_audit_entity ON audit_logs (entity_type, entity_id);

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- Users can only read their own audit logs, never modify
CREATE POLICY audit_logs_select ON audit_logs FOR SELECT TO app_user
    USING (user_id = current_app_user_id());

CREATE POLICY audit_logs_insert ON audit_logs FOR INSERT TO app_user
    WITH CHECK (user_id = current_app_user_id());

-- Prevent UPDATE and DELETE on audit logs
-- (No UPDATE or DELETE policies means those operations are denied by RLS)

-- Additional safety: revoke UPDATE/DELETE from app_user at the grant level
REVOKE UPDATE, DELETE ON audit_logs FROM app_user;
```

### 5.15 Schema Summary

| Table | RLS | Soft Delete | Audit | Key Indexes |
|-------|-----|------------|-------|-------------|
| `users` | No | No | N/A | email, phone, google_id |
| `refresh_tokens` | No | No | No | token_hash, user_id |
| `categories` | Yes (+ system) | No | No | user_id, parent_id |
| `accounts` | Yes | No | Yes | user_id |
| `transactions` | Yes | Yes | Yes | user+date+id composite, account, category, type, tags GIN |
| `recurring_transactions` | Yes | No | Yes | user_id, next_due_date |
| `budgets` | Yes | No | Yes | user+category+fy unique |
| `investment_holdings` | Yes | No | Yes | user_id, user+type, symbol |
| `investment_transactions` | Yes | Yes | Yes | user_id, holding+date |
| `bond_details` | Yes | No | No | holding_id |
| `screenshot_parse_logs` | Yes | No | No | user+created, status |
| `api_usage` | Yes (read-only) | No | No | user+date unique |
| `audit_logs` | Yes (insert+read) | N/A | N/A | user+date, entity |

---

## 6. API Endpoints

### 6.1 Response Envelope

All API responses follow a consistent envelope format.

**Success Response:**

```json
{
    "success": true,
    "data": { ... },
    "meta": {
        "request_id": "req_abc123",
        "timestamp": "2026-03-29T10:30:00Z"
    }
}
```

**Paginated Response (cursor-based):**

```json
{
    "success": true,
    "data": [ ... ],
    "pagination": {
        "has_more": true,
        "next_cursor": "eyJ0IjoiMjAyNi0wMy0yOFQxMDowMDowMFoiLCJpIjoiYWJjMTIzIn0=",
        "limit": 25
    },
    "meta": {
        "request_id": "req_abc123",
        "timestamp": "2026-03-29T10:30:00Z"
    }
}
```

**Error Response:**

```json
{
    "success": false,
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Invalid request parameters",
        "details": [
            {
                "field": "amount",
                "message": "Amount must be greater than 0"
            }
        ]
    },
    "meta": {
        "request_id": "req_abc123",
        "timestamp": "2026-03-29T10:30:00Z"
    }
}
```

**Error Codes:**

| HTTP Status | Error Code | Description |
|------------|------------|-------------|
| 400 | `VALIDATION_ERROR` | Request body/params failed validation |
| 400 | `BAD_REQUEST` | Generic bad request |
| 401 | `UNAUTHORIZED` | Missing or invalid access token |
| 401 | `TOKEN_EXPIRED` | Access token expired (frontend should refresh) |
| 403 | `FORBIDDEN` | Authenticated but not authorized |
| 404 | `NOT_FOUND` | Resource not found |
| 409 | `CONFLICT` | Duplicate resource (e.g., duplicate budget) |
| 429 | `RATE_LIMITED` | Too many requests |
| 500 | `INTERNAL_ERROR` | Unexpected server error |

### 6.2 Cursor-Based Pagination

Offset-based pagination (`?page=50&limit=25`) has O(n) performance because PostgreSQL must scan and discard the first `offset` rows. At thousands of transactions per user, this degrades noticeably.

Cursor-based pagination uses a composite cursor of `(transaction_date, id)` and a keyset `WHERE` clause, giving O(1) performance regardless of page depth.

**Cursor encoding:**

```python
import base64, json

def encode_cursor(transaction_date: str, id: str) -> str:
    """Encode (date, id) tuple as URL-safe base64 cursor."""
    payload = json.dumps({"t": transaction_date, "i": id})
    return base64.urlsafe_b64encode(payload.encode()).decode()

def decode_cursor(cursor: str) -> tuple[str, str]:
    """Decode cursor back to (date, id) tuple."""
    payload = json.loads(base64.urlsafe_b64decode(cursor))
    return payload["t"], payload["i"]
```

**SQL query pattern:**

```sql
-- First page (no cursor)
SELECT * FROM transactions
WHERE user_id = $1 AND is_deleted = false
ORDER BY transaction_date DESC, id DESC
LIMIT 26;  -- Fetch limit+1 to determine has_more

-- Subsequent pages (with cursor)
SELECT * FROM transactions
WHERE user_id = $1 AND is_deleted = false
  AND (transaction_date, id) < ($2, $3)  -- cursor values
ORDER BY transaction_date DESC, id DESC
LIMIT 26;
```

### 6.3 Complete Endpoint Map

#### Authentication

| Method | Path | Auth | Rate Limit | Description |
|--------|------|------|------------|-------------|
| `POST` | `/auth/register` | No | 5/hr/IP | Register with email + password |
| `POST` | `/auth/login` | No | 10/min/IP | Login with email + password |
| `GET` | `/auth/google` | No | - | Get Google OAuth authorization URL |
| `GET` | `/auth/google/callback` | No | - | Google OAuth callback (exchanges code for tokens) |
| `POST` | `/auth/otp/request` | No | 3/hr/phone | Request OTP to phone number |
| `POST` | `/auth/otp/verify` | No | 5/OTP | Verify OTP and get tokens |
| `POST` | `/auth/refresh` | Cookie | 30/min/user | Refresh access token using refresh token cookie |
| `POST` | `/auth/logout` | Yes | - | Revoke refresh token, clear cookie |

**`POST /auth/register`**

```
Request:
{
    "email": "user@example.com",
    "password": "SecurePass123!",
    "full_name": "Rahul Sharma"
}

Response (201):
{
    "success": true,
    "data": {
        "user": { "id": "...", "email": "user@example.com", "full_name": "Rahul Sharma" },
        "access_token": "eyJ..."
    }
}
+ Set-Cookie: refresh_token=...; HttpOnly; Secure; SameSite=Strict; Path=/auth; Max-Age=2592000
```

**`POST /auth/login`**

```
Request:
{
    "email": "user@example.com",
    "password": "SecurePass123!"
}

Response (200):
{
    "success": true,
    "data": {
        "user": { "id": "...", "email": "...", "full_name": "..." },
        "access_token": "eyJ..."
    }
}
+ Set-Cookie: refresh_token=...
```

#### User

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/users/me` | Yes | Get current user profile |
| `PATCH` | `/users/me` | Yes | Update profile (name, preferences) |
| `DELETE` | `/users/me` | Yes | Soft-delete account (requires password/OTP confirmation) |
| `POST` | `/users/me/export` | Yes | Request data export (async, returns job ID) |
| `GET` | `/users/me/export/{job_id}` | Yes | Check export status, get download URL |
| `GET` | `/users/me/usage` | Yes | Get API usage stats (current day, current month) |

#### Accounts

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/accounts` | Yes | List all accounts with balances |
| `POST` | `/accounts` | Yes | Create new account |
| `GET` | `/accounts/{id}` | Yes | Get account details |
| `PATCH` | `/accounts/{id}` | Yes | Update account |
| `DELETE` | `/accounts/{id}` | Yes | Deactivate account (fails if has transactions) |

**`POST /accounts`**

```
Request:
{
    "name": "HDFC Savings",
    "type": "savings",
    "bank_name": "HDFC Bank",
    "balance": 50000.00,
    "is_default": true
}

Response (201):
{
    "success": true,
    "data": {
        "id": "...",
        "name": "HDFC Savings",
        "type": "savings",
        "bank_name": "HDFC Bank",
        "balance": 50000.00,
        "is_default": true,
        "is_active": true,
        "created_at": "2026-03-29T10:00:00Z"
    }
}
```

#### Categories

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/categories` | Yes | List all categories (system + user, as tree) |
| `POST` | `/categories` | Yes | Create custom category |
| `PATCH` | `/categories/{id}` | Yes | Update custom category (cannot modify system) |
| `DELETE` | `/categories/{id}` | Yes | Delete custom category (cannot delete system) |

**`GET /categories`** returns a tree structure:

```json
{
    "success": true,
    "data": [
        {
            "id": "...",
            "name": "Food & Dining",
            "type": "expense",
            "icon": "utensils",
            "is_system": true,
            "children": [
                { "id": "...", "name": "Groceries", "icon": "shopping-cart", "is_system": true, "children": [] },
                { "id": "...", "name": "Swiggy / Zomato", "icon": "bike", "is_system": true, "children": [] }
            ]
        }
    ]
}
```

#### Transactions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/transactions` | Yes | List transactions (cursor paginated, filterable) |
| `POST` | `/transactions` | Yes | Create transaction |
| `GET` | `/transactions/{id}` | Yes | Get transaction details |
| `PATCH` | `/transactions/{id}` | Yes | Update transaction |
| `DELETE` | `/transactions/{id}` | Yes | Soft-delete transaction |

**`GET /transactions` Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `cursor` | string | null | Pagination cursor from previous response |
| `limit` | int | 25 | Items per page (max 100) |
| `type` | enum | null | `income`, `expense`, `transfer` |
| `account_id` | UUID | null | Filter by account |
| `category_id` | UUID | null | Filter by category |
| `date_from` | date | null | Start date (inclusive) |
| `date_to` | date | null | End date (inclusive) |
| `min_amount` | decimal | null | Minimum amount |
| `max_amount` | decimal | null | Maximum amount |
| `tags` | string | null | Comma-separated tags (AND logic) |
| `search` | string | null | Search in description (ILIKE) |

**`POST /transactions`**

```
Request:
{
    "account_id": "...",
    "category_id": "...",
    "type": "expense",
    "amount": 499.00,
    "description": "Swiggy order - dinner",
    "tags": ["food-delivery"],
    "transaction_date": "2026-03-28T19:30:00+05:30"
}

Response (201):
{
    "success": true,
    "data": {
        "id": "...",
        "account_id": "...",
        "category_id": "...",
        "type": "expense",
        "amount": 499.00,
        "description": "Swiggy order - dinner",
        "tags": ["food-delivery"],
        "transaction_date": "2026-03-28T19:30:00+05:30",
        "created_at": "2026-03-29T10:00:00Z"
    }
}
```

#### Recurring Transactions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/recurring` | Yes | List recurring transactions |
| `POST` | `/recurring` | Yes | Create recurring transaction |
| `GET` | `/recurring/{id}` | Yes | Get recurring transaction details |
| `PATCH` | `/recurring/{id}` | Yes | Update recurring transaction |
| `DELETE` | `/recurring/{id}` | Yes | Deactivate recurring transaction |

#### Budgets

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/budgets` | Yes | List budgets for current FY |
| `GET` | `/budgets?fy_year=2025` | Yes | List budgets for specific FY |
| `POST` | `/budgets` | Yes | Create budget |
| `PATCH` | `/budgets/{id}` | Yes | Update budget |
| `DELETE` | `/budgets/{id}` | Yes | Delete budget |

#### Investments

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/investments/holdings` | Yes | List all holdings with current values |
| `POST` | `/investments/holdings` | Yes | Add new holding |
| `GET` | `/investments/holdings/{id}` | Yes | Get holding with transaction history |
| `PATCH` | `/investments/holdings/{id}` | Yes | Update holding metadata |
| `DELETE` | `/investments/holdings/{id}` | Yes | Deactivate holding |
| `GET` | `/investments/transactions` | Yes | List investment transactions (cursor paginated) |
| `POST` | `/investments/transactions` | Yes | Record buy/sell/dividend/etc. |
| `PATCH` | `/investments/transactions/{id}` | Yes | Update investment transaction |
| `DELETE` | `/investments/transactions/{id}` | Yes | Soft-delete investment transaction |
| `GET` | `/investments/summary` | Yes | Portfolio summary (total value, gains, allocation) |

**`GET /investments/summary` Response:**

```json
{
    "success": true,
    "data": {
        "total_invested": 500000.00,
        "current_value": 575000.00,
        "total_gain": 75000.00,
        "total_gain_pct": 15.0,
        "day_change": 2500.00,
        "day_change_pct": 0.44,
        "allocation": [
            { "type": "equity", "value": 300000.00, "pct": 52.17 },
            { "type": "mutual_fund", "value": 150000.00, "pct": 26.09 },
            { "type": "fd", "value": 75000.00, "pct": 13.04 },
            { "type": "gold", "value": 50000.00, "pct": 8.70 }
        ],
        "xirr": 18.5
    }
}
```

#### Screenshots

| Method | Path | Auth | Rate Limit | Description |
|--------|------|------|------------|-------------|
| `POST` | `/screenshots/upload` | Yes | 50/day/user | Upload screenshot for parsing |
| `GET` | `/screenshots/{id}/status` | Yes | - | Poll parsing status |
| `GET` | `/screenshots/{id}/result` | Yes | - | Get parsed data |
| `POST` | `/screenshots/{id}/confirm` | Yes | - | Confirm parsed data, create transaction |

#### Dashboard

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/dashboard/summary` | Yes | Monthly income, expense, savings, balance |
| `GET` | `/dashboard/category-breakdown` | Yes | Spending by category (for pie chart) |
| `GET` | `/dashboard/trend` | Yes | Income/expense trend (last 12 months) |
| `GET` | `/dashboard/budget-status` | Yes | Budget utilization for current month |
| `GET` | `/dashboard/net-worth` | Yes | Net worth over time (accounts + investments) |

**`GET /dashboard/summary` Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `month` | int | current | Month (1-12) |
| `year` | int | current | Year |

**Response:**

```json
{
    "success": true,
    "data": {
        "period": { "month": 3, "year": 2026 },
        "total_income": 85000.00,
        "total_expense": 42500.00,
        "net_savings": 42500.00,
        "savings_rate": 50.0,
        "total_balance": 250000.00,
        "transaction_count": 87,
        "top_expense_category": {
            "name": "Food & Dining",
            "amount": 12500.00,
            "pct": 29.4
        },
        "vs_last_month": {
            "income_change": 5000.00,
            "expense_change": -2000.00
        }
    }
}
```

#### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | No | Basic health check (DB, Redis, S3 connectivity) |
| `GET` | `/health/ready` | No | Readiness probe (all dependencies healthy) |

---

## 7. Screenshot Parsing Pipeline

### 7.1 Pipeline Architecture

```
┌──────────┐     ┌──────────────┐     ┌─────────┐     ┌──────────────┐
│  User    │     │   FastAPI     │     │  Redis   │     │   Celery     │
│  Upload  │────>│  Validation   │────>│  Queue   │────>│   Worker     │
└──────────┘     └──────────────┘     └─────────┘     └──────┬───────┘
                        │                                      │
                        │ S3 Upload                           │ Claude Vision API
                        v                                      v
                 ┌──────────────┐                      ┌──────────────┐
                 │  S3 Bucket   │──────────────────────│  Claude API  │
                 │  (Mumbai)    │  (pre-signed URL)    │  (Sonnet)    │
                 └──────────────┘                      └──────┬───────┘
                                                              │
                        ┌──────────────────────────────────────┘
                        v
                 ┌──────────────┐     ┌──────────────┐     ┌──────────┐
                 │  Pydantic    │     │  Parse Log   │     │ Frontend │
                 │  Validation  │────>│  (PostgreSQL)│────>│ Pre-fill │
                 └──────────────┘     └──────────────┘     └────┬─────┘
                                                                │
                                                                │ User confirms
                                                                v
                                                         ┌──────────────┐
                                                         │ Transaction  │
                                                         │  Created     │
                                                         └──────────────┘
```

### 7.2 Step-by-Step Flow

**Step 1: Upload & Validation (FastAPI)**

```python
# screenshots/router.py

@router.post("/upload", status_code=201)
async def upload_screenshot(
    file: UploadFile,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Check daily rate limit (50/day/user)
    if not await check_rate_limit(f"screenshots:{user_id}", 50, 86400):
        raise RateLimitError("Daily screenshot limit reached (50/day)")

    # 2. Check daily API cost limit
    usage = await get_daily_usage(db, user_id)
    if usage and usage.total_cost_usd * 100 >= user.daily_api_cost_limit_paise:
        raise RateLimitError("Daily API cost limit reached")

    # 3. Read file bytes
    content = await file.read()

    # 4. Validate magic bytes (not just Content-Type header)
    detected_type = magic_from_bytes(content)
    if detected_type not in ("image/jpeg", "image/png", "image/webp"):
        raise ValidationError("Only JPEG, PNG, and WebP images are accepted")

    # 5. Validate file size (max 10MB)
    if len(content) > 10 * 1024 * 1024:
        raise ValidationError("File size must be under 10MB")

    # 6. Re-encode via Pillow (strips EXIF, normalizes format, prevents image bombs)
    image = Image.open(io.BytesIO(content))
    image.verify()  # Check for corruption
    image = Image.open(io.BytesIO(content))  # Re-open after verify

    if image.width * image.height > 25_000_000:  # 25 megapixels
        raise ValidationError("Image dimensions too large")

    # Re-encode as JPEG (reduces size, strips metadata)
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=85)
    clean_content = buffer.getvalue()

    # 7. Upload to S3
    s3_key = f"screenshots/{user_id}/{uuid4()}.jpg"
    await upload_to_s3(s3_key, clean_content, "image/jpeg")

    # 8. Create parse log record
    parse_log = ScreenshotParseLog(
        user_id=user_id,
        s3_key=s3_key,
        original_filename=file.filename,
        file_size_bytes=len(clean_content),
        mime_type="image/jpeg",
        status="uploaded",
        queued_at=datetime.utcnow(),
    )
    db.add(parse_log)
    await db.flush()

    # 9. Dispatch Celery task
    parse_screenshot.delay(str(parse_log.id))

    return {"success": True, "data": {"id": str(parse_log.id), "status": "uploaded"}}
```

**Step 2: Celery Task (Worker)**

```python
# tasks/screenshot_tasks.py

@celery_app.task(
    bind=True,
    queue="parsing",
    max_retries=2,
    default_retry_delay=30,
    rate_limit="10/m",  # Max 10 screenshots per minute across all workers
    soft_time_limit=60,
    time_limit=90,
)
def parse_screenshot(self, parse_log_id: str):
    """Download screenshot from S3, send to Claude Vision, store result."""

    with sync_db_session() as db:
        log = db.get(ScreenshotParseLog, parse_log_id)
        log.status = "processing"
        log.processing_started_at = datetime.utcnow()
        db.commit()

        try:
            # Download from S3
            image_bytes = download_from_s3(log.s3_key)
            image_b64 = base64.b64encode(image_bytes).decode()

            # Call Claude Vision API
            start_time = time.monotonic()
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64,
                            }
                        },
                        {
                            "type": "text",
                            "text": SCREENSHOT_PARSE_PROMPT,
                        }
                    ]
                }]
            )
            latency_ms = int((time.monotonic() - start_time) * 1000)

            # Parse Claude's response
            raw_text = response.content[0].text
            parsed = parse_claude_response(raw_text)  # Returns Pydantic model

            # Update log
            log.status = "parsed"
            log.claude_model = response.model
            log.claude_request_id = response.id
            log.input_tokens = response.usage.input_tokens
            log.output_tokens = response.usage.output_tokens
            log.cost_usd = calculate_cost(response.usage)
            log.api_latency_ms = latency_ms
            log.parsed_data = parsed.model_dump()
            log.parsed_at = datetime.utcnow()

            # Update daily usage
            update_daily_usage(db, log.user_id, response.usage, log.cost_usd)

            db.commit()

        except anthropic.APIError as e:
            log.status = "failed"
            log.error_message = str(e)
            log.error_code = "CLAUDE_API_ERROR"
            db.commit()
            raise self.retry(exc=e)

        except ValidationError as e:
            log.status = "failed"
            log.error_message = str(e)
            log.error_code = "PARSE_VALIDATION_ERROR"
            db.commit()
            # Don't retry validation errors
```

### 7.3 Claude Prompt Template

```python
SCREENSHOT_PARSE_PROMPT = """You are a financial transaction parser for an Indian personal finance app.

Analyze this screenshot of a payment confirmation, UPI transaction, bank SMS, or receipt.

Extract the following information and respond ONLY with a valid JSON object (no markdown, no explanation):

{
    "transaction_type": "expense" or "income",
    "amount": <number in INR, no commas>,
    "description": "<brief description of the transaction>",
    "merchant": "<merchant/payee name if visible>",
    "category_suggestion": "<best matching category from: Food & Dining, Transport, Shopping, Bills & Utilities, Housing, Health, Education, Entertainment, Personal Care, Travel, Gifts & Donations, EMI & Loans, Taxes, Insurance, Domestic Help, Miscellaneous, Salary, Freelance, Business Income, Interest Income, Dividend Income, Rental Income, Capital Gains, Cashback, Other Income>",
    "subcategory_suggestion": "<subcategory if identifiable, e.g., 'Swiggy / Zomato' for food delivery>",
    "transaction_date": "<ISO 8601 datetime if visible, e.g., 2026-03-28T19:30:00+05:30>",
    "payment_method": "<UPI, NEFT, IMPS, card, cash, or unknown>",
    "upi_id": "<UPI ID if visible, e.g., merchant@paytm>",
    "reference_number": "<transaction reference/UTR number if visible>",
    "from_account": "<source account/bank if visible>",
    "to_account": "<destination account/bank if visible>",
    "confidence": <0.0 to 1.0, your confidence in the extraction accuracy>
}

Rules:
- Amount must be a plain number (e.g., 499.00, not "Rs 499" or "4,99,000")
- Use Indian number formatting context (1,00,000 = 100000)
- If a field is not visible or not applicable, set it to null
- transaction_date should include timezone +05:30 (IST) if date is visible
- confidence should be lower if the image is blurry, partially visible, or ambiguous
- If this is clearly NOT a financial transaction screenshot, return: {"error": "not_a_transaction", "confidence": 0.0}
"""
```

### 7.4 Confirmation Flow

```python
# screenshots/router.py

@router.post("/{parse_log_id}/confirm")
async def confirm_screenshot(
    parse_log_id: UUID,
    body: ConfirmScreenshotRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    User reviews the parsed data, optionally modifies fields, and confirms.
    This creates the actual transaction.
    """
    log = await db.get(ScreenshotParseLog, parse_log_id)

    if log.status != "parsed":
        raise BadRequest("Screenshot is not in parsed state")

    # Create transaction from confirmed data
    # body contains user-corrected values (amount, category, date, etc.)
    transaction = Transaction(
        user_id=user_id,
        account_id=body.account_id,
        category_id=body.category_id,
        type=body.transaction_type,
        amount=body.amount,
        description=body.description,
        tags=body.tags or [],
        transaction_date=body.transaction_date,
        screenshot_parse_log_id=parse_log_id,
    )
    db.add(transaction)

    log.status = "confirmed"
    log.confirmed_at = datetime.utcnow()
    log.transaction_id = transaction.id

    await db.flush()

    return {"success": True, "data": TransactionResponse.model_validate(transaction)}
```

### 7.5 Cost Calculation

```python
def calculate_cost(usage) -> float:
    """
    Calculate Claude API cost in USD.
    Claude Sonnet pricing (as of 2026):
    - Input: $3.00 per million tokens
    - Output: $15.00 per million tokens
    """
    input_cost = (usage.input_tokens / 1_000_000) * 3.00
    output_cost = (usage.output_tokens / 1_000_000) * 15.00
    return round(input_cost + output_cost, 6)
```

**Typical screenshot parse cost:**
- Input: ~1,200 tokens (image) + ~300 tokens (prompt) = ~1,500 tokens = $0.0045
- Output: ~200 tokens (JSON response) = $0.003
- **Total per screenshot: ~$0.0075 (~Rs 0.63)**

---

## 8. Background Jobs (Celery)

### 8.1 Queue Architecture

```python
# tasks/celery_app.py

from celery import Celery

celery_app = Celery("expense_tracker")

celery_app.conf.update(
    broker_url="redis://redis:6379/0",
    result_backend="redis://redis:6379/1",

    # Queue routing
    task_routes={
        "app.tasks.screenshot_tasks.*": {"queue": "parsing"},
        "app.tasks.price_tasks.*": {"queue": "prices"},
        "app.tasks.export_tasks.*": {"queue": "default"},
        "app.tasks.recurring_tasks.*": {"queue": "default"},
        "app.tasks.cleanup_tasks.*": {"queue": "default"},
    },

    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="Asia/Kolkata",
    enable_utc=True,

    # Reliability
    task_acks_late=True,           # Ack after completion, not receipt
    worker_prefetch_multiplier=1,  # One task at a time per worker process
    task_reject_on_worker_lost=True,

    # Result expiry
    result_expires=3600,  # 1 hour

    # Rate limits (applied per worker)
    worker_concurrency=4,
)
```

### 8.2 Worker Deployment

```bash
# Start workers for each queue (in Docker Compose)

# Default queue: recurring, export, cleanup
celery -A app.tasks.celery_app worker -Q default -c 2 --loglevel=info

# Parsing queue: screenshot parsing (rate limited)
celery -A app.tasks.celery_app worker -Q parsing -c 2 --loglevel=info

# Prices queue: investment price fetching
celery -A app.tasks.celery_app worker -Q prices -c 1 --loglevel=info

# Beat scheduler (single instance)
celery -A app.tasks.celery_app beat --loglevel=info
```

### 8.3 Celery Beat Schedule

```python
celery_app.conf.beat_schedule = {
    # ──────────────────────────────────────────────────
    # RECURRING TRANSACTIONS
    # Generate due recurring transactions daily at 1:00 AM IST
    # ──────────────────────────────────────────────────
    "generate-recurring-transactions": {
        "task": "app.tasks.recurring_tasks.generate_recurring_transactions",
        "schedule": crontab(hour=1, minute=0),  # 1:00 AM IST
        "options": {"queue": "default"},
    },

    # ──────────────────────────────────────────────────
    # INVESTMENT PRICES
    # Fetch stock/MF/gold prices twice daily (market hours)
    # ──────────────────────────────────────────────────
    "fetch-prices-morning": {
        "task": "app.tasks.price_tasks.fetch_all_prices",
        "schedule": crontab(hour=9, minute=30),  # 9:30 AM IST (market open)
        "options": {"queue": "prices"},
    },
    "fetch-prices-afternoon": {
        "task": "app.tasks.price_tasks.fetch_all_prices",
        "schedule": crontab(hour=15, minute=45),  # 3:45 PM IST (after market close)
        "options": {"queue": "prices"},
    },

    # ──────────────────────────────────────────────────
    # CLEANUP
    # Expire old tokens, clean temp files at 3:00 AM IST
    # ──────────────────────────────────────────────────
    "cleanup-expired-tokens": {
        "task": "app.tasks.cleanup_tasks.cleanup_expired_tokens",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "default"},
    },
    "cleanup-old-screenshots": {
        "task": "app.tasks.cleanup_tasks.cleanup_old_screenshots",
        "schedule": crontab(hour=3, minute=30),  # Delete S3 objects for failed/rejected parses > 30 days
        "options": {"queue": "default"},
    },

    # ──────────────────────────────────────────────────
    # HARD DELETE
    # Permanently delete soft-deleted records older than 30 days
    # Weekly on Sunday at 4:00 AM IST
    # ──────────────────────────────────────────────────
    "hard-delete-old-records": {
        "task": "app.tasks.cleanup_tasks.hard_delete_old_records",
        "schedule": crontab(hour=4, minute=0, day_of_week="sun"),
        "options": {"queue": "default"},
    },

    # ──────────────────────────────────────────────────
    # API USAGE RESET
    # Reset daily counters (or just let new rows be created per-date)
    # Aggregate monthly usage on 1st of each month
    # ──────────────────────────────────────────────────
    "aggregate-monthly-usage": {
        "task": "app.tasks.cleanup_tasks.aggregate_monthly_usage",
        "schedule": crontab(hour=2, minute=0, day_of_month=1),
        "options": {"queue": "default"},
    },
}
```

### 8.4 Task Catalog

| Task | Queue | Rate Limit | Retries | Retry Delay | Timeout | Description |
|------|-------|------------|---------|-------------|---------|-------------|
| `parse_screenshot` | parsing | 10/min | 2 | 30s exponential | 60s soft / 90s hard | Parse screenshot via Claude Vision |
| `generate_recurring_transactions` | default | - | 3 | 60s | 300s | Create transactions for due recurring schedules |
| `fetch_all_prices` | prices | - | 3 | 120s | 600s | Fetch BSE/NSE stock prices, MF NAVs, gold prices |
| `generate_export` | default | - | 2 | 60s | 300s | Generate CSV/JSON export, upload to S3 |
| `cleanup_expired_tokens` | default | - | 1 | 60s | 120s | Delete expired refresh tokens |
| `cleanup_old_screenshots` | default | - | 1 | 60s | 300s | Delete S3 objects for old failed/rejected parses |
| `hard_delete_old_records` | default | - | 1 | 60s | 600s | Permanently delete soft-deleted transactions >30d |
| `aggregate_monthly_usage` | default | - | 1 | 60s | 120s | Summarize daily API usage into monthly totals |

### 8.5 Recurring Transaction Generation

```python
# tasks/recurring_tasks.py

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def generate_recurring_transactions(self):
    """
    Run daily at 1:00 AM IST.
    Finds all active recurring transactions where next_due_date <= today
    and creates the corresponding transaction records.
    """
    today = date.today()

    with sync_db_session_as_admin() as db:  # Admin session (no RLS)
        due_records = db.execute(
            select(RecurringTransaction)
            .where(RecurringTransaction.is_active == True)
            .where(RecurringTransaction.next_due_date <= today)
            .where(
                or_(
                    RecurringTransaction.end_date.is_(None),
                    RecurringTransaction.end_date >= today
                )
            )
        ).scalars().all()

        for rec in due_records:
            # Create the transaction (using RLS-bypassing admin session)
            txn = Transaction(
                user_id=rec.user_id,
                account_id=rec.account_id,
                category_id=rec.category_id,
                type=rec.type,
                amount=rec.amount,
                description=rec.description,
                tags=rec.tags,
                transaction_date=datetime.combine(rec.next_due_date, time.min, tzinfo=IST),
                recurring_transaction_id=rec.id,
            )
            db.add(txn)

            # Advance next_due_date
            rec.next_due_date = calculate_next_due(
                rec.next_due_date, rec.frequency, rec.schedule_day
            )
            rec.last_generated = datetime.utcnow()

            # Deactivate if past end_date
            if rec.end_date and rec.next_due_date > rec.end_date:
                rec.is_active = False

        db.commit()
        logger.info("recurring_generation_complete", count=len(due_records))
```

---

## 9. Caching (Redis)

### 9.1 Cache Strategy

The caching layer uses a **write-through delete** (cache-aside) strategy:

1. **Read:** Check Redis first. On miss, query PostgreSQL, cache the result.
2. **Write:** Write to PostgreSQL. Delete the relevant cache key(s). Next read will repopulate.

This avoids stale data issues from write-through caching while keeping reads fast.

### 9.2 Cache Keys and TTLs

| Key Pattern | TTL | Invalidated On | Description |
|-------------|-----|----------------|-------------|
| `dashboard:summary:{user_id}:{year}:{month}` | 5 min | Any transaction create/update/delete | Monthly income/expense/savings |
| `dashboard:category_breakdown:{user_id}:{year}:{month}` | 5 min | Any transaction create/update/delete | Spending by category |
| `dashboard:trend:{user_id}` | 10 min | Any transaction create/update/delete | 12-month trend data |
| `dashboard:budget_status:{user_id}:{fy_year}` | 5 min | Transaction or budget change | Budget utilization |
| `dashboard:net_worth:{user_id}` | 15 min | Account/investment/transaction change | Net worth timeline |
| `categories:{user_id}` | 1 hour | Category create/update/delete | User's category tree |
| `accounts:{user_id}` | 10 min | Account create/update/delete or transaction change | Account list with balances |
| `rate_limit:{scope}:{key}` | Varies | Auto-expire | Sliding window sorted set |
| `otp:{phone}` | 5 min | OTP verified or expired | Phone OTP + attempt counter |
| `token_blacklist:{jti}` | 15 min | Auto-expire | Blacklisted access tokens (on logout) |

### 9.3 Cache Implementation

```python
# core/redis.py

import json
from typing import Any, Callable
from redis.asyncio import Redis

redis_client: Redis = None  # Initialized in app lifespan

async def cache_get(key: str) -> Any | None:
    """Get a cached value, returning None on miss."""
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    return None

async def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    """Set a cached value with TTL."""
    await redis_client.setex(key, ttl_seconds, json.dumps(value, default=str))

async def cache_delete(*keys: str) -> None:
    """Delete one or more cache keys."""
    if keys:
        await redis_client.delete(*keys)

async def cache_delete_pattern(pattern: str) -> None:
    """Delete all keys matching a pattern. Use sparingly."""
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)
        if keys:
            await redis_client.delete(*keys)
        if cursor == 0:
            break

async def cached(
    key: str,
    ttl_seconds: int,
    fetch_fn: Callable,
) -> Any:
    """Cache-aside helper: return cached value or fetch and cache."""
    result = await cache_get(key)
    if result is not None:
        return result
    result = await fetch_fn()
    await cache_set(key, result, ttl_seconds)
    return result
```

### 9.4 Cache Invalidation in Services

```python
# transactions/service.py

async def create_transaction(db: AsyncSession, user_id: str, data: TransactionCreate):
    txn = Transaction(user_id=user_id, **data.model_dump())
    db.add(txn)
    await db.flush()

    # Invalidate affected caches
    month = txn.transaction_date.month
    year = txn.transaction_date.year
    await cache_delete(
        f"dashboard:summary:{user_id}:{year}:{month}",
        f"dashboard:category_breakdown:{user_id}:{year}:{month}",
        f"dashboard:trend:{user_id}",
        f"dashboard:budget_status:{user_id}:{get_fy_year(txn.transaction_date.date())}",
        f"dashboard:net_worth:{user_id}",
        f"accounts:{user_id}",
    )

    return txn
```

### 9.5 Redis Memory Estimation

| Data | Per User | 5,000 Users | Notes |
|------|----------|-------------|-------|
| Dashboard cache (5 keys) | ~5 KB | ~25 MB | JSON blobs, short TTL |
| Categories cache | ~2 KB | ~10 MB | Tree structure |
| Accounts cache | ~1 KB | ~5 MB | List with balances |
| Rate limit sets | ~0.5 KB | ~2.5 MB | Sliding window entries |
| OTP storage | ~0.1 KB | Negligible | Only active OTPs |
| **Total** | **~8.5 KB** | **~42.5 MB** | Well within 256 MB Redis |

---

## 10. Frontend Architecture

### 10.1 Project Setup

```typescript
// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
          query: ["@tanstack/react-query"],
        },
      },
    },
  },
});
```

### 10.2 Auth Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        AUTH FLOW                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  App loads                                                       │
│    ↓                                                             │
│  Check Zustand store (in-memory): has access token?              │
│    ↓ No                                                          │
│  POST /auth/refresh (cookie sent automatically)                  │
│    ↓ Success                    ↓ Failure (401)                  │
│  Store access token             Redirect to /login               │
│  in Zustand (memory)                                             │
│    ↓                                                             │
│  Render app                                                      │
│                                                                  │
│  API call returns 401 (token expired):                           │
│    → Axios interceptor catches                                   │
│    → Queues the failed request                                   │
│    → POST /auth/refresh                                          │
│    → On success: update Zustand, retry queued requests           │
│    → On failure: clear Zustand, redirect to /login               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Zustand Auth Store:**

```typescript
// stores/authStore.ts
import { create } from "zustand";

interface User {
  id: string;
  email: string | null;
  phone: string | null;
  full_name: string;
  avatar_url: string | null;
  preferences: Record<string, unknown>;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  setAuth: (user: User, token: string) => void;
  setToken: (token: string) => void;
  logout: () => void;
  setLoading: (loading: boolean) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: null,
  isAuthenticated: false,
  isLoading: true, // True until initial refresh attempt completes

  setAuth: (user, token) =>
    set({ user, accessToken: token, isAuthenticated: true, isLoading: false }),

  setToken: (token) => set({ accessToken: token }),

  logout: () =>
    set({
      user: null,
      accessToken: null,
      isAuthenticated: false,
      isLoading: false,
    }),

  setLoading: (loading) => set({ isLoading: loading }),
}));
```

**Axios Interceptor with Token Refresh:**

```typescript
// api/client.ts
import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/stores/authStore";

const apiClient = axios.create({
  baseURL: "/api",
  withCredentials: true, // Send cookies (refresh token)
});

// Request interceptor: attach access token
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: handle 401 with token refresh
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];

const processQueue = (error: unknown, token: string | null) => {
  failedQueue.forEach((promise) => {
    if (token) {
      promise.resolve(token);
    } else {
      promise.reject(error);
    }
  });
  failedQueue = [];
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        // Queue this request until refresh completes
        return new Promise((resolve, reject) => {
          failedQueue.push({
            resolve: (token: string) => {
              originalRequest.headers.Authorization = `Bearer ${token}`;
              resolve(apiClient(originalRequest));
            },
            reject,
          });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const { data } = await axios.post(
          "/api/auth/refresh",
          {},
          { withCredentials: true }
        );
        const newToken = data.data.access_token;
        useAuthStore.getState().setToken(newToken);
        processQueue(null, newToken);
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        useAuthStore.getState().logout();
        window.location.href = "/login";
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default apiClient;
```

### 10.3 Routing

```typescript
// router.tsx
import { createBrowserRouter } from "react-router-dom";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { AppLayout } from "@/components/layout/AppLayout";

export const router = createBrowserRouter([
  // Public routes
  {
    path: "/login",
    lazy: () => import("@/pages/LoginPage"),
  },
  {
    path: "/register",
    lazy: () => import("@/pages/RegisterPage"),
  },
  {
    path: "/auth/callback",
    lazy: () => import("@/pages/OAuthCallbackPage"),
  },

  // Protected routes
  {
    element: <AuthGuard />,
    children: [
      {
        element: <AppLayout />,
        children: [
          {
            path: "/",
            lazy: () => import("@/pages/DashboardPage"),
          },
          {
            path: "/dashboard",
            lazy: () => import("@/pages/DashboardPage"),
          },
          {
            path: "/transactions",
            lazy: () => import("@/pages/TransactionsPage"),
          },
          {
            path: "/transactions/new",
            lazy: () => import("@/pages/TransactionFormPage"),
          },
          {
            path: "/transactions/:id/edit",
            lazy: () => import("@/pages/TransactionFormPage"),
          },
          {
            path: "/accounts",
            lazy: () => import("@/pages/AccountsPage"),
          },
          {
            path: "/budgets",
            lazy: () => import("@/pages/BudgetsPage"),
          },
          {
            path: "/investments",
            lazy: () => import("@/pages/InvestmentsPage"),
          },
          {
            path: "/investments/holdings/:id",
            lazy: () => import("@/pages/HoldingDetailPage"),
          },
          {
            path: "/screenshots",
            lazy: () => import("@/pages/ScreenshotsPage"),
          },
          {
            path: "/settings",
            lazy: () => import("@/pages/SettingsPage"),
          },
        ],
      },
    ],
  },
]);
```

### 10.4 TanStack Query Hooks

```typescript
// hooks/useTransactions.ts
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/api/client";
import type { Transaction, TransactionCreate, CursorPage } from "@/types";

export function useTransactions(filters?: Record<string, unknown>) {
  return useInfiniteQuery<CursorPage<Transaction>>({
    queryKey: ["transactions", filters],
    queryFn: async ({ pageParam }) => {
      const params = { ...filters, cursor: pageParam, limit: 25 };
      const { data } = await apiClient.get("/transactions", { params });
      return data;
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) =>
      lastPage.pagination.has_more ? lastPage.pagination.next_cursor : undefined,
    staleTime: 30_000, // 30 seconds
  });
}

export function useCreateTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: TransactionCreate) => {
      const response = await apiClient.post("/transactions", data);
      return response.data;
    },
    onSuccess: () => {
      // Invalidate all transaction and dashboard queries
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}
```

### 10.5 INR Formatting

```typescript
// lib/format.ts

/**
 * Format a number as Indian Rupees.
 * Examples: 1000 → "1,000", 100000 → "1,00,000", 10000000 → "1,00,00,000"
 */
export function formatINR(amount: number, showSymbol = true): string {
  const formatter = new Intl.NumberFormat("en-IN", {
    style: showSymbol ? "currency" : "decimal",
    currency: "INR",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
  return formatter.format(amount);
}

/**
 * Format a date for display.
 * Default: "28 Mar 2026"
 */
export function formatDate(date: string | Date): string {
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(date));
}

/**
 * Get the Financial Year label for a date.
 * e.g., April 2026 → "FY 2026-27", January 2027 → "FY 2026-27"
 */
export function formatFY(date: Date): string {
  const month = date.getMonth() + 1; // 1-indexed
  const year = month >= 4 ? date.getFullYear() : date.getFullYear() - 1;
  return `FY ${year}-${String(year + 1).slice(-2)}`;
}
```

### 10.6 Page Descriptions

| Page | URL | Components | Data Queries |
|------|-----|------------|-------------|
| **Login** | `/login` | GoogleButton, PhoneOtpForm, EmailPasswordForm | - |
| **Register** | `/register` | RegisterForm | - |
| **Dashboard** | `/dashboard` | SummaryCards, CategoryPieChart, TrendLineChart, BudgetProgressBars, NetWorthChart | summary, category-breakdown, trend, budget-status, net-worth |
| **Transactions** | `/transactions` | TransactionFilters, TransactionList (infinite scroll), QuickAddFAB | useTransactions (infinite query) |
| **Transaction Form** | `/transactions/new` | TransactionForm (react-hook-form + zod), CategoryPicker, AccountSelect, DatePicker, TagInput | categories, accounts |
| **Accounts** | `/accounts` | AccountCards (grid), AccountForm (modal), BalanceSummary | accounts |
| **Budgets** | `/budgets` | FYSelector, BudgetCards, BudgetForm (modal), BudgetProgressBar | budgets, budget-status |
| **Investments** | `/investments` | PortfolioSummary, AllocationPieChart, HoldingCards (by type), InvestmentForm (modal) | holdings, summary |
| **Holding Detail** | `/investments/holdings/:id` | HoldingHeader, InvestmentTransactionList, GainLossChart, AddTransactionForm | holding detail, investment transactions |
| **Screenshots** | `/screenshots` | DropZone (drag-and-drop), UploadProgress, ParsePreview, ConfirmForm, RecentParseList | parse logs |
| **Settings** | `/settings` | ProfileForm, PreferencesForm, AccountDeletionSection, UsageStats, ExportSection | user profile, usage |

---

## 11. Deployment

### 11.1 Phase 1 Architecture (0--5,000 Users)

```
┌─────────────────────────────────────────────────────────┐
│                      Single VM                           │
│            (4 vCPU, 8 GB RAM, 100 GB SSD)               │
│                                                          │
│  ┌─────────────────────────────────────────────────┐     │
│  │                    Caddy                         │     │
│  │         (Reverse proxy + auto HTTPS)             │     │
│  │         :443 → FastAPI, static → SPA             │     │
│  └──────────────────┬──────────────────────────────┘     │
│                     │                                     │
│  ┌──────────────────▼──────────────────────────────┐     │
│  │             FastAPI (Gunicorn)                    │     │
│  │          4 Uvicorn workers, :8000                │     │
│  └──────┬────────────────────────────┬─────────────┘     │
│         │                            │                    │
│  ┌──────▼──────┐              ┌──────▼──────┐            │
│  │  PgBouncer  │              │    Redis    │            │
│  │   :6432     │              │   :6379     │            │
│  └──────┬──────┘              └──────┬──────┘            │
│         │                            │                    │
│  ┌──────▼──────┐              ┌──────▼──────┐            │
│  │ PostgreSQL  │              │   Celery    │            │
│  │  16, :5432  │              │  Workers    │            │
│  └─────────────┘              │  + Beat     │            │
│                               └─────────────┘            │
│                                                          │
│  External: S3 (ap-south-1)                               │
└─────────────────────────────────────────────────────────┘
```

### 11.2 Docker Compose (Development)

```yaml
# docker/docker-compose.yml

version: "3.9"

services:
  # ──────────────────────────────────────────
  # PostgreSQL
  # ──────────────────────────────────────────
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: expense_tracker
      POSTGRES_USER: expense_tracker
      POSTGRES_PASSWORD: ${DB_PASSWORD:-devpassword}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U expense_tracker"]
      interval: 5s
      timeout: 5s
      retries: 5

  # ──────────────────────────────────────────
  # Redis
  # ──────────────────────────────────────────
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  # ──────────────────────────────────────────
  # Backend (FastAPI)
  # ──────────────────────────────────────────
  backend:
    build:
      context: ../backend
      dockerfile: Dockerfile
    environment:
      - DATABASE_URL=postgresql+asyncpg://expense_tracker:${DB_PASSWORD:-devpassword}@postgres:5432/expense_tracker
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY:-dev-secret-key-change-in-production}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
      - S3_BUCKET=${S3_BUCKET:-expense-tracker-dev}
      - S3_REGION=ap-south-1
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
      - MSG91_AUTH_KEY=${MSG91_AUTH_KEY}
      - ENVIRONMENT=development
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: >
      uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - ../backend/app:/code/app  # Hot reload

  # ──────────────────────────────────────────
  # Celery Worker
  # ──────────────────────────────────────────
  celery-worker:
    build:
      context: ../backend
      dockerfile: Dockerfile
    environment:
      - DATABASE_URL=postgresql://expense_tracker:${DB_PASSWORD:-devpassword}@postgres:5432/expense_tracker
      - REDIS_URL=redis://redis:6379/0
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
      - S3_BUCKET=${S3_BUCKET:-expense-tracker-dev}
      - S3_REGION=ap-south-1
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: >
      celery -A app.tasks.celery_app worker
      -Q default,parsing,prices
      -c 4
      --loglevel=info

  # ──────────────────────────────────────────
  # Celery Beat (Scheduler)
  # ──────────────────────────────────────────
  celery-beat:
    build:
      context: ../backend
      dockerfile: Dockerfile
    environment:
      - DATABASE_URL=postgresql://expense_tracker:${DB_PASSWORD:-devpassword}@postgres:5432/expense_tracker
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
    command: >
      celery -A app.tasks.celery_app beat --loglevel=info

  # ──────────────────────────────────────────
  # Frontend (Vite dev server)
  # ──────────────────────────────────────────
  frontend:
    build:
      context: ../frontend
      dockerfile: Dockerfile
      target: development
    ports:
      - "5173:5173"
    volumes:
      - ../frontend/src:/app/src  # Hot reload
    environment:
      - VITE_API_URL=http://localhost:8000

volumes:
  postgres_data:
  redis_data:
```

### 11.3 Docker Compose (Production)

```yaml
# docker/docker-compose.prod.yml

version: "3.9"

services:
  # ──────────────────────────────────────────
  # Caddy (Reverse Proxy + HTTPS)
  # ──────────────────────────────────────────
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./caddy/Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
      - frontend_build:/srv/frontend  # Static SPA files
    depends_on:
      - backend
    restart: unless-stopped

  # ──────────────────────────────────────────
  # PostgreSQL
  # ──────────────────────────────────────────
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: expense_tracker
      POSTGRES_USER: expense_tracker
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    shm_size: "256mb"
    command: >
      postgres
        -c shared_buffers=2GB
        -c effective_cache_size=4GB
        -c work_mem=16MB
        -c maintenance_work_mem=512MB
        -c max_connections=200
        -c wal_buffers=64MB
        -c checkpoint_completion_target=0.9
        -c random_page_cost=1.1
        -c effective_io_concurrency=200
        -c log_min_duration_statement=500
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U expense_tracker"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # ──────────────────────────────────────────
  # PgBouncer (Connection Pooler)
  # ──────────────────────────────────────────
  pgbouncer:
    image: edoburu/pgbouncer:1.22.0
    volumes:
      - ./pgbouncer/pgbouncer.ini:/etc/pgbouncer/pgbouncer.ini
    environment:
      - DATABASE_URL=postgres://expense_tracker:${DB_PASSWORD}@postgres:5432/expense_tracker
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  # ──────────────────────────────────────────
  # Redis
  # ──────────────────────────────────────────
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
      - ./redis/redis.conf:/usr/local/etc/redis/redis.conf
    command: redis-server /usr/local/etc/redis/redis.conf
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # ──────────────────────────────────────────
  # Backend (FastAPI + Gunicorn)
  # ──────────────────────────────────────────
  backend:
    build:
      context: ../backend
      dockerfile: Dockerfile
      target: production
    environment:
      - DATABASE_URL=postgresql+asyncpg://expense_tracker:${DB_PASSWORD}@pgbouncer:6432/expense_tracker
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
      - S3_BUCKET=${S3_BUCKET}
      - S3_REGION=ap-south-1
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
      - GOOGLE_REDIRECT_URI=${GOOGLE_REDIRECT_URI}
      - MSG91_AUTH_KEY=${MSG91_AUTH_KEY}
      - MSG91_TEMPLATE_ID=${MSG91_TEMPLATE_ID}
      - SENTRY_DSN=${SENTRY_DSN}
      - ENVIRONMENT=production
      - CORS_ORIGINS=${CORS_ORIGINS}
    command: >
      gunicorn app.main:app
        --worker-class uvicorn.workers.UvicornWorker
        --workers 4
        --bind 0.0.0.0:8000
        --timeout 120
        --keep-alive 5
        --max-requests 1000
        --max-requests-jitter 100
        --access-logfile -
        --error-logfile -
    depends_on:
      pgbouncer:
        condition: service_started
      redis:
        condition: service_healthy
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "2"

  # ──────────────────────────────────────────
  # Celery Worker (Default + Parsing)
  # ──────────────────────────────────────────
  celery-worker:
    build:
      context: ../backend
      dockerfile: Dockerfile
      target: production
    environment:
      - DATABASE_URL=postgresql://expense_tracker:${DB_PASSWORD}@pgbouncer:6432/expense_tracker
      - REDIS_URL=redis://redis:6379/0
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
      - S3_BUCKET=${S3_BUCKET}
      - S3_REGION=ap-south-1
      - SENTRY_DSN=${SENTRY_DSN}
      - ENVIRONMENT=production
    command: >
      celery -A app.tasks.celery_app worker
        -Q default,parsing,prices
        -c 4
        --loglevel=info
        --without-heartbeat
        --without-mingle
        --without-gossip
    depends_on:
      pgbouncer:
        condition: service_started
      redis:
        condition: service_healthy
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: "1"

  # ──────────────────────────────────────────
  # Celery Beat (Scheduler -- single instance)
  # ──────────────────────────────────────────
  celery-beat:
    build:
      context: ../backend
      dockerfile: Dockerfile
      target: production
    environment:
      - DATABASE_URL=postgresql://expense_tracker:${DB_PASSWORD}@pgbouncer:6432/expense_tracker
      - REDIS_URL=redis://redis:6379/0
      - ENVIRONMENT=production
    command: >
      celery -A app.tasks.celery_app beat
        --loglevel=info
        --pidfile=/tmp/celerybeat.pid
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: "0.25"

volumes:
  postgres_data:
  redis_data:
  caddy_data:
  caddy_config:
  frontend_build:
```

### 11.4 Caddyfile

```
# docker/caddy/Caddyfile

{
    email admin@yourdomain.com
}

yourdomain.com {
    # API routes → FastAPI backend
    handle /api/* {
        uri strip_prefix /api
        reverse_proxy backend:8000 {
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
        }
    }

    # Auth routes (no /api prefix in backend)
    handle /auth/* {
        reverse_proxy backend:8000 {
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
        }
    }

    # Health check (direct, no /api prefix)
    handle /health* {
        reverse_proxy backend:8000
    }

    # Static SPA files
    handle {
        root * /srv/frontend
        try_files {path} /index.html
        file_server

        # Cache static assets aggressively
        @static path *.js *.css *.png *.jpg *.svg *.woff2
        header @static Cache-Control "public, max-age=31536000, immutable"
    }

    # Security headers
    header {
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        X-XSS-Protection "1; mode=block"
        Referrer-Policy strict-origin-when-cross-origin
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
        Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://*.amazonaws.com; connect-src 'self' https://accounts.google.com; font-src 'self';"
        -Server
    }

    # Compression
    encode gzip zstd

    # Request size limit (screenshots up to 10MB)
    request_body {
        max_size 12MB
    }
}
```

### 11.5 PgBouncer Configuration

```ini
; docker/pgbouncer/pgbouncer.ini

[databases]
expense_tracker = host=postgres port=5432 dbname=expense_tracker

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432

; Transaction mode: connection is returned to pool after each transaction.
; Essential for RLS SET LOCAL to work correctly (setting scoped to txn).
pool_mode = transaction

; Pool sizing
; 4 Gunicorn workers + 4 Celery workers = 8 processes.
; Each may hold 1-2 connections. Postgres max_connections = 200.
default_pool_size = 20
min_pool_size = 5
max_client_conn = 100
max_db_connections = 50

; Timeouts
server_idle_timeout = 600
client_idle_timeout = 0
query_timeout = 30
query_wait_timeout = 120

; Auth
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt

; Logging
log_connections = 0
log_disconnections = 0
log_pooler_errors = 1
stats_period = 60

; Admin
admin_users = expense_tracker
```

### 11.6 Redis Configuration

```conf
# docker/redis/redis.conf

# Memory
maxmemory 256mb
maxmemory-policy allkeys-lru

# Persistence (AOF for durability)
appendonly yes
appendfsync everysec

# Security
# bind 127.0.0.1  -- not needed in Docker (network isolation)
protected-mode no

# Performance
tcp-keepalive 60
timeout 0

# Logging
loglevel notice
```

### 11.7 Backend Dockerfile

```dockerfile
# backend/Dockerfile

# ============ Base Stage ============
FROM python:3.12-slim AS base

WORKDIR /code

# System dependencies for asyncpg, Pillow, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libjpeg62-turbo-dev \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt requirements/base.txt
RUN pip install --no-cache-dir -r requirements/base.txt

COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .

# ============ Development Stage ============
FROM base AS development

COPY requirements/dev.txt requirements/dev.txt
RUN pip install --no-cache-dir -r requirements/dev.txt

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ============ Production Stage ============
FROM base AS production

COPY requirements/prod.txt requirements/prod.txt
RUN pip install --no-cache-dir -r requirements/prod.txt

# Non-root user
RUN adduser --disabled-password --gecos "" appuser
USER appuser

CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000"]
```

### 11.8 Frontend Dockerfile

```dockerfile
# frontend/Dockerfile

# ============ Build Stage ============
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ============ Development Stage ============
FROM node:20-alpine AS development

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]

# ============ Production Stage ============
# Static files are served by Caddy, not nginx.
# This stage just outputs the build artifacts.
FROM alpine:3.19 AS production

COPY --from=build /app/dist /srv/frontend
```

### 11.9 Database Backup Script

```bash
#!/usr/bin/env bash
# scripts/backup_db.sh
#
# Daily PostgreSQL backup → gzip → S3.
# Run via cron: 0 2 * * * /path/to/backup_db.sh
#
# Required environment variables:
#   DB_HOST, DB_PORT, DB_NAME, DB_USER, PGPASSWORD
#   S3_BUCKET, S3_BACKUP_PREFIX

set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="/tmp/backup_${DB_NAME}_${TIMESTAMP}.sql.gz"

echo "[$(date)] Starting backup of ${DB_NAME}..."

# Dump and compress
pg_dump \
  -h "${DB_HOST:-localhost}" \
  -p "${DB_PORT:-5432}" \
  -U "${DB_USER:-expense_tracker}" \
  -d "${DB_NAME:-expense_tracker}" \
  --no-owner \
  --no-privileges \
  --format=plain \
  | gzip > "${BACKUP_FILE}"

FILESIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date)] Backup created: ${BACKUP_FILE} (${FILESIZE})"

# Upload to S3
S3_KEY="${S3_BACKUP_PREFIX:-backups}/${DB_NAME}/${TIMESTAMP}.sql.gz"
aws s3 cp "${BACKUP_FILE}" "s3://${S3_BUCKET}/${S3_KEY}" \
  --storage-class STANDARD_IA \
  --region ap-south-1

echo "[$(date)] Uploaded to s3://${S3_BUCKET}/${S3_KEY}"

# Cleanup local file
rm -f "${BACKUP_FILE}"

# Delete backups older than 30 days from S3
aws s3 ls "s3://${S3_BUCKET}/${S3_BACKUP_PREFIX:-backups}/${DB_NAME}/" \
  | while read -r line; do
    BACKUP_DATE=$(echo "$line" | awk '{print $1}')
    BACKUP_KEY=$(echo "$line" | awk '{print $4}')
    if [[ -n "$BACKUP_DATE" ]] && [[ $(date -d "$BACKUP_DATE" +%s) -lt $(date -d "30 days ago" +%s) ]]; then
      echo "[$(date)] Deleting old backup: ${BACKUP_KEY}"
      aws s3 rm "s3://${S3_BUCKET}/${S3_BACKUP_PREFIX:-backups}/${DB_NAME}/${BACKUP_KEY}"
    fi
  done

echo "[$(date)] Backup complete."
```

### 11.10 Environment Variables

```bash
# .env.example

# ============ Core ============
ENVIRONMENT=development                    # development | production
SECRET_KEY=change-me-to-64-char-random     # openssl rand -hex 32

# ============ Database ============
DB_PASSWORD=change-me
DATABASE_URL=postgresql+asyncpg://expense_tracker:${DB_PASSWORD}@localhost:5432/expense_tracker

# ============ Redis ============
REDIS_URL=redis://localhost:6379/0

# ============ Claude API ============
ANTHROPIC_API_KEY=sk-ant-...               # Anthropic API key

# ============ AWS S3 ============
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=expense-tracker-prod
S3_REGION=ap-south-1

# ============ Google OAuth ============
GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-...
GOOGLE_REDIRECT_URI=https://yourdomain.com/auth/google/callback

# ============ MSG91 (Phone OTP) ============
MSG91_AUTH_KEY=...
MSG91_TEMPLATE_ID=...                      # DLT-registered template ID
MSG91_SENDER_ID=EXPTRK                     # 6-char sender ID

# ============ Sentry ============
SENTRY_DSN=https://examplePublicKey@o0.ingest.sentry.io/0

# ============ CORS ============
CORS_ORIGINS=https://yourdomain.com

# ============ Backup ============
S3_BACKUP_PREFIX=backups
```

---

## 12. Monitoring

### 12.1 Structured Logging (structlog)

```python
# core/config.py (logging setup, called in main.py lifespan)

import structlog
import logging
import sys

def setup_logging(environment: str):
    """
    Configure structlog for structured JSON logging.
    Development: colored console output.
    Production: JSON lines for log aggregation.
    """
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if environment == "production":
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO if environment == "production" else logging.DEBUG,
    )
```

**Request logging middleware:**

```python
# core/middleware.py

import time
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = structlog.get_logger()

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.monotonic()

        # Bind request context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request.headers.get("x-request-id", ""),
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else "",
        )

        response = await call_next(request)

        duration_ms = round((time.monotonic() - start_time) * 1000, 2)

        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        response.headers["X-Request-ID"] = structlog.contextvars.get_contextvars().get("request_id", "")
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        return response
```

### 12.2 Sentry Integration

```python
# main.py

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.redis import RedisIntegration

def init_sentry(settings):
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,

            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                CeleryIntegration(monitor_beat_tasks=True),
                RedisIntegration(),
            ],

            # Performance monitoring
            traces_sample_rate=0.1 if settings.ENVIRONMENT == "production" else 1.0,
            profiles_sample_rate=0.1,

            # Filter sensitive data
            before_send=filter_sensitive_data,

            # Release tracking
            release=settings.APP_VERSION,

            # Ignore common non-errors
            ignore_errors=[KeyboardInterrupt],
        )

def filter_sensitive_data(event, hint):
    """Strip sensitive headers and body fields before sending to Sentry."""
    if "request" in event:
        headers = event["request"].get("headers", {})
        for sensitive in ["authorization", "cookie", "x-api-key"]:
            if sensitive in headers:
                headers[sensitive] = "[REDACTED]"
    return event
```

### 12.3 Prometheus Metrics

```python
# main.py

from prometheus_fastapi_instrumentator import Instrumentator, metrics

def setup_prometheus(app):
    """
    Expose /metrics endpoint for Prometheus scraping.
    Tracks: request latency, request count, in-progress requests, response sizes.
    """
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/health/ready", "/metrics"],
    )

    # Default metrics (latency, count, in-progress, response size)
    instrumentator.add(metrics.default())

    # Custom metrics
    instrumentator.add(
        metrics.latency(
            metric_name="http_request_duration_seconds",
            metric_doc="HTTP request duration in seconds",
        )
    )

    instrumentator.instrument(app).expose(app, endpoint="/metrics")
```

**Custom business metrics (tracked via Prometheus client):**

```python
# core/metrics.py

from prometheus_client import Counter, Histogram, Gauge

# Screenshot parsing
screenshots_uploaded_total = Counter(
    "screenshots_uploaded_total",
    "Total screenshots uploaded",
    ["status"]  # uploaded, parsed, confirmed, rejected, failed
)

screenshot_parse_duration_seconds = Histogram(
    "screenshot_parse_duration_seconds",
    "Time taken to parse a screenshot via Claude API",
    buckets=[1, 2, 5, 10, 30, 60]
)

claude_api_cost_usd_total = Counter(
    "claude_api_cost_usd_total",
    "Total Claude API cost in USD"
)

# Celery
celery_task_duration_seconds = Histogram(
    "celery_task_duration_seconds",
    "Celery task execution duration",
    ["task_name", "status"]
)

celery_queue_length = Gauge(
    "celery_queue_length",
    "Number of tasks in Celery queue",
    ["queue"]
)

# Business
active_users_daily = Gauge(
    "active_users_daily",
    "Number of users who made at least one request today"
)

transactions_created_total = Counter(
    "transactions_created_total",
    "Total transactions created",
    ["type", "source"]  # source: manual, screenshot, recurring
)
```

### 12.4 Health Check Endpoint

```python
# main.py

@app.get("/health")
async def health_check():
    """Basic liveness probe. Returns 200 if the process is running."""
    return {"status": "ok"}

@app.get("/health/ready")
async def readiness_check():
    """
    Readiness probe. Checks all dependencies.
    Returns 200 only if all are healthy.
    """
    checks = {}
    all_healthy = True

    # PostgreSQL
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        all_healthy = False

    # Redis
    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)}"
        all_healthy = False

    # S3 (lightweight check)
    try:
        await s3_client.head_bucket(Bucket=settings.S3_BUCKET)
        checks["s3"] = "ok"
    except Exception as e:
        checks["s3"] = f"error: {str(e)}"
        all_healthy = False

    status_code = 200 if all_healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "healthy" if all_healthy else "unhealthy", "checks": checks}
    )
```

### 12.5 Alerting Rules (Prometheus)

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| High Error Rate | 5xx rate > 5% for 5 min | Critical | Page on-call |
| High Latency | p95 > 2s for 5 min | Warning | Investigate slow queries |
| Database Connection Pool Exhausted | PgBouncer free connections = 0 | Critical | Scale pool or connections |
| Redis Memory High | Used memory > 80% of maxmemory | Warning | Review TTLs, eviction |
| Celery Queue Backlog | Queue length > 100 for 10 min | Warning | Scale workers |
| Claude API Cost Spike | Daily cost > $100 | Warning | Check for abuse |
| Screenshot Parse Failure Rate | > 20% failures in 1 hour | Warning | Check Claude API status |
| Disk Usage High | > 80% used | Warning | Cleanup / expand |
| SSL Certificate Expiry | < 7 days to expiry | Critical | Caddy should auto-renew; investigate if not |

---

## 13. Cost Projections

### 13.1 Assumptions

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Screenshots per user per month | 30--100 | Range: light (30 screenshots) to heavy (100 screenshots) |
| Cost per screenshot parse | $0.0075 | ~1,500 input tokens + ~200 output tokens on Claude Sonnet |
| S3 storage per user | 50 MB | ~100 screenshots at ~500 KB each |
| API requests per user per day | 50--100 | Dashboard loads, CRUD operations |

### 13.2 Cost Breakdown

| Component | 1,000 Users | 5,000 Users | 10,000 Users |
|-----------|-------------|-------------|--------------|
| **VM (Hetzner/DigitalOcean)** | | | |
| Compute (4 vCPU, 8 GB) | $40/mo | - | - |
| Compute (8 vCPU, 16 GB) | - | $80/mo | - |
| Compute (16 vCPU, 32 GB) | - | - | $160/mo |
| | | | |
| **Claude API** | | | |
| Low usage (30 screenshots/user/mo) | $225/mo | $1,125/mo | $2,250/mo |
| High usage (100 screenshots/user/mo) | $750/mo | $3,750/mo | $7,500/mo |
| **Estimated (50 avg)** | **$375/mo** | **$1,875/mo** | **$3,750/mo** |
| | | | |
| **AWS S3 (ap-south-1)** | | | |
| Storage (50 MB/user) | $0.25/mo | $1.25/mo | $2.50/mo |
| Requests (PUT + GET) | $5/mo | $25/mo | $50/mo |
| | | | |
| **Domain + DNS** | $15/yr | $15/yr | $15/yr |
| | | | |
| **Sentry** | $0 (free tier) | $26/mo | $26/mo |
| | | | |
| **MSG91 SMS** | | | |
| OTP SMS (~0.5 SMS/user/mo) | $3/mo | $15/mo | $30/mo |
| | | | |
| **Total (low Claude usage)** | **$270/mo** | **$1,175/mo** | **$2,520/mo** |
| **Total (medium Claude usage)** | **$440/mo** | **$2,025/mo** | **$4,020/mo** |
| **Total (high Claude usage)** | **$810/mo** | **$3,900/mo** | **$7,770/mo** |

### 13.3 Cost Optimization Levers

| Lever | Savings | Trade-off |
|-------|---------|-----------|
| **Claude Haiku instead of Sonnet** for simple screenshots | 60--75% on API costs | Lower accuracy on complex receipts |
| **Prompt caching** (reuse system prompt prefix) | 10--20% on input tokens | Minimal -- highly recommended |
| **Daily per-user screenshot limit** (50/day default) | Caps worst case | Power users may hit limit |
| **S3 Intelligent-Tiering** | ~30% on storage | Negligible |
| **Hetzner vs. DigitalOcean** | 30--50% on compute | European company (but has Singapore DC) |
| **Spot/preemptible for Celery workers** (at scale) | 60--70% on worker compute | Need graceful task handling |

---

## 14. Scaling Strategy

### 14.1 What Breaks First

| Scale Point | Bottleneck | Symptoms | Mitigation |
|-------------|-----------|----------|------------|
| **1,000 users** | Nothing (comfortable) | - | Single VM handles this easily. |
| **2,000--3,000 users** | **PostgreSQL connections** | PgBouncer pool exhaustion, connection wait timeouts. | Tune PgBouncer pool sizes. Ensure all queries are short-lived. Check for connection leaks. |
| **3,000--5,000 users** | **CPU on single VM** | Gunicorn workers saturated during peak hours (8--10 PM IST). High p95 latency. | Upgrade VM to 8 vCPU / 16 GB. Or split: separate VM for PostgreSQL. |
| **5,000--7,000 users** | **Celery queue depth** | Screenshot parsing queue backs up. Users wait >30s for results. | Add a second Celery worker VM. Separate parsing queue onto its own worker. |
| **7,000--10,000 users** | **PostgreSQL disk I/O** | Dashboard aggregation queries slow (>500ms). Write contention on transactions table. | Move to managed PostgreSQL (RDS / Supabase). Add read replica for dashboard queries. Materialized views for monthly aggregates. |
| **10,000--15,000 users** | **Redis memory** | Cache evictions increase. Rate limiting becomes unreliable. | Upgrade Redis to 1 GB. Consider separate Redis instances for cache vs. Celery broker. |
| **15,000--20,000 users** | **Single application server** | Even with 8 workers, peak request rate exceeds capacity. | Horizontal scaling: 2--3 backend VMs behind a load balancer. Sticky sessions not needed (stateless JWT). |
| **20,000+ users** | **Operational complexity** | Manual Docker Compose management becomes error-prone. Deploys cause downtime. | Migrate to Kubernetes (or managed container service). Blue-green deployments. Auto-scaling worker pods. |

### 14.2 Phase 2 Architecture (5,000--20,000 Users)

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                   │
│  ┌───────────┐     ┌───────────────┐     ┌──────────────────┐    │
│  │   Caddy    │     │  App Server 1 │     │  App Server 2    │    │
│  │   (LB)     │────>│  FastAPI (4w) │     │  FastAPI (4w)    │    │
│  └───────────┘     └───────┬───────┘     └────────┬─────────┘    │
│                            │                       │              │
│                     ┌──────▼───────────────────────▼──────┐       │
│                     │            PgBouncer                 │       │
│                     └──────────────┬──────────────────────┘       │
│                                    │                              │
│                     ┌──────────────▼──────────────────────┐       │
│                     │   Managed PostgreSQL (RDS/Supabase) │       │
│                     │   Primary + Read Replica             │       │
│                     └─────────────────────────────────────┘       │
│                                                                   │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐        │
│  │   Redis     │     │ Celery       │     │ Celery       │        │
│  │  (Managed)  │     │ Worker 1     │     │ Worker 2     │        │
│  └─────────────┘     │ (default)    │     │ (parsing)    │        │
│                      └─────────────┘     └─────────────┘         │
│                                                                   │
│  External: S3, CloudFront CDN (static assets)                    │
└──────────────────────────────────────────────────────────────────┘
```

### 14.3 Key Scaling Decisions

| Decision | Trigger | Action |
|----------|---------|--------|
| **Separate database server** | CPU consistently >70% on single VM | Move PostgreSQL to its own VM or managed service. |
| **Read replica** | Dashboard queries >500ms p95 | Route all `GET /dashboard/*` queries to read replica. |
| **CDN for static assets** | Frontend bundle >2 MB, global users | CloudFront in front of Caddy for `*.js`, `*.css`, images. |
| **Separate Redis instances** | Cache evictions while Celery broker is stable | One Redis for caching (volatile), one for Celery (persistent). |
| **Materialized views** | Monthly aggregation queries >1s | Pre-computed views for dashboard summary, refreshed every 5 min. |
| **Kubernetes** | >3 app server VMs, operational burden of Docker Compose | K8s with HPA for app servers and Celery workers. |
| **Object storage lifecycle** | S3 costs growing | Move screenshots older than 90 days to S3 Glacier Instant Retrieval. |

### 14.4 Database Scaling Specifics

**Materialized view for monthly summary (needed at ~7,000+ users):**

```sql
CREATE MATERIALIZED VIEW mv_monthly_summary AS
SELECT
    user_id,
    date_trunc('month', transaction_date) AS month,
    type,
    category_id,
    COUNT(*) AS txn_count,
    SUM(amount) AS total_amount
FROM transactions
WHERE is_deleted = false
GROUP BY user_id, date_trunc('month', transaction_date), type, category_id;

CREATE UNIQUE INDEX idx_mv_monthly_summary
    ON mv_monthly_summary (user_id, month, type, category_id);

-- Refresh every 5 minutes via Celery Beat
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_monthly_summary;
```

**Table partitioning (needed at ~20,000+ users):**

```sql
-- Partition transactions by month for faster queries and easier archival
CREATE TABLE transactions (
    id UUID NOT NULL DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    transaction_date TIMESTAMPTZ NOT NULL,
    -- ... other columns ...
) PARTITION BY RANGE (transaction_date);

-- Create partitions for each month
CREATE TABLE transactions_2026_04 PARTITION OF transactions
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE transactions_2026_05 PARTITION OF transactions
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
-- ... auto-created by a monthly Celery task ...
```

### 14.5 Claude API Scaling

| Users | Estimated Screenshots/Month | API Calls/Day | Strategy |
|-------|-----------------------------|---------------|----------|
| 1,000 | 50,000 | ~1,667 | Single queue, rate limit 10/min |
| 5,000 | 250,000 | ~8,333 | Separate parsing workers, consider Haiku for simple screenshots |
| 10,000 | 500,000 | ~16,667 | Tiered parsing (Haiku first, Sonnet for low-confidence), prompt caching |
| 20,000+ | 1,000,000+ | ~33,333 | Batch API, dedicated API tier from Anthropic |

**Tiered parsing strategy (at scale):**

1. First pass: Claude Haiku ($0.001/screenshot) -- fast, cheap, handles 70% of screenshots.
2. If confidence < 0.8: re-parse with Claude Sonnet ($0.0075/screenshot) -- better accuracy.
3. Effective blended cost: ~$0.003/screenshot (60% savings vs. Sonnet-only).

---

*End of Architecture Document*
