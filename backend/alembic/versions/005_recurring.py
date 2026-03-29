"""Create recurring_transactions table with RLS

Revision ID: 005
Revises: 004
Create Date: 2026-03-29
"""
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TYPE expense_tracker.recurrence_frequency AS ENUM (
        'daily', 'weekly', 'biweekly', 'monthly', 'quarterly', 'yearly'
    );

    CREATE TABLE expense_tracker.recurring_transactions (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        account_id      UUID NOT NULL REFERENCES expense_tracker.accounts(id) ON DELETE RESTRICT,
        category_id     UUID REFERENCES expense_tracker.categories(id) ON DELETE SET NULL,
        type            expense_tracker.transaction_type NOT NULL,
        amount          DECIMAL(12,2) NOT NULL CHECK (amount > 0),
        description     VARCHAR(500),
        tags            TEXT[] DEFAULT '{}',
        frequency       expense_tracker.recurrence_frequency NOT NULL,
        schedule_day    SMALLINT,
        start_date      DATE NOT NULL,
        end_date        DATE,
        next_due_date   DATE NOT NULL,
        last_generated  TIMESTAMPTZ,
        is_active       BOOLEAN NOT NULL DEFAULT true,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX idx_recurring_user ON expense_tracker.recurring_transactions (user_id);
    CREATE INDEX idx_recurring_next_due ON expense_tracker.recurring_transactions (next_due_date)
        WHERE is_active = true;

    ALTER TABLE expense_tracker.recurring_transactions ENABLE ROW LEVEL SECURITY;
    ALTER TABLE expense_tracker.recurring_transactions FORCE ROW LEVEL SECURITY;

    CREATE POLICY recurring_all ON expense_tracker.recurring_transactions FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id());

    CREATE TRIGGER trg_recurring_updated_at
        BEFORE UPDATE ON expense_tracker.recurring_transactions
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at();

    -- Add deferred FK from transactions to recurring_transactions
    ALTER TABLE expense_tracker.transactions
        ADD CONSTRAINT fk_txn_recurring
        FOREIGN KEY (recurring_transaction_id) REFERENCES expense_tracker.recurring_transactions(id) ON DELETE SET NULL;
    """)

def downgrade() -> None:
    op.execute("""
    ALTER TABLE expense_tracker.transactions DROP CONSTRAINT IF EXISTS fk_txn_recurring;
    DROP TABLE IF EXISTS expense_tracker.recurring_transactions CASCADE;
    DROP TYPE IF EXISTS expense_tracker.recurrence_frequency;
    """)
