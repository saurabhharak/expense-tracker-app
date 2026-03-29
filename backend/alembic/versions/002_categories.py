"""Create categories table with RLS

Revision ID: 002
Revises: 001
Create Date: 2026-03-29
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("CREATE TYPE expense_tracker.category_type AS ENUM ('income', 'expense')")

    op.execute("""
    CREATE TABLE expense_tracker.categories (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id         UUID REFERENCES expense_tracker.users(id) ON DELETE CASCADE,
        parent_id       UUID REFERENCES expense_tracker.categories(id) ON DELETE CASCADE,
        name            VARCHAR(100) NOT NULL,
        type            expense_tracker.category_type NOT NULL,
        icon            VARCHAR(50),
        color           VARCHAR(7),
        is_system       BOOLEAN NOT NULL DEFAULT false,
        sort_order      INTEGER NOT NULL DEFAULT 0,
        is_active       BOOLEAN NOT NULL DEFAULT true,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("""
    CREATE UNIQUE INDEX idx_categories_unique_name
        ON expense_tracker.categories (
            COALESCE(user_id, '00000000-0000-0000-0000-000000000000'),
            COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'),
            type, lower(name)
        )
    """)

    op.execute("CREATE INDEX idx_categories_user_id ON expense_tracker.categories (user_id)")
    op.execute("CREATE INDEX idx_categories_parent_id ON expense_tracker.categories (parent_id)")

    op.execute("ALTER TABLE expense_tracker.categories ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE expense_tracker.categories FORCE ROW LEVEL SECURITY")

    op.execute("""
    CREATE POLICY categories_select ON expense_tracker.categories FOR SELECT TO app_user
        USING (user_id IS NULL OR user_id = expense_tracker.current_app_user_id())
    """)
    op.execute("""
    CREATE POLICY categories_insert ON expense_tracker.categories FOR INSERT TO app_user
        WITH CHECK (user_id = expense_tracker.current_app_user_id())
    """)
    op.execute("""
    CREATE POLICY categories_update ON expense_tracker.categories FOR UPDATE TO app_user
        USING (user_id = expense_tracker.current_app_user_id() AND is_system = false)
    """)
    op.execute("""
    CREATE POLICY categories_delete ON expense_tracker.categories FOR DELETE TO app_user
        USING (user_id = expense_tracker.current_app_user_id() AND is_system = false)
    """)

    op.execute("""
    CREATE TRIGGER trg_categories_updated_at
        BEFORE UPDATE ON expense_tracker.categories
        FOR EACH ROW EXECUTE FUNCTION expense_tracker.update_updated_at()
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS expense_tracker.categories CASCADE")
    op.execute("DROP TYPE IF EXISTS expense_tracker.category_type")
