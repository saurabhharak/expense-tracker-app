# Epics, User Stories & Tasks

> Personal Finance Tracker — Multi-tenant webapp for thousands of Indian users
> Tech: FastAPI + React (Vite) + PostgreSQL (RLS) + Celery + Redis + Claude Vision

---

## Implementation Phases

| Phase | Weeks | Epics |
|-------|-------|-------|
| **Phase 1: Foundation** | 1-4 | Epic 1, Epic 2, Epic 3, Epic 4 (US-4.1 only) |
| **Phase 2: Core Value** | 5-8 | Epic 4 (US-4.2, 4.3), Epic 5, Epic 7, Epic 8 |
| **Phase 3: Investments & Polish** | 9-12 | Epic 6, Epic 9, Epic 10 |
| **Phase 4: Scale** | As needed | Partitioning, read replicas, managed services |

---

# EPIC 1: Project Foundation & Infrastructure

**Goal:** Scaffolded backend + frontend + Docker Compose + complete DB schema with RLS
**T-Shirt Size:** XL | **Priority:** P0 | **Phase:** 1

---

## US-1.1: Backend Project Scaffolding

**As a** developer, **I want** the backend scaffolded with FastAPI **so that** I can start building features.

**Acceptance Criteria:**
- [ ] FastAPI app with factory pattern (`create_app()`)
- [ ] SQLAlchemy async engine + sync engine (dual session factory)
- [ ] Alembic migrations configured for async PostgreSQL
- [ ] `pyproject.toml` with all dependencies pinned
- [ ] Dockerfile (multi-stage, non-root user, read-only FS)
- [ ] Health check endpoint (`GET /health`) checking DB, Redis, S3
- [ ] Core middleware: request ID, timing, error handling, security headers

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-1.1.1 | Initialize Python project with pyproject.toml | `backend/pyproject.toml` | 1h |
| T-1.1.2 | Create FastAPI app factory with lifespan | `backend/app/main.py` | 2h |
| T-1.1.3 | Set up dual DB session factory (async for FastAPI, sync for Celery) with RLS context setter | `backend/app/core/database.py` | 3h |
| T-1.1.4 | Configure Alembic for async PostgreSQL | `backend/alembic/`, `backend/alembic.ini` | 2h |
| T-1.1.5 | Create core middleware (request ID, timing, security headers, error handler) | `backend/app/core/middleware.py` | 3h |
| T-1.1.6 | Create Pydantic settings with all env vars | `backend/app/core/config.py` | 1h |
| T-1.1.7 | Create Dockerfile (multi-stage, python:3.12-slim, non-root, read-only FS) | `backend/Dockerfile` | 1h |
| T-1.1.8 | Write health check endpoint (DB + Redis + S3) | `backend/app/main.py` | 1h |
| T-1.1.9 | Set up Redis client singleton | `backend/app/core/redis.py` | 1h |
| T-1.1.10 | Set up S3 client abstraction | `backend/app/core/storage.py` | 1h |

