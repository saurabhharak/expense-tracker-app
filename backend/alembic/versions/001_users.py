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
    CREATE OR REPLACE FUNCTION expense_tracker.update_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = now();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """)

    op.execute("""
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
    )
    """)

    op.execute("""
    ALTER TABLE expense_tracker.users ADD CONSTRAINT chk_auth_method
        CHECK (email IS NOT NULL OR phone IS NOT NULL OR google_id IS NOT NULL)
    """)

    op.execute("CREATE INDEX idx_users_email ON expense_tracker.users (email) WHERE email IS NOT NULL")
    op.execute("CREATE INDEX idx_users_phone ON expense_tracker.users (phone) WHERE phone IS NOT NULL")
    op.execute("CREATE INDEX idx_users_google_id ON expense_tracker.users (google_id) WHERE google_id IS NOT NULL")

    op.execute("""
    CREATE TRIGGER trg_users_updated_at
        BEFORE UPDATE ON expense_tracker.users
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at()
    """)

    op.execute("""
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
    )
    """)

    op.execute("CREATE INDEX idx_refresh_tokens_user_id ON expense_tracker.refresh_tokens (user_id)")
    op.execute("CREATE INDEX idx_refresh_tokens_token_hash ON expense_tracker.refresh_tokens (token_hash) WHERE revoked_at IS NULL")
    op.execute("CREATE INDEX idx_refresh_tokens_expires ON expense_tracker.refresh_tokens (expires_at) WHERE revoked_at IS NULL")

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS expense_tracker.refresh_tokens CASCADE")
    op.execute("DROP TABLE IF EXISTS expense_tracker.users CASCADE")
    op.execute("DROP FUNCTION IF EXISTS expense_tracker.update_updated_at()")
