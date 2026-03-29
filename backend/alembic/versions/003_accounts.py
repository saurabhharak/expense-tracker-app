"""Create accounts table with RLS

Revision ID: 003
Revises: 002
Create Date: 2026-03-29
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TYPE expense_tracker.account_type AS ENUM (
        'savings', 'current', 'credit_card', 'wallet', 'cash', 'loan'
    );

    CREATE TABLE expense_tracker.accounts (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        name            VARCHAR(100) NOT NULL,
        type            expense_tracker.account_type NOT NULL,
        bank_name       VARCHAR(100),
        balance         DECIMAL(14,2) NOT NULL DEFAULT 0,
        credit_limit    DECIMAL(14,2),
        billing_day     SMALLINT CHECK (billing_day BETWEEN 1 AND 31),
        icon            VARCHAR(50),
        color           VARCHAR(7),
        is_active       BOOLEAN NOT NULL DEFAULT true,
        is_default      BOOLEAN NOT NULL DEFAULT false,
        sort_order      INTEGER NOT NULL DEFAULT 0,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX idx_accounts_user_id ON expense_tracker.accounts (user_id);
    CREATE UNIQUE INDEX idx_accounts_default
        ON expense_tracker.accounts (user_id) WHERE is_default = true AND is_active = true;

    ALTER TABLE expense_tracker.accounts ENABLE ROW LEVEL SECURITY;
    ALTER TABLE expense_tracker.accounts FORCE ROW LEVEL SECURITY;

    CREATE POLICY accounts_all ON expense_tracker.accounts FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id());

    CREATE TRIGGER trg_accounts_updated_at
        BEFORE UPDATE ON expense_tracker.accounts
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at();
    """)

def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS expense_tracker.accounts CASCADE;
    DROP TYPE IF EXISTS expense_tracker.account_type;
    """)
