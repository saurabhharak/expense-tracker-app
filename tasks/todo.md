# Task Tracker

## Completed
- [x] Project setup — multi-agent configuration
- [x] Architecture doc (docs/architecture.md — 4,191 lines)
- [x] Security doc (docs/security.md — 983 lines)
- [x] Security rules (.claude/rules/security.md — 216 lines)
- [x] Epics & stories (docs/epics-and-stories.md — 10 epics, 24 stories, 152 tasks)
- [x] Architecture review — 5 critical fixes applied
- [x] Doc contradictions resolved (JWT RS256, rate limits, audit schema, API prefix)

## Next: Sprint 1 — Foundation (Week 1-2)

### Backend Scaffolding (US-1.1)
- [ ] T-1.1.1: Initialize backend Python project (pyproject.toml)
- [ ] T-1.1.2: FastAPI app factory (app/main.py)
- [ ] T-1.1.3: Dual DB session factory (async + sync) with RLS context
- [ ] T-1.1.4: Alembic async migrations config
- [ ] T-1.1.5: Core middleware (request ID, timing, security headers)
- [ ] T-1.1.6: Pydantic settings (app/core/config.py)
- [ ] T-1.1.7: Backend Dockerfile
- [ ] T-1.1.8: Health check endpoint
- [ ] T-1.1.9: Redis client singleton
- [ ] T-1.1.10: S3 client abstraction

### Infrastructure (US-1.3)
- [ ] T-1.3.1: Dev docker-compose.yml
- [ ] T-1.3.2: Prod docker-compose.prod.yml
- [ ] T-1.3.3: Caddyfile
- [ ] T-1.3.4: PgBouncer config
- [ ] T-1.3.5: Redis config
- [ ] T-1.3.6: .env.example
- [ ] T-1.3.7: Seed categories script

### Database Schema (US-1.4)
- [ ] T-1.4.1: Migration: users + refresh_tokens
- [ ] T-1.4.2: Migration: categories (hierarchical) + RLS
- [ ] T-1.4.3: Migration: accounts + RLS
- [ ] T-1.4.4: Migration: transactions (indexes, GIN, trigger) + RLS
- [ ] T-1.4.5: Migration: recurring_transactions + RLS
- [ ] T-1.4.6: Migration: budgets (FY-aware) + RLS
- [ ] T-1.4.7: Migration: investments (holdings, transactions, bonds) + RLS
- [ ] T-1.4.8: Migration: screenshot_parse_logs + api_usage + RLS
- [ ] T-1.4.9: Migration: audit_logs (BIGSERIAL, INSERT-only)
- [ ] T-1.4.10: Migration: FY helpers + balance trigger + updated_at trigger
- [ ] T-1.4.11: Migration: seed Indian categories
- [ ] T-1.4.12: RLS isolation integration test (CRITICAL)

## Backlog

### Sprint 2 (Week 3-4): Auth + CRUD
See docs/epics-and-stories.md — Epic 2, Epic 3, US-1.2

### Sprint 3 (Week 5-6): Transactions + Screenshots
See docs/epics-and-stories.md — US-4.1, Epic 5

### Sprint 4 (Week 7-8): Budgets + Dashboard
See docs/epics-and-stories.md — US-4.2, US-4.3, Epic 7, Epic 8

### Sprint 5 (Week 9-10): Investments
See docs/epics-and-stories.md — Epic 6

### Sprint 6 (Week 11-12): Production
See docs/epics-and-stories.md — Epic 9, Epic 10
