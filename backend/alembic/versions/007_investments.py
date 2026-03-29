"""Create investment tables with RLS

Revision ID: 007
Revises: 006
Create Date: 2026-03-29
"""
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TYPE expense_tracker.investment_type AS ENUM (
        'equity', 'mutual_fund', 'etf', 'fd', 'rd', 'ppf', 'nps', 'bond', 'gold'
    )
    """)

    op.execute("""
    CREATE TABLE expense_tracker.investment_holdings (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        type            expense_tracker.investment_type NOT NULL,
        name            VARCHAR(255) NOT NULL,
        symbol          VARCHAR(50),
        quantity        DECIMAL(14,4) NOT NULL DEFAULT 0,
        avg_buy_price   DECIMAL(14,4) NOT NULL DEFAULT 0,
        current_price   DECIMAL(14,4),
        current_value   DECIMAL(14,2) GENERATED ALWAYS AS (quantity * COALESCE(current_price, avg_buy_price)) STORED,
        invested_amount DECIMAL(14,2),
        maturity_amount DECIMAL(14,2),
        interest_rate   DECIMAL(5,2),
        maturity_date   DATE,
        broker          VARCHAR(100),
        demat_account   VARCHAR(50),
        notes           TEXT,
        price_updated_at TIMESTAMPTZ,
        is_active       BOOLEAN NOT NULL DEFAULT true,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("CREATE INDEX idx_holdings_user ON expense_tracker.investment_holdings (user_id)")
    op.execute("CREATE INDEX idx_holdings_user_type ON expense_tracker.investment_holdings (user_id, type)")
    op.execute("CREATE INDEX idx_holdings_symbol ON expense_tracker.investment_holdings (symbol) WHERE symbol IS NOT NULL")

    op.execute("ALTER TABLE expense_tracker.investment_holdings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE expense_tracker.investment_holdings FORCE ROW LEVEL SECURITY")

    op.execute("""
    CREATE POLICY holdings_all ON expense_tracker.investment_holdings FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id())
    """)

    op.execute("""
    CREATE TRIGGER trg_holdings_updated_at
        BEFORE UPDATE ON expense_tracker.investment_holdings
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at()
    """)

    op.execute("""
    CREATE TYPE expense_tracker.investment_txn_type AS ENUM (
        'buy', 'sell', 'dividend', 'interest', 'split', 'bonus', 'sip'
    )
    """)

    op.execute("""
    CREATE TABLE expense_tracker.investment_transactions (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        holding_id      UUID NOT NULL REFERENCES expense_tracker.investment_holdings(id) ON DELETE CASCADE,
        type            expense_tracker.investment_txn_type NOT NULL,
        quantity        DECIMAL(14,4),
        price_per_unit  DECIMAL(14,4),
        amount          DECIMAL(14,2) NOT NULL,
        ratio_from      SMALLINT,
        ratio_to        SMALLINT,
        brokerage       DECIMAL(10,2) DEFAULT 0,
        stt             DECIMAL(10,2) DEFAULT 0,
        gst             DECIMAL(10,2) DEFAULT 0,
        stamp_duty      DECIMAL(10,2) DEFAULT 0,
        other_charges   DECIMAL(10,2) DEFAULT 0,
        transaction_date DATE NOT NULL,
        settlement_date  DATE,
        notes           TEXT,
        is_deleted      BOOLEAN NOT NULL DEFAULT false,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("CREATE INDEX idx_inv_txn_user ON expense_tracker.investment_transactions (user_id)")
    op.execute("CREATE INDEX idx_inv_txn_holding ON expense_tracker.investment_transactions (holding_id, transaction_date DESC)")
    op.execute("""
    CREATE INDEX idx_inv_txn_user_date ON expense_tracker.investment_transactions (user_id, transaction_date DESC)
        WHERE is_deleted = false
    """)

    op.execute("ALTER TABLE expense_tracker.investment_transactions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE expense_tracker.investment_transactions FORCE ROW LEVEL SECURITY")

    op.execute("""
    CREATE POLICY inv_txn_all ON expense_tracker.investment_transactions FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id())
    """)

    op.execute("""
    CREATE TRIGGER trg_inv_txn_updated_at
        BEFORE UPDATE ON expense_tracker.investment_transactions
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at()
    """)

    op.execute("""
    CREATE TYPE expense_tracker.coupon_frequency AS ENUM ('monthly', 'quarterly', 'semi_annual', 'annual', 'zero_coupon')
    """)

    op.execute("""
    CREATE TYPE expense_tracker.credit_rating AS ENUM (
        'AAA', 'AA+', 'AA', 'AA-', 'A+', 'A', 'A-',
        'BBB+', 'BBB', 'BBB-', 'BB+', 'BB', 'BB-', 'B+', 'B', 'B-',
        'C', 'D', 'unrated', 'sovereign'
    )
    """)

    op.execute("""
    CREATE TABLE expense_tracker.bond_details (
        id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        holding_id          UUID NOT NULL UNIQUE REFERENCES expense_tracker.investment_holdings(id) ON DELETE CASCADE,
        user_id             UUID NOT NULL REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        isin                VARCHAR(12),
        face_value          DECIMAL(12,2) NOT NULL DEFAULT 1000,
        coupon_rate         DECIMAL(5,2),
        coupon_frequency    expense_tracker.coupon_frequency NOT NULL DEFAULT 'semi_annual',
        issue_date          DATE,
        maturity_date       DATE NOT NULL,
        next_coupon_date    DATE,
        credit_rating       expense_tracker.credit_rating DEFAULT 'unrated',
        rating_agency       VARCHAR(50),
        issuer_name         VARCHAR(255),
        is_tax_free         BOOLEAN NOT NULL DEFAULT false,
        is_callable         BOOLEAN NOT NULL DEFAULT false,
        call_date           DATE,
        ytm                 DECIMAL(5,2),
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("CREATE INDEX idx_bond_details_holding ON expense_tracker.bond_details (holding_id)")

    op.execute("ALTER TABLE expense_tracker.bond_details ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE expense_tracker.bond_details FORCE ROW LEVEL SECURITY")

    op.execute("""
    CREATE POLICY bond_details_all ON expense_tracker.bond_details FOR ALL TO app_user
        USING (user_id = expense_tracker.current_app_user_id())
        WITH CHECK (user_id = expense_tracker.current_app_user_id())
    """)

    op.execute("""
    CREATE TRIGGER trg_bond_details_updated_at
        BEFORE UPDATE ON expense_tracker.bond_details
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at()
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS expense_tracker.bond_details CASCADE")
    op.execute("DROP TABLE IF EXISTS expense_tracker.investment_transactions CASCADE")
    op.execute("DROP TABLE IF EXISTS expense_tracker.investment_holdings CASCADE")
    op.execute("DROP TYPE IF EXISTS expense_tracker.credit_rating")
    op.execute("DROP TYPE IF EXISTS expense_tracker.coupon_frequency")
    op.execute("DROP TYPE IF EXISTS expense_tracker.investment_txn_type")
    op.execute("DROP TYPE IF EXISTS expense_tracker.investment_type")
