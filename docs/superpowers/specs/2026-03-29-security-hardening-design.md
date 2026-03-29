# Security Hardening Design Spec

**Date:** 2026-03-29
**Status:** Approved
**Author:** Staff Architect (Claude)
**Scope:** Address 12 critical security gaps identified in architecture re-evaluation

---

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vision provider compliance | Regulatory gate with `data_residency_compliant` flag | Flexibility without RBI violation |
| Session revocation | Soft revocation (15-min grace) | Less disruptive, access tokens expire naturally |
| PII encryption at rest | TDE + full-disk encryption (no app-level) | Sufficient for IT Act 43A, avoids blind index complexity |
| Celery task signing | Network isolation only (no message signing) | Redis in private subnet; signing adds operational burden |

---

## 1. Vision Provider Regulatory Gate

### Design

Add `data_residency_compliant` flag to provider registry. Factory rejects non-compliant providers unless explicitly overridden (test-only).

```python
# screenshots/providers/registry.py

PROVIDER_REGISTRY = {
    "anthropic": {
        "data_residency_compliant": True,
        "legal_review_date": "2026-03-29",
        "notes": "Anthropic API terms: data not used for training, not stored",
    },
    "openai": {
        "data_residency_compliant": False,
        "legal_review_date": None,
        "notes": "May process outside India. Requires legal sign-off.",
    },
    "google": {
        "data_residency_compliant": False,
        "legal_review_date": None,
        "notes": "May process outside India. Requires legal sign-off.",
    },
}
```

```python
# screenshots/providers/factory.py

def get_vision_provider() -> VisionProvider:
    provider_name = settings.VISION_PROVIDER
    registry = PROVIDER_REGISTRY.get(provider_name)

    if not registry:
        raise ConfigurationError(f"Unknown provider: {provider_name}")

    if not registry["data_residency_compliant"]:
        if not settings.VISION_ALLOW_NON_COMPLIANT:
            raise ConfigurationError(
                f"Provider '{provider_name}' is not RBI data-residency compliant. "
                f"Set VISION_ALLOW_NON_COMPLIANT=true to override (testing only)."
            )
        # Log override to audit
        logger.warning(
            "non_compliant_provider_override",
            provider=provider_name,
            env=settings.ENVIRONMENT,
        )

    return _create_provider(provider_name)
```

**Env vars:**
```bash
VISION_PROVIDER=anthropic
VISION_ALLOW_NON_COMPLIANT=false   # true only in dev/test
```

**Files:** `backend/app/screenshots/providers/registry.py`, `backend/app/screenshots/providers/factory.py`

---

## 2. Session Revocation (Soft, 15-min Grace)

### Design

On security events, mark all refresh tokens as revoked. Existing access tokens work until natural 15-min expiry. No new tokens issued.

```python
# auth/service.py

async def soft_revoke_user_sessions(
    db: AsyncSession, user_id: UUID, reason: str, ip_address: str = None
):
    """Revoke all refresh tokens. Access tokens expire naturally (15 min max)."""
    result = await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.utcnow(), revoke_reason=reason)
    )

    db.add(AuditLog(
        user_id=user_id,
        action="SESSION_REVOKE_ALL",
        resource_type="refresh_token",
        metadata={"reason": reason, "tokens_revoked": result.rowcount},
        ip_address=ip_address,
    ))
```

**Trigger events:**

| Event | Reason | Endpoint |
|-------|--------|----------|
| Account deletion | `account_deleted` | `DELETE /api/v1/me` |
| Phone number change | `phone_changed` | `PATCH /api/v1/me` |
| Email change | `email_changed` | `PATCH /api/v1/me` |
| User-requested | `user_requested` | `POST /api/v1/auth/revoke-all-sessions` |

**New endpoint:**
```
POST /api/v1/auth/revoke-all-sessions
  - Requires re-authentication (send current OTP or Google token)
  - Revokes all refresh tokens for the user
  - Returns: { "sessions_revoked": 3 }
```

**Refresh endpoint check:**
```python
# auth/router.py — POST /api/v1/auth/refresh

token = await db.execute(
    select(RefreshToken).filter_by(token_hash=token_hash)
).scalar_one_or_none()

if not token or token.revoked_at is not None:
    raise HTTPException(401, "Session expired or revoked")
```

**Files:** `backend/app/auth/service.py`, `backend/app/auth/router.py`

---

## 3. Rate Limits on All Endpoints

### Design

Every endpoint gets a rate limit. Keyed by `user_id` for authenticated endpoints, `IP` for unauthenticated.

