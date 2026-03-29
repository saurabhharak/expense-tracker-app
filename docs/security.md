# Security Architecture Document

**Application:** Personal Expense Tracker (Multi-Tenant Financial WebApp)
**Classification:** HIGH RISK
**Last Updated:** 2026-03-29
**Version:** 1.0

---

## Table of Contents

1. [Risk Classification](#1-risk-classification)
2. [Authentication & Session Security](#2-authentication--session-security)
3. [Authorization & Data Isolation](#3-authorization--data-isolation)
4. [Input Validation & Injection Prevention](#4-input-validation--injection-prevention)
5. [File Upload Security](#5-file-upload-security-payment-screenshots)
6. [API Security](#6-api-security)
7. [Data Security](#7-data-security)
8. [LLM/AI Security](#8-llmai-security)
9. [Indian Regulatory Compliance](#9-indian-regulatory-compliance)
10. [Audit Logging](#10-audit-logging)
11. [Transaction Integrity](#11-transaction-integrity)
12. [Infrastructure Security](#12-infrastructure-security)
13. [Privacy & Compliance](#13-privacy--compliance)
14. [Threat Model (Top 10)](#14-threat-model-top-10)
15. [V1 Security Checklist](#15-v1-security-checklist-non-negotiable)
16. [V1 Should-Have](#16-v1-should-have-within-first-month)
17. [V2 Items](#17-v2-items-within-3-months)

---

## 1. Risk Classification

**HIGH RISK** application due to the following factors:

- **Financial PII**: The application processes and stores sensitive financial data including UPI IDs, bank account numbers, transaction amounts, and spending patterns.
- **RBI Regulations**: Subject to Reserve Bank of India data localization and security requirements for financial data handling.
- **DPDPA 2023**: Must comply with the Digital Personal Data Protection Act 2023, India's comprehensive data protection law covering consent, purpose limitation, data principal rights, and breach notification.
- **External LLM Data Processing**: Payment screenshots are sent to external AI (Anthropic Claude) for OCR and parsing, creating a data flow outside the application boundary.
- **Multi-Tenant Architecture**: Thousands of Indian users sharing infrastructure demands rigorous data isolation.

Any security failure could result in:
- Financial fraud or unauthorized access to transaction data
- Regulatory penalties under RBI directives and DPDPA 2023
- Reputational damage and loss of user trust
- Legal liability under IT Act 2000 Sections 43A and 72A

---

## 2. Authentication & Session Security

### Primary Authentication: Mobile OTP (Indian Market)

Mobile OTP is the primary authentication method, optimized for the Indian market where mobile-first usage dominates.

- **Provider**: MSG91 SMS gateway
- **OTP Format**: 6-digit numeric code
- **OTP Expiry**: 5 minutes from generation
- **Single Use**: Each OTP is invalidated immediately after successful verification or expiry
- **Rate Limiting**: Maximum 3 OTP requests per phone number per 10-minute window
- **Verification Attempts**: Maximum 5 verification attempts per phone number per 15-minute window

### Secondary Authentication: Google OAuth2

- Standard OAuth2 Authorization Code flow
- Verify `id_token` signature and claims server-side
- Link Google accounts to existing phone-based accounts via verified email or phone match

### Session & Token Management

| Token Type | Storage | Lifetime | Details |
|---|---|---|---|
| JWT Access Token | In-memory (JavaScript variable) | 15 minutes | Short-lived, contains user_id and role claims |
| Opaque Refresh Token | httpOnly Secure SameSite=Strict cookie | 30 days | Used only to obtain new access tokens |

- **Token Rotation**: A new refresh token is issued on every refresh request. The previous refresh token is immediately invalidated. This limits the window of a stolen refresh token.
- **Refresh Token Reuse Detection**: If a previously rotated (invalidated) refresh token is presented, revoke the entire token family and force re-authentication. This indicates token theft.

### Account Lockout Policy

- **Threshold**: 5 failed authentication attempts
- **Lockout Duration**: 15 minutes (exponential backoff not applied in V1, but recommended for V2)
- **CAPTCHA Trigger**: CAPTCHA challenge is presented after 3 failed attempts (before lockout)
- **CAPTCHA Provider**: hCaptcha (GDPR-friendly, works well in India)

### MFA for High-Value Operations

- **Method**: TOTP (Time-based One-Time Password) via authenticator apps (Google Authenticator, Authy)
- **Protected Operations**: Data export, account deletion, changing phone number, changing linked email
- **Implementation**: `pyotp` library for TOTP generation and verification
- **Recovery**: One-time recovery codes generated at TOTP setup (store hashed, show once)

### Libraries

| Library | Purpose |
|---|---|
| `python-jose` | JWT creation, validation, and signing (RS256 recommended) |
| `passlib[bcrypt]` | Password hashing (for any future password-based flows) |
| `pyotp` | TOTP generation and verification for MFA |
| `fastapi-limiter` | Rate limiting middleware using Redis backend |

---

## 3. Authorization & Data Isolation

### PostgreSQL Row-Level Security (RLS)

RLS is the **primary data isolation mechanism**. It operates at the database level, providing defense-in-depth independent of application logic.

```sql
-- Example RLS policy on transactions table
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions FORCE ROW LEVEL SECURITY;

CREATE POLICY transactions_isolation ON transactions
    USING (user_id = current_setting('app.current_user_id')::uuid)
    WITH CHECK (user_id = current_setting('app.current_user_id')::uuid);
```

**Critical RLS Rules:**

1. **EVERY user-data table** must have RLS enabled. No exceptions.
2. **FORCE ROW LEVEL SECURITY** must be set on every table so that even the table owner is subject to RLS policies. This prevents bypassing RLS if the application database role inadvertently has ownership privileges.
3. **Application database role must NOT be a superuser** or have `BYPASSRLS` privilege. Superusers bypass RLS entirely.
4. **`SET LOCAL`** must be used to set the `app.current_user_id` configuration parameter within each transaction. `SET LOCAL` is scoped to the current transaction and automatically resets, preventing cross-request leakage in connection-pooled environments.

```python
# Per-request RLS context setup (FastAPI dependency)
async def set_rls_context(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await db.execute(
        text("SET LOCAL app.current_user_id = :user_id"),
        {"user_id": str(current_user.id)},
    )
    return db
```

### Public-Facing ID Strategy

- **External**: UUIDs (v4) for all IDs exposed in API responses and URLs
- **Internal**: Sequential integer IDs (bigint) for database performance (joins, indexing)
- **Mapping**: API layer translates between UUID and internal ID; internal IDs never leave the backend

### Information Disclosure Prevention (CWE-203)

- **Return 404 (not 403)** when a user attempts to access a resource they do not own. Returning 403 confirms the resource exists, which is an information leak.
- Apply this consistently across all endpoints.

### IDOR Prevention

- **Every database query** on user data must include a `user_id` filter, even with RLS enabled (defense-in-depth).
- Application-level ownership checks serve as the first line; RLS is the safety net.

### Automated Testing

- **RLS isolation tests are required** in the test suite: create data as User A, attempt to read/modify/delete as User B, assert failure.
- These tests must run in CI on every PR.

---

## 4. Input Validation & Injection Prevention

### SQL Injection (CWE-89)

- **Primary Defense**: SQLAlchemy ORM with parameterized queries exclusively
- **Ban**: f-strings, `.format()`, and `%` string interpolation anywhere near database queries. This is an **automatic rejection** criterion in code review.
- **Raw SQL**: If absolutely necessary (rare), use `text()` with bound parameters only: `text("SELECT * FROM t WHERE id = :id")` with `{"id": value}`

### Cross-Site Scripting / XSS (CWE-79)

- **React Default**: React escapes all interpolated values by default. This is the primary defense.
- **Ban**: `dangerouslySetInnerHTML` is **banned** in this codebase. Any use is an automatic rejection.
- **LLM Output**: All output from the LLM (Claude) must be treated as **untrusted user input**. It must be validated through Pydantic models and rendered as text (never as HTML) on the frontend.
- **CSP**: Content Security Policy header to prevent inline script execution (see Section 6).

### Command Injection (CWE-78)

- **Image Processing**: Use `Pillow` (PIL) for all image manipulation. Never invoke shell commands (`convert`, `ffmpeg`, etc.) for processing user-uploaded files.
- **General Rule**: Avoid `subprocess`, `os.system`, and `os.popen` with user-influenced input.

### Path Traversal (CWE-22)

- **UUID Filenames**: All uploaded files are renamed to UUID-based filenames. The original filename from the user is **never** used for storage.
- **No User-Controlled Paths**: File retrieval endpoints use resource IDs that map to stored paths; users never supply file paths.

### CSV Injection (CWE-1236)

When exporting transaction data to CSV:

- **Prefix** any cell value starting with `=`, `+`, `-`, `@`, `\t`, or `\r` with a single quote (`'`).
- This prevents formula injection when users open exported CSV files in Excel or Google Sheets.

```python
def sanitize_csv_value(value: str) -> str:
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{value}"
    return value
```

### SSRF (CWE-918)

- If any feature requires fetching external URLs (e.g., receipt URLs, webhook callbacks):
  - **Block private IP ranges**: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, 169.254.0.0/16, ::1, fc00::/7
  - **DNS rebinding protection**: Resolve the hostname first, check the IP, then connect
  - **Timeout**: Maximum 5-second timeout on all outbound requests

---

## 5. File Upload Security (Payment Screenshots)

Payment screenshots are the primary input mechanism for transaction parsing. They are also the highest-risk attack surface for file-based exploits.

### Validation Pipeline

```
User Upload → Size Check → Magic Byte Validation → Pillow Re-encode → UUID Rename → AV Scan → S3 Upload
```

### Detailed Controls

| Control | Implementation | Rationale |
|---|---|---|
| Magic byte validation | `python-magic` library | Content-Type headers are trivially spoofed; magic bytes verify actual file format |
| Pillow re-encode | Open with Pillow, save as PNG/JPEG | Destroys polyglot payloads (e.g., GIFAR), strips all metadata including EXIF and GPS data |
| UUID filenames | `uuid.uuid4()` + extension | Prevents path traversal, name collision, and information disclosure from original filenames |
| File size limit (nginx) | `client_max_body_size 10m;` | First line of defense, rejects before hitting application |
| File size limit (FastAPI) | Check `Content-Length` and stream body size | Defense-in-depth; nginx can be misconfigured |
| Image dimensions | Max 4096x4096 pixels | Prevents decompression bombs (zip bombs for images) |
| Private S3 bucket | Block all public access | Files are never directly accessible via S3 URL |
| Pre-signed URLs | 5-minute expiry, GET only | Time-limited access for frontend to display images |
| Response headers | `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` | Prevent browser from executing uploaded files inline |
| Antivirus scanning | ClamAV (production) | Detect known malware patterns; scan before S3 upload |
| Auto-deletion | 90-day TTL via S3 lifecycle policy | Data minimization; screenshots are only needed for initial parsing and dispute resolution |

### Accepted File Types

Only the following MIME types (validated by magic bytes) are accepted:

- `image/jpeg`
- `image/png`
- `image/webp`

---

## 6. API Security

### Rate Limiting

All rate limits are enforced via `fastapi-limiter` with a Redis backend.

| Endpoint | Limit | Window | Key | Rationale |
|---|---|---|---|---|
| `POST /auth/otp/send` | 3 requests | 10 min | Phone number | OTP bombing prevention (SMS cost + user annoyance) |
| `POST /auth/otp/verify` | 5 requests | 15 min | Phone number | Brute force prevention (10^6 combinations) |
| `POST /upload/screenshot` | 10 requests | 1 hour | User ID | Cost control (Claude API calls are expensive) |
| `GET/POST /api/v1/*` (general) | 100 requests | 1 min | User ID | General DoS prevention |
| `POST /api/v1/export` | 5 requests | 1 hour | User ID | Data scraping prevention |

Rate limit responses return `429 Too Many Requests` with `Retry-After` header.

### CORS Configuration

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://expenses.yourdomain.com"],  # NEVER use "*" with credentials
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)
```

- **Never** use wildcard (`*`) origin when `allow_credentials=True`. This is an automatic rejection criterion.
- Allowed origins must be explicitly whitelisted.

### CSRF Protection

- **SameSite=Strict** on the refresh token cookie prevents cross-site request attachment.
- **Custom Header Requirement**: All API requests must include `X-Requested-With: XMLHttpRequest`. Simple cross-origin form submissions cannot set custom headers, providing CSRF protection.
- Combined, these provide robust CSRF defense without traditional CSRF tokens.

### Security Headers Middleware

Every response must include:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data: https://*.amazonaws.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self';
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
```

### Error Handling

- **Never** leak stack traces in API responses. All unhandled exceptions return a generic error message with a correlation ID for internal debugging.
- **SQLAlchemyError**: Catch separately and log at ERROR level with sanitized details. Return generic "database error" to client.
- **Pydantic ValidationError**: Return structured 422 with field-level errors (this is safe as it only reveals schema, not internal state).
- Use structured error responses:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "The requested resource was not found.",
    "correlation_id": "req_abc123def456"
  }
}
```

### Request Size Limits

| Endpoint | Max Body Size |
|---|---|
| General API | 1 MB |
| Upload endpoint | 10 MB |

Enforced at both nginx (`client_max_body_size`) and FastAPI (middleware).

---

## 7. Data Security

### Encryption at Rest

| Data | Method | Details |
|---|---|---|
| PostgreSQL database | `pgcrypto` extension / LUKS volume encryption | Full-disk encryption for the database volume; `pgcrypto` for column-level where needed |
| PII columns (UPI IDs, account numbers) | Fernet symmetric encryption (`cryptography` library) | Application-level encryption before storage; key stored in AWS Secrets Manager |
| S3 objects (screenshots) | SSE-S3 (AES-256) | Server-side encryption enabled on the bucket by default |
| Backups | Encrypted with separate key | Database backups encrypted at rest with a dedicated backup encryption key |

### Encryption in Transit

- **TLS 1.2+** required on all connections (application, database, cache, S3)
- **PostgreSQL**: `sslmode=verify-full` in connection string (verifies server certificate and hostname)
- **Redis**: TLS-enabled Redis (ElastiCache in-transit encryption)
- **Internal services**: All inter-service communication over TLS

### PII Log Sanitization

Implement a custom `SanitizingFormatter` for Python logging:

```python
class SanitizingFormatter(logging.Formatter):
    """Redacts PII patterns from log messages."""

    PII_PATTERNS = [
        (re.compile(r'\b\d{10}\b'), '[REDACTED_PHONE]'),           # Indian phone numbers
        (re.compile(r'\b[\w.-]+@[\w-]+\b'), '[REDACTED_UPI]'),     # UPI IDs (vpa@bank)
        (re.compile(r'\b\d{9,18}\b'), '[REDACTED_ACCOUNT]'),       # Bank account numbers
    ]

    def format(self, record):
        message = super().format(record)
        for pattern, replacement in self.PII_PATTERNS:
            message = pattern.sub(replacement, message)
        return message
```

**Never** log the following in any log level:
- Phone numbers
- UPI IDs / VPAs
- Bank account numbers
- Full names in combination with financial data
- OTP codes
- JWT tokens or refresh tokens

### Data Retention Policy

| Data Type | Retention Period | Deletion Method |
|---|---|---|
| Payment screenshots | 90 days | S3 lifecycle policy auto-delete |
| Transaction records | Account lifetime + 7 years | Cryptographic erasure on account deletion; retained records anonymized |
| Audit logs | 5 years | Immutable storage; purged after 5 years |
| Refresh tokens | 30 days (or until rotation) | Automatic expiry in database |
| OTP codes | 5 minutes | Automatic expiry + explicit invalidation |

### Cryptographic Erasure on Account Deletion

When a user deletes their account:

1. Delete the per-user Fernet encryption key from Secrets Manager
2. PII columns encrypted with that key become permanently unreadable
3. Delete all S3 objects (screenshots) associated with the user
4. Anonymize transaction records required for regulatory retention (remove user_id, replace with hash)
5. Mark audit log entries with anonymized user reference

---

## 8. LLM/AI Security

### Prompt Injection via Screenshots

Payment screenshots are processed by Claude for OCR and data extraction. Attackers could craft screenshots containing text that attempts to manipulate the LLM.

**Mitigations:**

- **Tool-use mode**: Use Claude's tool-use (function calling) mode to enforce structured output. The LLM must return data via a predefined tool schema, not free-form text.
- **Structured output enforcement**: Define a strict Pydantic model for the expected response (amount, date, payee, UPI ID, etc.). Reject any response that doesn't conform.
- **Never return raw LLM response to the frontend**: The LLM response is parsed, validated, and transformed server-side. The frontend only receives the validated structured data.

### Field-Level Validation

Every field extracted by the LLM must be independently validated:

| Field | Validation |
|---|---|
| Amount | Positive number, reasonable range (0.01 to 10,00,000 INR) |
| Date | Valid date, not in the future, not more than 1 year in the past |
| UPI ID | Regex: `^[\w.\-]+@[\w]+$`, length limits |
| Bank/payee name | Whitelist of known Indian banks + free-text with length limit |
| Transaction type | Enum: debit, credit |
| Category | Enum from predefined list |

### Human Confirmation

- **Every LLM-parsed transaction requires explicit user confirmation** before being saved to the database.
- The UI presents the parsed data for review, with the ability to edit any field.
- This is the ultimate defense against LLM hallucination and prompt injection.

### Data Leakage Prevention

- **Send ONLY the image** to the Claude API. Do not include any user context (name, account details, history, preferences) in the prompt.
- The system prompt should be generic and focused on extraction, not personalized.

### Two-Stage OCR Approach (Recommended)

To minimize data sent to external APIs:

1. **Stage 1**: Run Tesseract OCR locally to extract raw text from the screenshot
2. **Stage 2**: Send the extracted text (not the image) to Claude for structured parsing

Benefits:
- Reduces data exposure (text vs. full image)
- Lower API costs (text tokens are cheaper than vision tokens)
- Faster processing
- Can pre-filter obvious non-receipt images locally

Fallback: If Tesseract extraction quality is poor, fall back to sending the image directly to Claude.

### API Key Security

- **Storage**: Claude API key stored in AWS Secrets Manager (never in code, environment variables, or config files)
- **Rotation**: Quarterly key rotation (90-day maximum lifetime)
- **Spending Limits**: Configure spending limits on the Anthropic account dashboard
- **Monitoring**: Alert on unusual API spend (>2x daily average)

### Cost Attack Prevention

An attacker could upload many images to drive up Claude API costs.

| Control | Limit |
|---|---|
| Parse requests per user per day | 50 |
| Pre-validation | Check image is valid (magic bytes, dimensions) before sending to Claude |
| Image size pre-filter | Reject images < 10KB (likely not a real screenshot) or > 10MB |
| Duplicate detection | Hash-based deduplication to prevent re-processing identical images |

---

## 9. Indian Regulatory Compliance

### RBI Data Localization

- **All data must reside in AWS ap-south-1 (Mumbai) region**
- This includes: database, S3 buckets, Redis cache, backups, logs, and any derived data
- No cross-region replication to regions outside India
- CDN (CloudFront) edge caches may serve static assets globally, but user data must not be cached at edge
- **Exception**: Data sent to Anthropic Claude API for processing is transient and not stored by Anthropic (verify Anthropic's data processing terms)

### DPDPA 2023 (Digital Personal Data Protection Act)

| Requirement | Implementation |
|---|---|
| **Specific consent** | Granular consent collection at signup; separate consent for AI processing of screenshots |
| **Purpose limitation** | Data collected only for expense tracking and analysis; consent specifies each purpose |
| **Right to erasure** | `/api/v1/me/delete` endpoint with cryptographic erasure (see Section 7) |
| **Right to correction** | Users can edit all their transaction data and profile information |
| **Right to access** | `/api/v1/me/export` provides complete data export |
| **Breach notification** | Notify DPBI (Data Protection Board of India) and affected users within 72 hours |
| **Data Protection Officer** | Appoint DPO if processing volume exceeds threshold (monitor regulatory guidance) |
| **Children's data** | Service restricted to users 18+; age verification at signup |

### IT Act 2000 - Sections 43A and 72A

- **Section 43A**: Requires "reasonable security practices and procedures" for handling sensitive personal data. This document and its implementation constitute those practices.
- **Section 72A**: Criminalizes disclosure of personal information in breach of lawful contract. Enforce strict access controls for all personnel.

### SPDI Rules 2011 (Sensitive Personal Data or Information)

| Requirement | Implementation |
|---|---|
| **Consent before collection** | Explicit consent screen before any data collection |
| **Privacy policy** | Published and accessible from every screen; available in English and Hindi |
| **Purpose disclosure** | Clear statement of why each data point is collected |
| **Data correction** | Full CRUD on user's own data |
| **Opt-out** | Users can withdraw consent and delete their account at any time |
| **Grievance officer** | Designated contact published in privacy policy |

---

## 10. Audit Logging

### Immutable Audit Log

The `audit_logs` table is **INSERT-only**. No UPDATE or DELETE operations are permitted, even for administrators.

```sql
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id UUID,  -- NULL for system events
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id UUID,
    ip_address INET,
    user_agent TEXT,
    metadata JSONB,  -- Additional context (never PII)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Prevent UPDATE and DELETE
REVOKE UPDATE, DELETE ON audit_logs FROM app_role;

-- Index for common queries
CREATE INDEX idx_audit_logs_user_id ON audit_logs (user_id, timestamp);
CREATE INDEX idx_audit_logs_action ON audit_logs (action, timestamp);
```

### Events to Log

| Category | Events |
|---|---|
| Authentication | Login success, login failure, logout, OTP sent, OTP verified, account lockout, MFA setup, MFA verified |
| Data Access | Transaction list viewed, transaction detail viewed, export requested |
| Data Modification | Transaction created, updated, deleted; category changed; recurring rule created |
| Account | Profile updated, phone changed, email changed, account deletion requested, account deleted |
| File Operations | Screenshot uploaded, screenshot processed, screenshot deleted |
| Security | Rate limit hit, CORS violation, invalid token, suspicious activity detected |

### Audit Log Fields

```json
{
  "timestamp": "2026-03-29T10:15:30.123Z",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "action": "transaction.create",
  "resource_type": "transaction",
  "resource_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "ip_address": "203.0.113.45",
  "user_agent": "Mozilla/5.0 ...",
  "metadata": {
    "source": "screenshot_parse",
    "amount_inr": 1500
  }
}
```

### Retention

- **Minimum 5 years** retention for all audit logs
- Archive to S3 Glacier after 1 year for cost optimization
- Logs remain queryable via Athena for compliance investigations

### PII in Audit Logs

- **Never** log PII in audit log entries
- Use resource IDs (UUIDs) to reference entities, not their content
- `metadata` field must not contain phone numbers, UPI IDs, account numbers, or full names
- IP addresses are retained as they are necessary for security investigations (legal basis: legitimate interest)

---

## 11. Transaction Integrity

### HMAC Checksum

Every transaction record includes an HMAC-SHA256 checksum to detect unauthorized modification (whether by application bug, direct database access, or attacker).

```python
import hmac
import hashlib

def compute_transaction_checksum(transaction: dict, secret_key: bytes) -> str:
    """Compute HMAC-SHA256 over critical transaction fields."""
    message = f"{transaction['id']}|{transaction['user_id']}|{transaction['amount']}|{transaction['date']}|{transaction['type']}"
    return hmac.new(secret_key, message.encode(), hashlib.sha256).hexdigest()
```

- Checksum is computed on INSERT and verified on READ
- Checksum mismatch triggers a security alert and prevents the transaction from being displayed
- HMAC key is stored in AWS Secrets Manager (separate from encryption keys)

### Optimistic Locking

```sql
ALTER TABLE transactions ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
```

- Every UPDATE to a transaction must include `WHERE version = :expected_version`
- On success, increment `version`
- On conflict (version mismatch), return 409 Conflict and require the client to re-fetch
- Prevents lost updates in concurrent modification scenarios

---

## 12. Infrastructure Security

### Docker Hardening

```dockerfile
# Run as non-root user
RUN adduser --disabled-password --gecos '' appuser
USER appuser

# Read-only filesystem
# (configured in docker-compose or orchestrator)
```

```yaml
# docker-compose.yml security settings
services:
  api:
    read_only: true
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
```

- **Non-root user**: Application runs as `appuser`, never as root
- **Read-only filesystem**: Container filesystem is read-only; `/tmp` is a tmpfs mount
- **Drop all capabilities**: `cap_drop: ALL` removes all Linux capabilities
- **No privilege escalation**: `no-new-privileges` prevents setuid binaries
- **Image scanning**: Run Trivy in CI to scan images for known vulnerabilities before deployment

### Network Security

| Resource | Network Placement | Internet Access |
|---|---|---|
| PostgreSQL | Private subnet | No |
| Redis | Private subnet | No |
| Application (FastAPI) | Private subnet behind ALB | Outbound only (for Claude API, MSG91) |
| S3 | VPC endpoint | No public access |

- Database and Redis are only accessible from the application subnet via security groups
- No SSH access to production instances (use SSM Session Manager)

### Secrets Management

| Secret | Storage | Rotation |
|---|---|---|
| Database credentials | AWS Secrets Manager | 90-day automatic rotation |
| Claude API key | AWS Secrets Manager | 90-day manual rotation |
| JWT signing key | AWS Secrets Manager | 90-day rotation (with grace period for old key) |
| Fernet encryption key | AWS Secrets Manager | Annual rotation (re-encrypt on rotation) |
| HMAC signing key | AWS Secrets Manager | Annual rotation |
| MSG91 API key | AWS Secrets Manager | 90-day rotation |

- **Never** store secrets in code, environment variables in Dockerfiles, or config files committed to git
- Use IAM roles for AWS service authentication (no access keys on instances)

### Dependency Security

- **Python**: Run `pip-audit` in CI on every build; fail the build on any HIGH/CRITICAL vulnerability
- **JavaScript**: Run `npm audit` in CI on every build; fail on HIGH/CRITICAL
- **Pin all versions**: Use exact version pins in `requirements.txt` and `package-lock.json` (no ranges)
- **Renovate/Dependabot**: Automated dependency update PRs with security priority

### WAF & DDoS Protection

- **WAF**: Cloudflare WAF with OWASP Core Rule Set (CRS) enabled
- **DDoS**: Cloudflare edge DDoS protection (always-on)
- **Bot Management**: Cloudflare Bot Management to filter automated traffic
- **Rate Limiting at Edge**: Cloudflare rate limiting as first layer before application rate limiting

---

## 13. Privacy & Compliance

### Privacy Policy Requirements

The privacy policy must clearly disclose:

| Item | Details |
|---|---|
| **Data collected** | Phone number, email (optional), transaction data, payment screenshots, device info, IP address |
| **Purpose** | Expense tracking, AI-powered receipt parsing, spending analytics |
| **Third-party sharing** | Anthropic (transient image/text processing, not stored), MSG91 (phone number for OTP delivery) |
| **Storage location** | AWS Mumbai (ap-south-1), India |
| **Retention periods** | Screenshots: 90 days, Transactions: account lifetime + 7 years, Audit logs: 5 years |
| **User rights** | Access, correction, erasure, data portability, withdraw consent |
| **Grievance officer** | Name, email, and address of designated officer |
| **Updates** | Users notified of material changes; continued use after notice constitutes acceptance |

### Data Subject Access Requests (DSAR)

| Endpoint | Purpose | Details |
|---|---|---|
| `GET /api/v1/me/export` | Data portability | Returns all user data as JSON in a ZIP archive; includes transactions, categories, profile, audit log references |
| `DELETE /api/v1/me/delete` | Right to erasure | Initiates account deletion with a **30-day cooling-off period**; user can cancel during this period; after 30 days, cryptographic erasure is performed |

- DSAR requests are rate-limited (5/hour/user) to prevent abuse
- Export includes a manifest file listing all data categories included
- Deletion requires MFA confirmation

### Cookie Consent

- **Strictly necessary cookies** (session, CSRF): No consent required
- **Analytics cookies** (if any): Require explicit opt-in consent via cookie banner
- **No advertising cookies**: This application does not use advertising or tracking cookies

### Third-Party Data Processors

| Processor | Data Shared | Purpose | Data Retention by Processor |
|---|---|---|---|
| Anthropic (Claude API) | Payment screenshot images or extracted text | OCR and transaction parsing | Transient (not retained per Anthropic's API terms; verify contractually) |
| MSG91 | Phone number | OTP SMS delivery | As per MSG91 retention policy (verify contractually) |
| AWS (infrastructure) | All data (encrypted) | Hosting and storage | Under customer control |

- Data Processing Agreements (DPAs) must be signed with all processors
- Verify Anthropic's data handling: ensure API inputs are not used for training and are not persisted

---

## 14. Threat Model (Top 10)

Threats are ordered by **likelihood x impact** score.

| # | Threat | Likelihood | Impact | Risk | Mitigations |
|---|---|---|---|---|---|
| 1 | **IDOR - Accessing other users' transactions** | HIGH | CRITICAL | **CRITICAL** | PostgreSQL RLS (FORCE), UUID public IDs, application-level user_id filter on every query, 404 (not 403), automated isolation tests |
| 2 | **Credential stuffing / brute force** | HIGH | HIGH | **HIGH** | OTP-based auth (no passwords to stuff), rate limiting (3 OTP/10min, 5 verify/15min), CAPTCHA after 3 failures, account lockout after 5, IP-based anomaly detection (V2) |
| 3 | **Stored XSS via LLM output** | MEDIUM | HIGH | **HIGH** | Pydantic validation of all LLM fields, React default escaping, ban `dangerouslySetInnerHTML`, CSP header, treat LLM output as untrusted |
| 4 | **API key exposure (Claude, MSG91)** | MEDIUM | CRITICAL | **HIGH** | AWS Secrets Manager, never in code/env files, git-secrets pre-commit hook, 90-day rotation, spending limits |
| 5 | **SQL injection** | MEDIUM | CRITICAL | **HIGH** | SQLAlchemy ORM only, ban f-strings near queries (auto-reject), parameterized queries for raw SQL, least-privilege DB role |
| 6 | **Cost attack (Claude API abuse)** | MEDIUM | MEDIUM | **MEDIUM** | 50 parses/day/user, 10 uploads/hour, pre-validation (magic bytes, dimensions), spending limits on Anthropic account |
| 7 | **File upload exploits (RCE, XSS via SVG)** | MEDIUM | HIGH | **HIGH** | Magic byte validation, Pillow re-encode, UUID filenames, whitelist JPEG/PNG/WebP only, ClamAV scan, Content-Disposition: attachment |
| 8 | **Prompt injection via screenshots** | LOW-MEDIUM | MEDIUM | **MEDIUM** | Tool-use mode (structured output), field-level validation, human confirmation required, never return raw LLM response |
| 9 | **Insider threat (admin data access)** | LOW | CRITICAL | **MEDIUM** | Admin actions in audit log, separate admin authentication, principle of least privilege, no direct DB access in production |
| 10 | **Supply chain attack (compromised dependency)** | MEDIUM | HIGH | **HIGH** | pip-audit + npm audit in CI, pin all versions, Dependabot/Renovate, review dependency changes in PRs, minimal dependency footprint |

---

## 15. V1 Security Checklist (Non-Negotiable)

These 16 items must be implemented before the first production deployment. No exceptions.

- [ ] **RLS enabled and FORCED** on every user-data table
- [ ] **Application DB role** is not superuser and does not have BYPASSRLS
- [ ] **JWT access tokens** with 15-minute expiry, refresh tokens in httpOnly Secure SameSite=Strict cookies
- [ ] **Token rotation** on every refresh; refresh token reuse detection
- [ ] **Rate limiting** on all endpoints per the table in Section 6
- [ ] **CORS whitelist** - explicit origin, never wildcard with credentials
- [ ] **Security headers** middleware (HSTS, CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy)
- [ ] **Input validation** via Pydantic models on every endpoint
- [ ] **File upload pipeline** - magic bytes, Pillow re-encode, UUID rename, size limits
- [ ] **LLM output validation** - Pydantic model, field-level checks, human confirmation
- [ ] **PII log sanitization** - SanitizingFormatter on all loggers
- [ ] **Audit logging** - INSERT-only table, log auth/access/modification events
- [ ] **TLS everywhere** - database (sslmode=verify-full), Redis, S3, all external APIs
- [ ] **Secrets in AWS Secrets Manager** - no secrets in code or environment variables
- [ ] **pip-audit + npm audit** in CI pipeline, fail on HIGH/CRITICAL
- [ ] **Automated RLS isolation tests** in CI

---

## 16. V1 Should-Have (Within First Month)

These 9 items should be implemented within the first month after launch.

- [ ] **ClamAV scanning** for uploaded files in production
- [ ] **Account lockout** with exponential backoff (upgrade from flat 15-min)
- [ ] **MFA (TOTP)** for high-value operations (export, delete account)
- [ ] **HMAC checksums** on transaction records
- [ ] **Two-stage OCR** (Tesseract local + Claude text parsing)
- [ ] **Duplicate image detection** via perceptual hashing
- [ ] **Cookie consent banner** for analytics cookies
- [ ] **Privacy policy** published in English and Hindi
- [ ] **Data Processing Agreements** signed with Anthropic and MSG91

---

## 17. V2 Items (Within 3 Months)

These 7 items are planned for the second major release.

- [ ] **IP-based anomaly detection** - flag logins from unusual locations
- [ ] **Device fingerprinting** - track known devices, challenge unknown ones
- [ ] **Refresh token binding** to device fingerprint
- [ ] **Automated penetration testing** - scheduled DAST scans (OWASP ZAP)
- [ ] **Bug bounty program** - responsible disclosure policy and rewards
- [ ] **SOC 2 Type II preparation** - if pursuing enterprise/B2B partnerships
- [ ] **Cryptographic erasure automation** - fully automated account deletion pipeline with verification

---

## Appendix A: Security Libraries & Tools

| Tool | Purpose | Stage |
|---|---|---|
| `python-jose` | JWT handling | Runtime |
| `passlib[bcrypt]` | Password/hash utilities | Runtime |
| `pyotp` | TOTP for MFA | Runtime |
| `fastapi-limiter` | Rate limiting | Runtime |
| `python-magic` | File type detection | Runtime |
| `Pillow` | Image processing & re-encoding | Runtime |
| `cryptography` (Fernet) | PII column encryption | Runtime |
| `pip-audit` | Python dependency vulnerability scanning | CI |
| `npm audit` | JavaScript dependency vulnerability scanning | CI |
| `Trivy` | Docker image vulnerability scanning | CI |
| `ClamAV` | Antivirus file scanning | Production |
| `git-secrets` | Prevent secret commits | Pre-commit |
| `OWASP ZAP` | Dynamic application security testing | V2 |

## Appendix B: Incident Response Summary

1. **Detection**: Automated alerts from audit logs, WAF, and rate limiting
2. **Triage**: On-call engineer assesses severity (P1-P4)
3. **Containment**: Isolate affected systems; revoke compromised credentials
4. **Notification**: DPBI and affected users within 72 hours (DPDPA requirement)
5. **Remediation**: Fix root cause, deploy patch
6. **Post-mortem**: Blameless post-mortem within 5 business days; update this security document

## Appendix C: Security Review Cadence

| Activity | Frequency |
|---|---|
| Dependency audit (pip-audit, npm audit) | Every CI build |
| Secret rotation | 90 days |
| Security architecture review | Quarterly |
| Penetration test (external) | Annually (V2+) |
| RLS isolation test suite | Every CI build |
| Audit log review | Monthly |
| Privacy policy review | Annually or on material changes |
