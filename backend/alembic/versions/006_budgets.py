"""Create budgets table with FY functions and RLS

Revision ID: 006
Revises: 005
Create Date: 2026-03-29
"""
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TYPE expense_tracker.budget_period AS ENUM ('monthly', 'quarterly', 'yearly');

    CREATE TABLE expense_tracker.budgets (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        category_id     UUID REFERENCES expense_tracker.categories(id) ON DELETE CASCADE,
        amount          DECIMAL(12,2) NOT NULL CHECK (amount > 0),
        period          expense_tracker.budget_period NOT NULL DEFAULT 'monthly',
        fy_year         SMALLINT NOT NULL,
        alert_threshold SMALLINT NOT NULL DEFAULT 80 CHECK (alert_threshold BETWEEN 1 AND 100),
        alert_sent      BOOLEAN NOT NULL DEFAULT false,
        is_active       BOOLEAN NOT NULL DEFAULT true,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE UNIQUE INDEX idx_budgets_unique
        ON expense_tracker.budgets (user_id, COALESCE(category_id, '00000000-0000-0000-0000-000000000000'), fy_year)
        WHERE is_active = true;
    CREATE INDEX idx_budgets_user_fy ON expense_tracker.budgets (user_id, fy_year);

    ALTER TABLE expense_tracker.budgets ENABLE ROW LEVEL SECURITY;
    ALTER TABLE expense_tracker.budgets FORCE ROW LEVEL SECURITY;

    CREATE POLICY budgets_all ON expense_tracker.budgets FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id());

    CREATE TRIGGER trg_budgets_updated_at
        BEFORE UPDATE ON expense_tracker.budgets
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at();

    -- FY helper functions
    CREATE OR REPLACE FUNCTION expense_tracker.get_fy_year(d DATE)
    RETURNS SMALLINT AS $$
    BEGIN
        IF EXTRACT(MONTH FROM d) >= 4 THEN
            RETURN EXTRACT(YEAR FROM d)::SMALLINT;
        ELSE
            RETURN (EXTRACT(YEAR FROM d) - 1)::SMALLINT;
        END IF;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;

    CREATE OR REPLACE FUNCTION expense_tracker.get_fy_range(fy SMALLINT)
    RETURNS TABLE(fy_start DATE, fy_end DATE) AS $$
    BEGIN
        RETURN QUERY SELECT make_date(fy, 4, 1), make_date(fy + 1, 3, 31);
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;

    GRANT EXECUTE ON FUNCTION expense_tracker.get_fy_year(DATE) TO app_user;
    GRANT EXECUTE ON FUNCTION expense_tracker.get_fy_range(SMALLINT) TO app_user;
    """)

def downgrade() -> None:
    op.execute("""
    DROP FUNCTION IF EXISTS expense_tracker.get_fy_range(SMALLINT);
    DROP FUNCTION IF EXISTS expense_tracker.get_fy_year(DATE);
    DROP TABLE IF EXISTS expense_tracker.budgets CASCADE;
    DROP TYPE IF EXISTS expense_tracker.budget_period;
    """)