```python
# core/rate_limit.py — applied as FastAPI dependencies

RATE_LIMITS = {
    # Auth (by IP)
    "auth_otp_send":      {"limit": 3,   "window": 600,   "key": "ip"},       # 3/10min
    "auth_otp_verify":    {"limit": 5,   "window": 900,   "key": "ip"},       # 5/15min
    "auth_login":         {"limit": 10,  "window": 60,    "key": "ip"},       # 10/min
    "auth_refresh":       {"limit": 30,  "window": 60,    "key": "ip"},       # 30/min

    # Reads (by user_id)
    "api_read":           {"limit": 200, "window": 60,    "key": "user_id"},  # 200/min
    "dashboard":          {"limit": 30,  "window": 60,    "key": "user_id"},  # 30/min

    # Writes (by user_id)
    "api_write":          {"limit": 50,  "window": 60,    "key": "user_id"},  # 50/min
    "transaction_create": {"limit": 30,  "window": 60,    "key": "user_id"},  # 30/min

    # Screenshots (by user_id)
    "screenshot_upload":  {"limit": 10,  "window": 3600,  "key": "user_id"},  # 10/hr
    "screenshot_daily":   {"limit": 50,  "window": 86400, "key": "user_id"},  # 50/day

    # Export (by user_id)
    "export":             {"limit": 5,   "window": 3600,  "key": "user_id"},  # 5/hr

    # Health (by IP)
    "health":             {"limit": 60,  "window": 60,    "key": "ip"},       # 60/min
}
```

Response headers on all 200/429 responses:
```
X-RateLimit-Limit: 200
X-RateLimit-Remaining: 187
X-RateLimit-Reset: 1711720800
```

**Files:** `backend/app/core/rate_limit.py`, all router files

---

## 4. Audit Logging with Before/After Values

### Design

Financial mutations log old and new values. Non-financial mutations log action only.

```python
# core/audit.py

async def audit_financial_mutation(
    db: AsyncSession,
    user_id: UUID,
    action: str,           # "TRANSACTION_UPDATE", "TRANSACTION_DELETE"
    resource_type: str,
    resource_id: str,
    old_values: dict,      # {"amount": 5000, "category_id": "..."}
    new_values: dict | None,  # None for deletes
    ip_address: str,
):
    db.add(AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        metadata={
            "old": old_values,
            "new": new_values,
            "fields_changed": [k for k in (new_values or {}) if old_values.get(k) != new_values.get(k)],
        },
    ))
```

**Audited events:**

| Action | old_values | new_values |
|--------|-----------|------------|
| `TRANSACTION_CREATE` | `None` | full row |
| `TRANSACTION_UPDATE` | changed fields (old) | changed fields (new) |
| `TRANSACTION_DELETE` | full row | `None` |
| `ACCOUNT_BALANCE_ADJUST` | `{balance: old}` | `{balance: new}` |
| `BUDGET_UPDATE` | `{amount: old}` | `{amount: new}` |
| `INVESTMENT_TRANSACTION` | `None` | full row |

**Files:** `backend/app/core/audit.py`, transaction/investment/budget service files

---

## 5. Admin Session Audit Logging

### Design

Every Celery task using `sync_db_session_as_admin()` logs entry and exit.

```python
# core/database.py

@contextmanager
def sync_db_session_as_admin(task_name: str, task_id: str):
    """Admin session that bypasses RLS. Logs entry/exit for audit."""
    session = sync_session_factory()
    try:
        # Log entry
        session.add(AuditLog(
            user_id=None,  # system event
            action="ADMIN_SESSION_START",
            resource_type="celery_task",
            metadata={"task_name": task_name, "task_id": task_id},
        ))
        session.commit()

        yield session

        # Log exit
        session.add(AuditLog(
            user_id=None,
            action="ADMIN_SESSION_END",
            resource_type="celery_task",
            metadata={"task_name": task_name, "task_id": task_id, "status": "success"},
        ))
        session.commit()
    except Exception as e:
        session.rollback()
        # Log failure
        session.add(AuditLog(
            user_id=None,
            action="ADMIN_SESSION_ERROR",
            resource_type="celery_task",
            metadata={"task_name": task_name, "task_id": task_id, "error": str(e)[:500]},
        ))
        session.commit()
        raise
    finally:
        session.close()
```

**Files:** `backend/app/core/database.py`

---

## 6. S3 Presigned URL Ownership Validation

### Design

Before generating a presigned download URL, verify the screenshot belongs to the requesting user.

```python
# screenshots/service.py

async def get_screenshot_download_url(
    db: AsyncSession, parse_log_id: UUID, user_id: UUID
) -> str:
    log = await db.execute(
        select(ScreenshotParseLog).filter_by(id=parse_log_id, user_id=user_id)
    ).scalar_one_or_none()

    if not log:
        raise HTTPException(404)  # 404, not 403 — don't confirm existence

    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": log.s3_key},
        ExpiresIn=300,  # 5 minutes for downloads
    )
```

