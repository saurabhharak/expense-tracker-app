---
paths:
  - "backend/**"
  - "frontend/**"
---

# Security Review Rules for Financial Application

This application is classified as **HIGH RISK** (financial PII, RBI regulations, DPDPA 2023, external LLM data processing). Every code change touching backend or frontend must be evaluated against these rules.

## AUTOMATIC REJECTION Criteria

The following are non-negotiable. Any code change that violates these rules must be rejected immediately with a clear explanation. Do not suggest workarounds; the code must be fixed.

### 1. No SQL String Interpolation

**REJECT** any SQL query using f-strings, `.format()`, or `%` interpolation.

```python
# REJECTED - SQL injection risk (CWE-89)
db.execute(f"SELECT * FROM transactions WHERE user_id = '{user_id}'")
db.execute("SELECT * FROM transactions WHERE user_id = '%s'" % user_id)
db.execute("SELECT * FROM transactions WHERE user_id = '{}'".format(user_id))

# ACCEPTED - parameterized query
db.execute(text("SELECT * FROM transactions WHERE user_id = :uid"), {"uid": user_id})
```

Use SQLAlchemy ORM or parameterized queries with `text()` exclusively.

### 2. No Missing Authentication

**REJECT** any endpoint missing `current_user` dependency injection.

Every API endpoint that accesses or modifies user data must include the `current_user` dependency. Public endpoints (health check, auth) are the only exceptions and must be explicitly documented.

```python
# REJECTED - no authentication
@router.get("/transactions")
async def list_transactions(db: Session = Depends(get_db)):
    ...

# ACCEPTED - authenticated
@router.get("/transactions")
async def list_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ...
```

### 3. No Missing User ID Filter

**REJECT** any database query on user data that does not include a `user_id` filter.

Even with Row-Level Security (RLS) enabled, the application layer must always filter by `user_id`. RLS is the safety net, not the primary filter.

```python
# REJECTED - missing user_id filter (IDOR risk)
transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()

# ACCEPTED - includes user_id filter
transaction = db.query(Transaction).filter(
    Transaction.id == transaction_id,
    Transaction.user_id == current_user.id,
).first()
```

### 4. No dangerouslySetInnerHTML

**REJECT** any use of `dangerouslySetInnerHTML` in React code.

This is a direct XSS vector (CWE-79). LLM output and user data must always be rendered as text, never as HTML.

```jsx
// REJECTED - XSS risk
<div dangerouslySetInnerHTML={{ __html: llmResponse.description }} />

// ACCEPTED - safe text rendering
<div>{llmResponse.description}</div>
```

### 5. No Hardcoded Secrets

**REJECT** any hardcoded secret, API key, password, or credential in source code.

This includes configuration files, environment variable defaults, comments, and test fixtures. Secrets must come from AWS Secrets Manager or equivalent vault at runtime.

```python
# REJECTED - hardcoded API key
CLAUDE_API_KEY = "sk-ant-api03-..."
DATABASE_URL = "postgresql://user:password123@localhost/db"

# ACCEPTED - from secrets manager
CLAUDE_API_KEY = get_secret("claude-api-key")
DATABASE_URL = get_secret("database-url")
```

### 6. No Original Filenames in File Uploads

**REJECT** any file upload endpoint that uses the original filename from the user.

Original filenames enable path traversal attacks (CWE-22) and information disclosure. All files must be renamed to UUIDs.

```python
# REJECTED - uses original filename
file_path = f"/uploads/{uploaded_file.filename}"

# ACCEPTED - UUID filename
file_path = f"/uploads/{uuid.uuid4()}{Path(uploaded_file.filename).suffix}"
```

### 7. No Unprotected Endpoints (Rate Limiting)

**REJECT** any endpoint missing rate limiting.

All endpoints must have rate limits applied, either via decorator or middleware. Refer to the rate limiting table in the security architecture document for specific limits.

```python
# REJECTED - no rate limit
@router.post("/upload/screenshot")
async def upload_screenshot(...):
    ...

# ACCEPTED - rate limited
@router.post("/upload/screenshot")
@limiter.limit("10/hour")
async def upload_screenshot(...):
    ...
```

### 8. No PII in Logs

**REJECT** any log statement that contains or could contain PII (phone numbers, UPI IDs, bank account numbers, full names combined with financial data).

```python
# REJECTED - logs phone number
logger.info(f"OTP sent to {phone_number}")
logger.info(f"User {user.phone} logged in")
logger.debug(f"Processing UPI payment to {upi_id}")

# ACCEPTED - uses user ID reference only
logger.info(f"OTP sent to user_id={user.id}")
logger.info(f"User {user.id} logged in")
logger.debug(f"Processing UPI payment for transaction_id={txn.id}")
```

### 9. No Unvalidated LLM Responses

**REJECT** any LLM response that is used without Pydantic validation.

All data extracted by the LLM must pass through a Pydantic model with field-level validation before being used, stored, or returned to the client.

```python
# REJECTED - raw LLM response used directly
result = await claude_client.parse_screenshot(image)
transaction = Transaction(**result)  # No validation

# ACCEPTED - validated through Pydantic
result = await claude_client.parse_screenshot(image)
validated = ParsedTransactionSchema(**result)  # Pydantic validates all fields
transaction = Transaction(**validated.dict())
```

### 10. No Wildcard CORS with Credentials

**REJECT** any CORS configuration using `"*"` as an allowed origin when credentials are enabled.

```python
# REJECTED - wildcard with credentials
CORSMiddleware(allow_origins=["*"], allow_credentials=True, ...)

# ACCEPTED - explicit whitelist
CORSMiddleware(allow_origins=["https://expenses.yourdomain.com"], allow_credentials=True, ...)
```

### 11. No Sequential IDs in API URLs

**REJECT** any sequential integer ID exposed in API request or response URLs/bodies.

Public-facing IDs must be UUIDs. Sequential integers reveal entity count and enable enumeration attacks.

```python
# REJECTED - sequential ID in URL
GET /api/v1/transactions/42

# ACCEPTED - UUID in URL
GET /api/v1/transactions/7c9e6679-7425-40de-944b-e07fc1f90ae7
```

### 12. No Unencrypted Database or Cache Connections in Production

**REJECT** any missing TLS/SSL on database or Redis connections in production configuration.

```python
# REJECTED - no SSL
DATABASE_URL = "postgresql://user:pass@host/db"
REDIS_URL = "redis://host:6379"

# ACCEPTED - SSL enabled
DATABASE_URL = "postgresql://user:pass@host/db?sslmode=verify-full"
REDIS_URL = "rediss://host:6379"  # note: rediss:// (with double s) enables TLS
```

## Additional Review Guidelines

When reviewing code that touches these areas, also verify:

- **File uploads**: Magic byte validation (not just Content-Type), Pillow re-encoding, dimension limits
- **Error responses**: No stack traces leaked, SQLAlchemy errors caught separately, generic messages returned
- **Audit logging**: Auth events, data access, modifications, and deletions are logged
- **CSRF**: SameSite=Strict on cookies, X-Requested-With header required
- **Security headers**: X-Content-Type-Options, X-Frame-Options, HSTS, CSP, Referrer-Policy, Permissions-Policy present
- **Data retention**: Screenshots auto-deleted after 90 days, export includes all user data
- **Transaction integrity**: HMAC checksums computed on insert, verified on read
- **RLS context**: `SET LOCAL app.current_user_id` used (not `SET`), scoped to transaction
