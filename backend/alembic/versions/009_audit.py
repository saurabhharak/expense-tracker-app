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
    )
    """)

    op.execute("CREATE INDEX idx_audit_user_date ON expense_tracker.audit_logs (user_id, created_at DESC)")
    op.execute("CREATE INDEX idx_audit_entity ON expense_tracker.audit_logs (entity_type, entity_id)")

    op.execute("ALTER TABLE expense_tracker.audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE expense_tracker.audit_logs FORCE ROW LEVEL SECURITY")

    op.execute("""
    CREATE POLICY audit_logs_select ON expense_tracker.audit_logs FOR SELECT TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
    """)
    op.execute("""
    CREATE POLICY audit_logs_insert ON expense_tracker.audit_logs FOR INSERT TO app_user
        WITH CHECK (user_id = expense_tracker.current_app_user_id())
    """)

    op.execute("REVOKE UPDATE, DELETE ON expense_tracker.audit_logs FROM app_user")

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS expense_tracker.audit_logs CASCADE")
