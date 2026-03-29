"""Create transactions table with balance trigger and RLS

Revision ID: 004
Revises: 003
Create Date: 2026-03-29
"""
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TYPE expense_tracker.transaction_type AS ENUM ('income', 'expense', 'transfer');

    CREATE TABLE expense_tracker.transactions (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        account_id      UUID NOT NULL REFERENCES expense_tracker.accounts(id) ON DELETE RESTRICT,
        category_id     UUID REFERENCES expense_tracker.categories(id) ON DELETE SET NULL,
        type            expense_tracker.transaction_type NOT NULL,
        amount          DECIMAL(12,2) NOT NULL CHECK (amount > 0),
        to_account_id   UUID REFERENCES expense_tracker.accounts(id) ON DELETE RESTRICT,
        description     VARCHAR(500),
        notes           TEXT,
        tags            TEXT[] DEFAULT '{}',
        transaction_date TIMESTAMPTZ NOT NULL DEFAULT now(),
        -- FK columns without constraints (referenced tables don't exist yet)
        screenshot_parse_log_id UUID,
        recurring_transaction_id UUID,
        is_deleted      BOOLEAN NOT NULL DEFAULT false,
        deleted_at      TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    -- Indexes
    CREATE INDEX idx_txn_user_date ON expense_tracker.transactions
        (user_id, transaction_date DESC, id DESC) WHERE is_deleted = false;
    CREATE INDEX idx_txn_user_account ON expense_tracker.transactions
        (user_id, account_id, transaction_date DESC) WHERE is_deleted = false;
    CREATE INDEX idx_txn_user_category ON expense_tracker.transactions
        (user_id, category_id, transaction_date DESC) WHERE is_deleted = false;
    CREATE INDEX idx_txn_user_type ON expense_tracker.transactions
        (user_id, type, transaction_date DESC) WHERE is_deleted = false;
    CREATE INDEX idx_txn_user_type_date ON expense_tracker.transactions
        (user_id, type, transaction_date) WHERE is_deleted = false;
    CREATE INDEX idx_txn_tags ON expense_tracker.transactions
        USING GIN (tags) WHERE is_deleted = false;

    -- RLS
    ALTER TABLE expense_tracker.transactions ENABLE ROW LEVEL SECURITY;
    ALTER TABLE expense_tracker.transactions FORCE ROW LEVEL SECURITY;

    CREATE POLICY transactions_all ON expense_tracker.transactions FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id());

    CREATE TRIGGER trg_transactions_updated_at
        BEFORE UPDATE ON expense_tracker.transactions
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at();

    -- Balance trigger (incremental account balance updates)
    CREATE OR REPLACE FUNCTION expense_tracker.update_account_balance()
    RETURNS TRIGGER
    SECURITY DEFINER
    SET search_path = expense_tracker
    AS $$
    DECLARE
        v_delta DECIMAL(14,2);
    BEGIN
        IF TG_OP = 'DELETE' THEN
            IF OLD.is_deleted = false THEN
                v_delta := CASE
                    WHEN OLD.type = 'income'   THEN -OLD.amount
                    WHEN OLD.type = 'expense'  THEN  OLD.amount
                    WHEN OLD.type = 'transfer' THEN  OLD.amount
                    ELSE 0
                END;
                UPDATE expense_tracker.accounts SET balance = balance + v_delta WHERE id = OLD.account_id;
                IF OLD.type = 'transfer' AND OLD.to_account_id IS NOT NULL THEN
                    UPDATE expense_tracker.accounts SET balance = balance - OLD.amount WHERE id = OLD.to_account_id;
                END IF;
            END IF;
            RETURN OLD;
        END IF;

        IF TG_OP = 'INSERT' THEN
            IF NEW.is_deleted = false THEN
                v_delta := CASE
                    WHEN NEW.type = 'income'   THEN  NEW.amount
                    WHEN NEW.type = 'expense'  THEN -NEW.amount
                    WHEN NEW.type = 'transfer' THEN -NEW.amount
                    ELSE 0
                END;
                UPDATE expense_tracker.accounts SET balance = balance + v_delta WHERE id = NEW.account_id;
                IF NEW.type = 'transfer' AND NEW.to_account_id IS NOT NULL THEN
                    UPDATE expense_tracker.accounts SET balance = balance + NEW.amount WHERE id = NEW.to_account_id;
                END IF;
            END IF;
            RETURN NEW;
        END IF;

        IF TG_OP = 'UPDATE' THEN
            IF OLD.is_deleted = false THEN
                v_delta := CASE
                    WHEN OLD.type = 'income'   THEN -OLD.amount
                    WHEN OLD.type = 'expense'  THEN  OLD.amount
                    WHEN OLD.type = 'transfer' THEN  OLD.amount
                    ELSE 0
                END;
                UPDATE expense_tracker.accounts SET balance = balance + v_delta WHERE id = OLD.account_id;
                IF OLD.type = 'transfer' AND OLD.to_account_id IS NOT NULL THEN
                    UPDATE expense_tracker.accounts SET balance = balance - OLD.amount WHERE id = OLD.to_account_id;
                END IF;
            END IF;
            IF NEW.is_deleted = false THEN
                v_delta := CASE
                    WHEN NEW.type = 'income'   THEN  NEW.amount
                    WHEN NEW.type = 'expense'  THEN -NEW.amount
                    WHEN NEW.type = 'transfer' THEN -NEW.amount
                    ELSE 0
                END;
                UPDATE expense_tracker.accounts SET balance = balance + v_delta WHERE id = NEW.account_id;
                IF NEW.type = 'transfer' AND NEW.to_account_id IS NOT NULL THEN
                    UPDATE expense_tracker.accounts SET balance = balance + NEW.amount WHERE id = NEW.to_account_id;
                END IF;
            END IF;
            RETURN NEW;
        END IF;

        RETURN COALESCE(NEW, OLD);
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER trg_update_account_balance
        AFTER INSERT OR UPDATE OR DELETE ON expense_tracker.transactions
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_account_balance();
    """)

def downgrade() -> None:
    op.execute("""
    DROP TRIGGER IF EXISTS trg_update_account_balance ON expense_tracker.transactions;
    DROP FUNCTION IF EXISTS expense_tracker.update_account_balance();
    DROP TABLE IF EXISTS expense_tracker.transactions CASCADE;
    DROP TYPE IF EXISTS expense_tracker.transaction_type;
    """)