**Dependencies:** None
**Key Libraries:** `fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `asyncpg`, `psycopg2-binary`, `alembic`, `pydantic-settings`, `structlog`, `sentry-sdk`, `redis`, `boto3`

---

## US-1.2: Frontend Project Scaffolding

**As a** developer, **I want** the frontend scaffolded with Vite + React **so that** I can build the UI.

**Acceptance Criteria:**
- [ ] Vite + React + TypeScript project initialized
- [ ] Tailwind CSS configured with custom INR-friendly theme
- [ ] API client with auth interceptor (auto-refresh on 401)
- [ ] React Router with route guards (redirect to /login if unauthenticated)
- [ ] Basic layout components (Shell, Sidebar, Header)
- [ ] Dockerfile (multi-stage: build → serve via Caddy)

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-1.2.1 | Initialize Vite + React + TypeScript project | `frontend/` | 1h |
| T-1.2.2 | Install all dependencies | `frontend/package.json` | 0.5h |
| T-1.2.3 | Configure Tailwind CSS with custom theme | `frontend/tailwind.config.js`, `frontend/src/styles/globals.css` | 1h |
| T-1.2.4 | Create API client with auth interceptor + auto-refresh + X-Requested-With header | `frontend/src/api/client.ts` | 2h |
| T-1.2.5 | Set up React Router with auth guards | `frontend/src/router.tsx` | 1h |
| T-1.2.6 | Create layout components (Shell, Sidebar, Header) | `frontend/src/components/layout/` | 3h |
| T-1.2.7 | Create INR currency formatter utility | `frontend/src/lib/currency.ts` | 0.5h |
| T-1.2.8 | Create FY helper utility (April-March) | `frontend/src/lib/fiscalYear.ts` | 0.5h |
| T-1.2.9 | Create Dockerfile (multi-stage build) | `frontend/Dockerfile` | 1h |

**Dependencies:** None
**Key Libraries:** `react`, `react-router-dom@7`, `@tanstack/react-query@5`, `zustand@5`, `axios`, `recharts`, `date-fns`, `react-hook-form@7`, `zod`, `react-dropzone`, `tailwindcss@4`, `clsx`, `tailwind-merge`

---

## US-1.3: Docker Compose & Infrastructure

**As a** developer, **I want** Docker Compose for local development **so that** all services run with one command.

**Acceptance Criteria:**
- [ ] `docker compose up` starts all services
- [ ] PostgreSQL + PgBouncer + Redis + Backend + Celery + MinIO + Frontend
- [ ] Production compose overrides with Caddy
- [ ] `.env.example` with all environment variables documented

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-1.3.1 | Create dev docker-compose.yml (postgres, pgbouncer, redis, backend, celery-worker, celery-beat, flower, minio, frontend) | `docker/docker-compose.yml` | 3h |
| T-1.3.2 | Create prod docker-compose.prod.yml (gunicorn, caddy, no dev volumes) | `docker/docker-compose.prod.yml` | 2h |
| T-1.3.3 | Create Caddyfile (static files, API reverse proxy, SPA fallback, security headers) | `docker/caddy/Caddyfile` | 1h |
| T-1.3.4 | Create PgBouncer config (transaction mode) | `docker/pgbouncer/pgbouncer.ini` | 0.5h |
| T-1.3.5 | Create Redis config (AOF persistence, memory limit) | `docker/redis/redis.conf` | 0.5h |
| T-1.3.6 | Create `.env.example` with all env vars (DB, Redis, JWT keys, Google OAuth, MSG91, S3, Anthropic, Sentry) | `.env.example` | 1h |
| T-1.3.7 | Create seed script for default Indian categories | `scripts/seed_categories.py` | 1h |

**Dependencies:** US-1.1, US-1.2

---

## US-1.4: Complete Database Schema with RLS

**As a** developer, **I want** the full database schema with Row-Level Security **so that** all user data is tenant-isolated from day one.

**Acceptance Criteria:**
- [ ] All 13 tables created via Alembic migrations
- [ ] RLS enabled AND forced on all data tables (11 tables)
- [ ] DECIMAL(12,2) for all money fields
- [ ] UUID primary keys for all public-facing entities
- [ ] Composite indexes on all query patterns
- [ ] GIN index on tags array
- [ ] FY helper functions (get_fy_year, get_fy_range)
- [ ] Incremental balance trigger on transactions
- [ ] Integration test: RLS isolation (2 users, verify cross-tenant blocked)

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-1.4.1 | Migration: users + refresh_tokens tables | `backend/alembic/versions/001_users.py` | 2h |
| T-1.4.2 | Migration: categories table (hierarchical, system defaults) + RLS | `backend/alembic/versions/002_categories.py` | 2h |
| T-1.4.3 | Migration: accounts table + RLS | `backend/alembic/versions/003_accounts.py` | 1h |
| T-1.4.4 | Migration: transactions table (all indexes, GIN, trigger) + RLS | `backend/alembic/versions/004_transactions.py` | 3h |
| T-1.4.5 | Migration: recurring_transactions + RLS | `backend/alembic/versions/005_recurring.py` | 1h |
| T-1.4.6 | Migration: budgets (FY-aware) + RLS | `backend/alembic/versions/006_budgets.py` | 1h |
| T-1.4.7 | Migration: investment_holdings + investment_transactions + bond_details + RLS | `backend/alembic/versions/007_investments.py` | 2h |
| T-1.4.8 | Migration: screenshot_parse_logs + api_usage + RLS | `backend/alembic/versions/008_screenshots.py` | 1h |
| T-1.4.9 | Migration: audit_logs (BIGSERIAL, INSERT-only) | `backend/alembic/versions/009_audit.py` | 1h |
| T-1.4.10 | Migration: FY helper functions + balance trigger + updated_at trigger | `backend/alembic/versions/010_functions.py` | 2h |
| T-1.4.11 | Migration: seed default Indian categories (income + expense) | `backend/alembic/versions/011_seed_categories.py` | 1h |
| T-1.4.12 | Write RLS isolation integration test (critical) | `backend/tests/integration/test_rls_isolation.py` | 3h |

**Dependencies:** US-1.1 (Alembic must be configured)

---

# EPIC 2: Authentication & User Management

**Goal:** Secure multi-method auth with Google OAuth, Phone OTP, and JWT tokens
**T-Shirt Size:** L | **Priority:** P0 | **Phase:** 1

---

## US-2.1: Google OAuth2 Login

**As a** user, **I want** to sign in with Google **so that** I can access the app without creating a password.

**Acceptance Criteria:**
- [ ] Google sign-in button on login page
- [ ] Backend exchanges auth code for user info via Google API
- [ ] Auto-creates account on first login
- [ ] Returns JWT access token (RS256, 15-min) + sets refresh token cookie (httpOnly, Secure, SameSite=Strict)
- [ ] Refresh token rotation on every use

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-2.1.1 | Create auth module structure | `backend/app/auth/` (router, service, models, schemas, dependencies) | 1h |
| T-2.1.2 | Implement User + RefreshToken SQLAlchemy models | `backend/app/auth/models.py` | 1h |
| T-2.1.3 | Implement Google OAuth2 code exchange | `backend/app/auth/oauth.py` | 2h |
| T-2.1.4 | POST /api/v1/auth/google endpoint | `backend/app/auth/router.py` | 1h |
| T-2.1.5 | JWT token generation (RS256 with asymmetric keys) | `backend/app/core/security.py` | 2h |
| T-2.1.6 | Refresh token creation (opaque, SHA-256 hashed in DB, 30-day, httpOnly cookie) | `backend/app/auth/service.py` | 2h |
| T-2.1.7 | `get_current_user` dependency (decode JWT, set RLS context) | `backend/app/auth/dependencies.py` | 2h |
| T-2.1.8 | POST /api/v1/auth/refresh (rotate refresh token) | `backend/app/auth/router.py` | 1h |
| T-2.1.9 | POST /api/v1/auth/logout (revoke refresh token) | `backend/app/auth/router.py` | 0.5h |
| T-2.1.10 | Frontend: Google sign-in button (auth code flow with PKCE) | `frontend/src/components/auth/GoogleButton.tsx` | 2h |
| T-2.1.11 | Frontend: Auth store (Zustand) + API interceptor for auto-refresh | `frontend/src/stores/authStore.ts`, `frontend/src/api/client.ts` | 2h |
| T-2.1.12 | Write auth flow integration tests (register, login, refresh, logout) | `backend/tests/integration/test_auth_flow.py` | 3h |

**Dependencies:** Epic 1 complete

---

## US-2.2: Phone OTP Login

**As a** user, **I want** to sign in with my phone number via OTP **so that** I can use the app without a Google account.

**Acceptance Criteria:**
- [ ] Phone number input with OTP verification flow
- [ ] OTP sent via MSG91 SMS API
- [ ] 6-digit OTP, 5-minute expiry, single-use
- [ ] Rate limited: 3 OTPs per phone per 10 minutes, 5 verify attempts per 15 min
- [ ] Auto-creates account on first OTP verification

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-2.2.1 | Integrate MSG91 SMS API client | `backend/app/auth/otp.py` | 2h |
| T-2.2.2 | POST /api/v1/auth/otp/request — send OTP, store hash in Redis (5-min TTL) | `backend/app/auth/router.py` | 2h |
| T-2.2.3 | POST /api/v1/auth/otp/verify — verify OTP, return tokens | `backend/app/auth/router.py` | 2h |
| T-2.2.4 | Rate limiting: 3/10min send, 5/15min verify (Redis sliding window) | `backend/app/core/rate_limit.py` | 2h |
| T-2.2.5 | Frontend: Phone input + OTP entry flow | `frontend/src/components/auth/OTPLogin.tsx` | 3h |
| T-2.2.6 | Write OTP flow tests (success, expired, max attempts, rate limit) | `backend/tests/integration/test_otp_flow.py` | 2h |

**Dependencies:** US-2.1 (shared auth infrastructure)

---

## US-2.3: User Profile Management

**As a** user, **I want** to manage my profile and preferences **so that** the app works the way I want.

**Acceptance Criteria:**
- [ ] View and edit display name, preferences (timezone, currency, FY start month)
- [ ] Request full data export (async, ZIP download)
- [ ] Delete account (30-day cooling-off, then hard delete)

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-2.3.1 | GET /api/v1/me — return user profile | `backend/app/auth/router.py` | 0.5h |
| T-2.3.2 | PATCH /api/v1/me — update profile and preferences | `backend/app/auth/router.py` | 1h |
| T-2.3.3 | DELETE /api/v1/me — soft delete (is_active=false), schedule hard delete | `backend/app/auth/router.py` | 1h |
| T-2.3.4 | GET /api/v1/me/export — enqueue Celery task to generate data ZIP | `backend/app/export/` | 2h |
| T-2.3.5 | GET /api/v1/me/usage — return API usage stats | `backend/app/auth/router.py` | 1h |
| T-2.3.6 | Frontend: Settings page (profile form, export, delete account) | `frontend/src/pages/Settings.tsx` | 3h |

**Dependencies:** US-2.1

---

# EPIC 3: Accounts & Categories

**Goal:** Bank accounts and hierarchical expense categories
**T-Shirt Size:** M | **Priority:** P0 | **Phase:** 1

---

## US-3.1: Bank Account Management

**As a** user, **I want** to add my bank accounts **so that** I can track where money comes from and goes.

**Acceptance Criteria:**
- [ ] CRUD for accounts (savings, current, credit_card, wallet, cash, loan)
- [ ] Balance tracked per account (updated by transaction trigger)
- [ ] Default accounts seeded (Cash, Primary Bank)

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-3.1.1 | Create accounts module (router, service, models, schemas) | `backend/app/accounts/` | 2h |
| T-3.1.2 | CRUD endpoints: GET/POST/PATCH/DELETE /api/v1/accounts | `backend/app/accounts/router.py` | 2h |
| T-3.1.3 | Frontend: Account management page (list, add, edit) | `frontend/src/pages/Accounts.tsx` | 3h |
| T-3.1.4 | Write account CRUD tests | `backend/tests/unit/test_accounts.py` | 1h |

**Dependencies:** US-1.4 (schema), US-2.1 (auth)

---

## US-3.2: Expense & Income Categories

**As a** user, **I want** categories organized hierarchically **so that** I can categorize my transactions.

**Acceptance Criteria:**
- [ ] System default categories visible to all (user_id IS NULL in RLS policy)
- [ ] Users can create custom subcategories under system categories
- [ ] Tree structure: parent_id self-referencing
- [ ] Icons and colors per category
- [ ] Separate income and expense category trees

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-3.2.1 | Create categories module (router, service, models, schemas) | `backend/app/categories/` | 2h |
| T-3.2.2 | GET /api/v1/categories — return tree structure | `backend/app/categories/router.py` | 1h |
| T-3.2.3 | POST/PATCH/DELETE /api/v1/categories — user custom categories | `backend/app/categories/router.py` | 1h |
| T-3.2.4 | Frontend: Category management with tree view | `frontend/src/pages/Categories.tsx` | 3h |
| T-3.2.5 | Write category tests (system vs user, hierarchy) | `backend/tests/unit/test_categories.py` | 1h |

**Default Indian Categories (seeded in T-1.4.11):**

**Expense:** Food (Restaurants, Groceries, Swiggy/Zomato), Transport (Fuel, Ola/Uber, Public), Bills (Electricity, Mobile, Internet, Gas, Water), Shopping (Clothes, Electronics, Home), Health (Doctor, Medicine, Gym), Education, Entertainment, Rent, Insurance, Personal Care, Gifts/Donations, EMI, Other

**Income:** Salary, Freelance, Interest, Dividend, Rental Income, Refund, Gift, Other

---

# EPIC 4: Transaction Management

**Goal:** Full CRUD for income/expense transactions with recurring support
**T-Shirt Size:** XL | **Priority:** P0 | **Phase:** 1-2

---

## US-4.1: Manual Transaction Entry (Phase 1)

**As a** user, **I want** to add income and expense transactions **so that** I can track my money.

**Acceptance Criteria:**
- [ ] Form: amount (INR, DECIMAL), type (income/expense), date, account, category, payee, notes, payment method (UPI/cash/card/NEFT/IMPS/etc.), tags
- [ ] Cursor-based pagination on transaction list
- [ ] Filters: date range, category, account, type, payment method, amount range, search text
- [ ] Account balance auto-updated via trigger
- [ ] All amounts stored as DECIMAL(12,2)

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-4.1.1 | Create transactions module (router, service, models, schemas) | `backend/app/transactions/` | 2h |
| T-4.1.2 | POST /api/v1/transactions — create with Pydantic validation | `backend/app/transactions/router.py` | 2h |
| T-4.1.3 | GET /api/v1/transactions — cursor pagination + all filters | `backend/app/transactions/router.py`, `backend/app/core/pagination.py` | 4h |
| T-4.1.4 | GET/PATCH/DELETE /api/v1/transactions/{id} | `backend/app/transactions/router.py` | 2h |
| T-4.1.5 | Implement cursor-based pagination helper | `backend/app/core/pagination.py` | 2h |
| T-4.1.6 | Frontend: Transaction list (infinite scroll, filters, search) | `frontend/src/pages/Transactions.tsx` | 5h |
| T-4.1.7 | Frontend: Transaction add/edit form (category picker, date picker, INR amount) | `frontend/src/components/transactions/TransactionForm.tsx` | 4h |
| T-4.1.8 | Write transaction service unit tests | `backend/tests/unit/test_transactions.py` | 2h |
| T-4.1.9 | Write transaction API integration tests (CRUD + pagination) | `backend/tests/integration/test_transactions_api.py` | 3h |

**Dependencies:** Epic 1 (all), Epic 2 (auth), Epic 3 (accounts + categories)

---

## US-4.2: Recurring Transactions (Phase 2)

**As a** user, **I want** recurring transactions (salary, rent, SIPs) **so that** they're auto-created monthly.

**Acceptance Criteria:**
- [ ] Define recurring: frequency (daily/weekly/monthly/quarterly/yearly), start/end date, template
- [ ] Celery Beat executes daily at 1 AM IST
- [ ] Auto-creates transactions on due date
- [ ] Can pause/resume (is_active flag)

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-4.2.1 | Create recurring module | `backend/app/transactions/` (extend existing) | 1h |
| T-4.2.2 | CRUD endpoints for recurring transactions | `backend/app/transactions/router.py` | 2h |
| T-4.2.3 | Celery task: generate_due_transactions (daily 1 AM IST) | `backend/app/tasks/recurring_tasks.py` | 3h |
| T-4.2.4 | Frontend: Recurring transaction management page | `frontend/src/pages/Recurring.tsx` | 3h |
| T-4.2.5 | Write recurring execution tests (due date logic, next_due_date calculation) | `backend/tests/unit/test_recurring.py` | 2h |

**Dependencies:** US-4.1, Celery setup (US-1.3)

---

## US-4.3: Account Transfers (Phase 2)

**As a** user, **I want** to record transfers between accounts **so that** my account balances stay accurate.

**Acceptance Criteria:**
- [ ] Transfer creates paired debit/credit entries
- [ ] Both source and destination balances updated atomically
- [ ] Shown as "transfer" type in transaction list

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-4.3.1 | POST /api/v1/transactions with type="transfer" + transfer_to_account_id | `backend/app/transactions/service.py` | 2h |
| T-4.3.2 | Frontend: Transfer form with source/destination pickers | `frontend/src/components/transactions/TransferForm.tsx` | 2h |
| T-4.3.3 | Write transfer tests (balance atomicity, trigger correctness) | `backend/tests/unit/test_transfers.py` | 1h |

**Dependencies:** US-4.1

---

# EPIC 5: Screenshot Auto-Parsing

**Goal:** Upload payment screenshots, Claude Vision extracts transaction data, user confirms
**T-Shirt Size:** XL | **Priority:** P0 | **Phase:** 2

---

## US-5.1: Screenshot Upload & Parsing

**As a** user, **I want** to upload a PhonePe/GPay screenshot and have the app auto-fill transaction details **so that** I don't have to type everything manually.

**Acceptance Criteria:**
- [ ] Upload PNG/JPEG (max 10MB)
- [ ] File validated: magic bytes, Pillow re-encode (strip EXIF), UUID filename
- [ ] Uploaded to S3, Celery task parses via Claude Sonnet Vision (tool-use mode)
- [ ] Extracts: amount, payee, date, note, payment method, UPI reference, transaction status
- [ ] Show pre-filled form for user review and confirmation
- [ ] Full audit trail in screenshot_parse_logs
- [ ] Duplicate detection: perceptual hash + UTR matching
- [ ] Rate limited: 10/hour + 50/day per user
- [ ] Cost tracked in api_usage table

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-5.1.1 | Create screenshots module (router, service, parser, models, schemas) | `backend/app/screenshots/` | 2h |
| T-5.1.2 | POST /api/v1/screenshots/upload — validate (magic bytes, size, Pillow re-encode, strip EXIF), UUID filename, upload to S3, create parse log, enqueue task | `backend/app/screenshots/router.py`, `backend/app/screenshots/service.py` | 4h |
| T-5.1.3 | Vision provider abstraction: base class, Anthropic, OpenAI, Gemini providers, factory | `backend/app/screenshots/providers/` (base.py, anthropic_provider.py, openai_provider.py, google_provider.py, factory.py) | 5h |
| T-5.1.4 | Celery task: parse_screenshot — download S3, call provider (via factory), validate with Pydantic, update parse log | `backend/app/tasks/screenshot_tasks.py` | 3h |
| T-5.1.4b | Write prompt template for Indian payment screenshots (shared across providers) | `backend/app/screenshots/prompts.py` | 2h |
| T-5.1.5 | GET /api/v1/screenshots/{id}/status — poll parse status | `backend/app/screenshots/router.py` | 0.5h |
| T-5.1.6 | GET /api/v1/screenshots/{id}/result — return parsed data | `backend/app/screenshots/router.py` | 0.5h |
| T-5.1.7 | POST /api/v1/screenshots/{id}/confirm — create transaction from parsed data | `backend/app/screenshots/router.py` | 2h |
| T-5.1.8 | POST /api/v1/screenshots/{id}/retry — retry failed parse (max 3) | `backend/app/screenshots/router.py` | 1h |
| T-5.1.9 | Duplicate detection: image hash + UTR/UPI ref matching | `backend/app/screenshots/service.py` | 2h |
| T-5.1.10 | Rate limiting: 10/hr + 50/day per user, cost tracking in api_usage | `backend/app/screenshots/service.py` | 1h |
| T-5.1.11 | Frontend: Upload dropzone (drag-and-drop) | `frontend/src/components/screenshots/UploadDropzone.tsx` | 2h |
| T-5.1.12 | Frontend: Parse result preview with editable pre-filled form | `frontend/src/components/screenshots/ParsePreview.tsx` | 3h |
| T-5.1.13 | Frontend: Screenshot history page | `frontend/src/pages/Screenshots.tsx` | 2h |
| T-5.1.14 | Write parser tests with mock Claude API responses | `backend/tests/unit/test_screenshot_parser.py` | 3h |
| T-5.1.15 | Write upload integration tests (valid image, oversized, wrong type, duplicate) | `backend/tests/integration/test_screenshot_upload.py` | 2h |

**Dependencies:** Epic 1 (S3, Celery), Epic 2 (auth), Epic 4 (transactions)

**Claude Tool Definition (for T-5.1.4):**
```python
PARSE_TOOL = {
    "name": "record_transaction",
    "description": "Extract transaction details from the payment screenshot",
    "input_schema": {
        "type": "object",
        "properties": {
            "amount": {"type": "number", "description": "Amount in INR"},
            "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
            "payee": {"type": "string", "description": "Name of recipient/merchant"},
            "description": {"type": "string", "description": "Payment note or description"},
            "payment_method": {"type": "string", "enum": ["upi", "card", "neft", "imps", "cash", "other"]},
            "upi_ref": {"type": "string", "description": "UPI transaction reference number"},
            "transaction_status": {"type": "string", "enum": ["success", "failed", "pending"]},
            "suggested_category": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
        },
        "required": ["amount", "date", "transaction_status", "confidence"]
    }
}
```

---

# EPIC 6: Investment Tracking

**Goal:** Track stocks, gold, bonds with interest, CSV import
**T-Shirt Size:** L | **Priority:** P1 | **Phase:** 3

---

## US-6.1: Stock & Mutual Fund Holdings

**As a** user, **I want** to track my equity and MF holdings **so that** I know my investment portfolio value.

**Acceptance Criteria:**
- [ ] Add holdings: equity, mutual_fund, etf (name, symbol, ISIN, institution)
- [ ] Record buy/sell/dividend/SIP transactions
- [ ] Calculate: total invested, current value, returns (absolute + %)
- [ ] Average buy price computed from transaction history

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-6.1.1 | Create investments module (router, service, models, schemas) | `backend/app/investments/` | 2h |
| T-6.1.2 | CRUD for holdings: GET/POST/PATCH/DELETE /api/v1/investments/holdings | `backend/app/investments/router.py` | 2h |
| T-6.1.3 | POST /api/v1/investments/transactions (buy/sell/dividend/sip) | `backend/app/investments/router.py` | 2h |
| T-6.1.4 | Calculate returns (avg buy price, current value, absolute/% return) | `backend/app/investments/service.py` | 3h |
| T-6.1.5 | Frontend: Holdings list with P&L | `frontend/src/pages/Investments.tsx` | 3h |
| T-6.1.6 | Frontend: Add holding + record transaction forms | `frontend/src/components/investments/` | 3h |

---

## US-6.2: Gold Investment Tracking

**As a** user, **I want** to track gold (physical, digital, SGB) **so that** I see my total gold allocation.

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-6.2.1 | Support types: gold, gold_digital, sgb with weight in grams | `backend/app/investments/service.py` | 1h |
| T-6.2.2 | SGB: track 2.5% PA interest + maturity date | `backend/app/investments/service.py` | 1h |
| T-6.2.3 | Frontend: Gold holdings section | `frontend/src/components/investments/GoldHoldings.tsx` | 2h |

---

## US-6.3: Bond & FD Tracking with Interest

**As a** user, **I want** to track bonds and FDs with their interest schedule **so that** I know my passive income.

**Acceptance Criteria:**
- [ ] Bond details: face value, coupon rate, frequency (monthly/quarterly/semi-annual/annual), maturity date, issuer, credit rating
- [ ] Auto-calculate interest income per period
- [ ] Link to recurring transactions for auto-generated interest entries
- [ ] Show maturity timeline

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-6.3.1 | bond_details CRUD (1:1 with holding) | `backend/app/investments/router.py` | 2h |
| T-6.3.2 | Calculate interest schedule from coupon_rate + frequency | `backend/app/investments/service.py` | 2h |
| T-6.3.3 | Link to recurring_transactions for auto interest entries | `backend/app/investments/service.py` | 1h |
| T-6.3.4 | Frontend: Bond/FD detail page with interest schedule | `frontend/src/components/investments/BondDetail.tsx` | 3h |

---

## US-6.4: CSV Import from Zerodha/Groww

**As a** user, **I want** to import my holdings from a CSV file **so that** I don't enter them manually.

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-6.4.1 | POST /api/v1/investments/import/csv — parse Zerodha/Groww formats | `backend/app/investments/router.py` | 3h |
| T-6.4.2 | Show preview before confirming import | `backend/app/investments/service.py` | 1h |
| T-6.4.3 | GET /api/v1/investments/summary — portfolio overview | `backend/app/investments/router.py` | 2h |
| T-6.4.4 | Frontend: CSV upload + format selection + preview table | `frontend/src/components/investments/CSVImport.tsx` | 3h |

---

# EPIC 7: Budgets

**Goal:** Monthly budget tracking per category with alerts
**T-Shirt Size:** M | **Priority:** P1 | **Phase:** 2

---

## US-7.1: Budget Management

**As a** user, **I want** to set monthly budgets per category **so that** I know when I'm overspending.

**Acceptance Criteria:**
- [ ] Set budget amount per category per period (monthly/quarterly/yearly)
- [ ] Indian Financial Year aware (April-March)
- [ ] Alert threshold (default 80%)
- [ ] Budget status shows current spend vs limit with progress bar
- [ ] Alert triggered when threshold exceeded (after transaction create)

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-7.1.1 | Create budgets module (router, service, models, schemas) | `backend/app/budgets/` | 2h |
| T-7.1.2 | CRUD endpoints for budgets | `backend/app/budgets/router.py` | 2h |
| T-7.1.3 | GET /api/v1/budgets/status — each budget with current spend and % used | `backend/app/budgets/router.py` | 2h |
| T-7.1.4 | Celery task: check budget threshold after transaction create | `backend/app/tasks/budget_tasks.py` | 2h |
| T-7.1.5 | Frontend: Budget management page with progress bars | `frontend/src/pages/Budgets.tsx` | 3h |
| T-7.1.6 | Frontend: Budget alert notification (in-app) | `frontend/src/components/budgets/BudgetAlert.tsx` | 1h |
| T-7.1.7 | Write budget tests (FY calculations, threshold alerts) | `backend/tests/unit/test_budgets.py` | 2h |

**Dependencies:** Epic 3 (categories), Epic 4 (transactions)

---

# EPIC 8: Dashboard & Analytics

**Goal:** Visual overview of financial health with charts
**T-Shirt Size:** L | **Priority:** P1 | **Phase:** 2

---

## US-8.1: Financial Dashboard

**As a** user, **I want** a dashboard showing my financial overview **so that** I understand my money at a glance.

**Acceptance Criteria:**
- [ ] Summary cards: monthly income, expense, savings, savings rate
- [ ] Category breakdown pie chart
- [ ] Monthly trend line chart (income vs expense over 12 months)
- [ ] Budget status overview
- [ ] Net worth (accounts + investments)
- [ ] FY toggle (current, previous, custom date range)
- [ ] Redis caching (10-min TTL, invalidated on transaction write)

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-8.1.1 | Create dashboard module (router, service, schemas) | `backend/app/dashboard/` | 1h |
| T-8.1.2 | GET /api/v1/dashboard/summary — monthly income, expense, savings | `backend/app/dashboard/router.py` | 2h |
| T-8.1.3 | GET /api/v1/dashboard/category-breakdown — pie chart data | `backend/app/dashboard/router.py` | 2h |
| T-8.1.4 | GET /api/v1/dashboard/trend — 12-month line chart data | `backend/app/dashboard/router.py` | 2h |
| T-8.1.5 | GET /api/v1/dashboard/budget-status — all budgets progress | `backend/app/dashboard/router.py` | 1h |
| T-8.1.6 | GET /api/v1/dashboard/net-worth — accounts + investments total | `backend/app/dashboard/router.py` | 2h |
| T-8.1.7 | Redis caching layer (10-min TTL, invalidate on txn write) | `backend/app/dashboard/service.py` | 2h |
| T-8.1.8 | Frontend: Dashboard page with Recharts (pie, line, summary cards) | `frontend/src/pages/Dashboard.tsx` | 5h |
| T-8.1.9 | Frontend: FY toggle (current/previous/custom) | `frontend/src/components/dashboard/FYSelector.tsx` | 1h |

**Dependencies:** Epic 4 (transactions), Epic 6 (investments), Epic 7 (budgets)

---

# EPIC 9: Data Export & Compliance

**Goal:** DPDPA compliance — data export, account deletion, privacy
**T-Shirt Size:** M | **Priority:** P1 | **Phase:** 3

---

## US-9.1: Data Export for Tax Filing

**As a** user, **I want** to export my data as CSV **so that** I can share it with my CA during ITR season.

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-9.1.1 | Celery task: generate ZIP (transactions.csv, investments.csv, summary.json) | `backend/app/tasks/export_tasks.py` | 3h |
| T-9.1.2 | FY-wise export (April-March date range) | `backend/app/export/service.py` | 1h |
| T-9.1.3 | CSV injection prevention (prefix cells starting with =,+,-,@ with ') | `backend/app/export/service.py` | 0.5h |
| T-9.1.4 | Frontend: Export page with FY selector + download | `frontend/src/pages/Export.tsx` | 2h |

---

## US-9.2: Account Deletion (DPDPA Compliance)

**As a** user, **I want** to delete my account and all data **so that** I can exercise my right to erasure.

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-9.2.1 | DELETE /api/v1/me — soft delete, require re-authentication | `backend/app/auth/router.py` | 1h |
| T-9.2.2 | 30-day cooling-off with reactivation endpoint | `backend/app/auth/service.py` | 1h |
| T-9.2.3 | Celery weekly task: hard delete users past cooling-off | `backend/app/tasks/cleanup_tasks.py` | 2h |
| T-9.2.4 | Delete all user data: transactions, investments, screenshots, S3 files | `backend/app/tasks/cleanup_tasks.py` | 2h |
| T-9.2.5 | Frontend: Account deletion flow with confirmation modal | `frontend/src/components/auth/DeleteAccount.tsx` | 1h |

---

# EPIC 10: Monitoring, CI/CD & Production Hardening

**Goal:** Production-ready monitoring, testing, and deployment
**T-Shirt Size:** L | **Priority:** P1 | **Phase:** 3

---

## US-10.1: Monitoring & Alerting

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-10.1.1 | Sentry integration (FastAPI + Celery + SQLAlchemy) | `backend/app/main.py` | 1h |
| T-10.1.2 | Prometheus metrics (prometheus-fastapi-instrumentator) | `backend/app/main.py` | 1h |
| T-10.1.3 | Custom metrics: users_total, transactions_created, screenshot_parses, claude_api_cost | `backend/app/core/metrics.py` | 2h |
| T-10.1.4 | Structured logging (structlog, JSON, request_id + user_id) | `backend/app/core/logging.py` | 2h |
| T-10.1.5 | PII sanitization formatter (redact phone, UPI, account numbers) | `backend/app/core/logging.py` | 1h |

---

## US-10.2: CI/CD Pipeline

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-10.2.1 | GitHub Actions: backend tests (pytest + PostgreSQL + Redis services) | `.github/workflows/ci.yml` | 2h |
| T-10.2.2 | GitHub Actions: frontend (lint + type-check + tests) | `.github/workflows/ci.yml` | 1h |
| T-10.2.3 | Security scanning: pip-audit + npm audit + Trivy | `.github/workflows/ci.yml` | 1h |
| T-10.2.4 | Docker image build and push | `.github/workflows/ci.yml` | 1h |
| T-10.2.5 | Auto-deploy to staging on main push | `.github/workflows/deploy.yml` | 2h |

---

## US-10.3: Database Backups

**Tasks:**

| ID | Task | File(s) | Est |
|----|------|---------|-----|
| T-10.3.1 | Backup script (pg_dump → S3, 30-day retention) | `scripts/backup_db.sh` | 1h |
| T-10.3.2 | Schedule via Celery Beat (daily 3 AM IST) | `backend/app/tasks/celery_app.py` | 0.5h |
| T-10.3.3 | Document and test restore procedure | `docs/deployment.md` | 1h |

---

# Task Summary

| Epic | Stories | Tasks | Est Hours |
|------|---------|-------|-----------|
| 1. Foundation | 4 | 39 | ~55h |
| 2. Auth | 3 | 23 | ~35h |
| 3. Accounts & Categories | 2 | 9 | ~14h |
| 4. Transactions | 3 | 17 | ~30h |
| 5. Screenshots | 1 | 15 | ~30h |
| 6. Investments | 4 | 13 | ~26h |
| 7. Budgets | 1 | 7 | ~14h |
| 8. Dashboard | 1 | 9 | ~18h |
| 9. Export & Compliance | 2 | 9 | ~14h |
| 10. Monitoring & CI/CD | 3 | 11 | ~14h |
| **TOTAL** | **24** | **152** | **~250h** |

---

# Sprint Plan

## Sprint 1 (Week 1-2): Foundation
T-1.1.1 → T-1.1.10, T-1.3.1 → T-1.3.7, T-1.4.1 → T-1.4.12

## Sprint 2 (Week 3-4): Auth + Core CRUD
T-2.1.1 → T-2.1.12, T-2.2.1 → T-2.2.6, T-3.1.1 → T-3.2.5, T-1.2.1 → T-1.2.9

## Sprint 3 (Week 5-6): Transactions + Screenshots
T-4.1.1 → T-4.1.9, T-5.1.1 → T-5.1.15

## Sprint 4 (Week 7-8): Budgets + Dashboard
T-4.2.1 → T-4.3.3, T-7.1.1 → T-7.1.7, T-8.1.1 → T-8.1.9

## Sprint 5 (Week 9-10): Investments
T-6.1.1 → T-6.4.4

## Sprint 6 (Week 11-12): Production
T-9.1.1 → T-9.2.5, T-10.1.1 → T-10.3.3, T-2.3.1 → T-2.3.6