Upload presigned URLs: 15-minute TTL, scoped to user's S3 prefix (`{user_id}/{year-month}/`).

**Files:** `backend/app/screenshots/service.py`, `backend/app/core/storage.py`

---

## 7. LLM Confidence Threshold (Modified: 0.6/0.8)

### Design

Three confidence tiers determine UX behavior:

| Confidence | Behavior | UI |
|------------|----------|----|
| `< 0.6` | **Reject** — don't show pre-filled form | "Could not extract data. Please enter manually." |
| `0.6 - 0.8` | **Warning** — show form with yellow highlight | "Low confidence. Please verify all fields." |
| `>= 0.8` | **Auto-fill** — show form normally | "Review and confirm." |

```python
# screenshots/schemas.py

class ParseConfidence(str, Enum):
    REJECTED = "rejected"      # < 0.6
    LOW = "low"                # 0.6 - 0.8
    HIGH = "high"              # >= 0.8

def classify_confidence(score: float) -> ParseConfidence:
    if score < 0.6:
        return ParseConfidence.REJECTED
    elif score < 0.8:
        return ParseConfidence.LOW
    return ParseConfidence.HIGH
```

Applied in the screenshot confirm flow — rejected parses cannot be confirmed without manual field entry.

**Files:** `backend/app/screenshots/schemas.py`, `backend/app/screenshots/service.py`

---

## 8. CORS Origin from Environment Variable

### Design

```python
# core/config.py

class Settings(BaseSettings):
    CORS_ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]  # dev default
```

```python
# main.py

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)
```

```bash
# .env (production)
CORS_ALLOWED_ORIGINS=["https://expenses.yourdomain.com"]
```

**Files:** `backend/app/core/config.py`, `backend/app/main.py`

---

## 9. Docker Hardening

### Design

```dockerfile
# Backend Dockerfile — add HEALTHCHECK
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
```

```yaml
# docker-compose.prod.yml — security context for all services
services:
  backend:
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    read_only: true
    tmpfs:
      - /tmp
    volumes:
      - /app/uploads  # writable mount for temp files

  celery-worker:
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    read_only: true
    tmpfs:
      - /tmp
    stop_grace_period: 30s
```

**Files:** `backend/Dockerfile`, `frontend/Dockerfile`, `docker/docker-compose.prod.yml`

---

## 10. Celery Task Idempotency

### Design

Screenshot parsing uses status-based idempotency:

```python
# tasks/screenshot_tasks.py

@celery_app.task(bind=True, queue="parsing", max_retries=2)
def parse_screenshot(self, parse_log_id: str):
    with sync_db_session() as db:
        log = db.get(ScreenshotParseLog, parse_log_id)

        # Idempotency: skip if already processing or completed
        if log.status in ("processing", "parsed", "confirmed"):
            logger.info("skipping_duplicate_parse", parse_log_id=parse_log_id, status=log.status)
            return

        log.status = "processing"
        db.commit()
        # ... continue with provider call
```

Recurring transactions use date-based dedup:

```python
# tasks/recurring_tasks.py

def generate_due_transactions():
    with sync_db_session_as_admin("generate_recurring", self.request.id) as db:
        due = db.query(RecurringTransaction).filter(
            RecurringTransaction.next_due_date <= date.today(),
            RecurringTransaction.is_active == True,
        ).all()

        for recurring in due:
            # Idempotency: check if today's entry already exists
            exists = db.query(Transaction).filter(
                Transaction.recurring_id == recurring.id,
                Transaction.transaction_date == recurring.next_due_date,
            ).first()

            if exists:
                continue  # Already generated

            # Create transaction + advance next_due_date
```

**Files:** `backend/app/tasks/screenshot_tasks.py`, `backend/app/tasks/recurring_tasks.py`

---

## 11. CSP Reporting (Deferred to Sprint 5)

Not included in V1. Ship with tight CSP header. Add `report-uri` endpoint in Sprint 5 after launch traffic establishes baseline.

---

## Summary of Changes

| # | Fix | Sprint | Effort |
|---|-----|--------|--------|
| 1 | Vision provider regulatory gate | 1 | 2h |
| 2 | Session revocation (soft) | 2 | 3h |
| 3 | Rate limits on all endpoints | 1 | 3h |
| 4 | Financial audit logging (before/after) | 2 | 4h |
| 5 | Admin session audit | 1 | 1h |
| 6 | S3 presigned URL ownership | 2 | 1h |
| 7 | LLM confidence threshold (0.6/0.8) | 3 | 1h |
| 8 | CORS from env var | 1 | 0.5h |
| 9 | Docker hardening | 6 | 1h |
| 10 | Celery idempotency | 3 | 2h |
| 11 | CSP reporting | 5 | Deferred |
| **Total** | | | **~18.5h** |
