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
    )
    """)

    op.execute("""
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
    )
    """)

    op.execute("CREATE INDEX idx_parse_logs_user ON expense_tracker.screenshot_parse_logs (user_id, created_at DESC)")
    op.execute("""
    CREATE INDEX idx_parse_logs_status ON expense_tracker.screenshot_parse_logs (status)
        WHERE status IN ('uploaded', 'processing')
    """)

    op.execute("ALTER TABLE expense_tracker.screenshot_parse_logs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE expense_tracker.screenshot_parse_logs FORCE ROW LEVEL SECURITY")

    op.execute("""
    CREATE POLICY parse_logs_all ON expense_tracker.screenshot_parse_logs FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id())
    """)

    op.execute("""
    CREATE TRIGGER trg_parse_logs_updated_at
        BEFORE UPDATE ON expense_tracker.screenshot_parse_logs
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at()
    """)

    op.execute("""
    ALTER TABLE expense_tracker.transactions
        ADD CONSTRAINT fk_txn_screenshot
        FOREIGN KEY (screenshot_parse_log_id) REFERENCES expense_tracker.screenshot_parse_logs(id) ON DELETE SET NULL
    """)

    op.execute("""
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
    )
    """)

    op.execute("CREATE UNIQUE INDEX idx_api_usage_user_date ON expense_tracker.api_usage (user_id, date)")

    op.execute("ALTER TABLE expense_tracker.api_usage ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE expense_tracker.api_usage FORCE ROW LEVEL SECURITY")

    op.execute("""
    CREATE POLICY api_usage_select ON expense_tracker.api_usage FOR SELECT TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
    """)
    op.execute("""
    CREATE POLICY api_usage_insert ON expense_tracker.api_usage FOR INSERT TO app_user
        WITH CHECK (user_id = expense_tracker.current_app_user_id())
    """)

    op.execute("""
    CREATE TRIGGER trg_api_usage_updated_at
        BEFORE UPDATE ON expense_tracker.api_usage
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at()
    """)

def downgrade() -> None:
    op.execute("ALTER TABLE expense_tracker.transactions DROP CONSTRAINT IF EXISTS fk_txn_screenshot")
    op.execute("DROP TABLE IF EXISTS expense_tracker.api_usage CASCADE")
    op.execute("DROP TABLE IF EXISTS expense_tracker.screenshot_parse_logs CASCADE")
    op.execute("DROP TYPE IF EXISTS expense_tracker.parse_status")
