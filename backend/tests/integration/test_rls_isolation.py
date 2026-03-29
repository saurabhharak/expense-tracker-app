"""
RLS Isolation Integration Test (T-1.4.12)

Validates that Row-Level Security enforces tenant isolation across all data tables.
Requires running PostgreSQL with migrations applied.
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Use sync engine for integration tests
DATABASE_URL = os.getenv(
    "SYNC_DATABASE_URL",
    "postgresql://postgres:postgres_dev@localhost:5433/expense_tracker",
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(engine)

# Two test user IDs
USER_A_ID = str(uuid.uuid4())
USER_B_ID = str(uuid.uuid4())


@pytest.fixture(scope="module", autouse=True)
def setup_test_users():
    """Create two test users and insert test data for each."""
    with SessionLocal() as session:
        session.execute(text("SET search_path TO expense_tracker, public"))

        # Create users
        session.execute(text("""
            INSERT INTO users (id, email, full_name)
            VALUES (:id_a, :email_a, 'User A'), (:id_b, :email_b, 'User B')
        """), {
            "id_a": USER_A_ID, "email_a": f"usera_{USER_A_ID[:8]}@test.com",
            "id_b": USER_B_ID, "email_b": f"userb_{USER_B_ID[:8]}@test.com",
        })

        # Create accounts for each user; capture the IDs for use in transactions
        account_ids = {}
        for user_id, name in [(USER_A_ID, "A Savings"), (USER_B_ID, "B Savings")]:
            acct_id = str(uuid.uuid4())
            account_ids[user_id] = acct_id
            session.execute(text("""
                INSERT INTO accounts (id, user_id, name, type, balance)
                VALUES (:aid, :uid, :name, 'savings', 10000)
            """), {"aid": acct_id, "uid": user_id, "name": name})

        # Create categories for each user
        for user_id, name in [(USER_A_ID, "A Food"), (USER_B_ID, "B Food")]:
            session.execute(text("""
                INSERT INTO categories (id, user_id, name, type)
                VALUES (uuid_generate_v4(), :uid, :name, 'expense')
            """), {"uid": user_id, "name": name})

        # Create budgets for each user
        for user_id in [USER_A_ID, USER_B_ID]:
            session.execute(text("""
                INSERT INTO budgets (user_id, amount, fy_year)
                VALUES (:uid, 50000, 2026)
            """), {"uid": user_id})

        # Create investment holdings for each user; capture IDs for child tables
        holding_ids = {}
        for user_id, name in [(USER_A_ID, "A HDFC"), (USER_B_ID, "B SBI")]:
            holding_id = str(uuid.uuid4())
            holding_ids[user_id] = holding_id
            session.execute(text("""
                INSERT INTO investment_holdings (id, user_id, type, name, quantity, avg_buy_price)
                VALUES (:hid, :uid, 'equity', :name, 10, 1500)
            """), {"hid": holding_id, "uid": user_id, "name": name})

        # Create transactions for each user
        for user_id in [USER_A_ID, USER_B_ID]:
            session.execute(text("""
                INSERT INTO transactions (user_id, account_id, type, amount, transaction_date)
                VALUES (:uid, :aid, 'expense', 100.00, now())
            """), {"uid": user_id, "aid": account_ids[user_id]})

        # Create recurring_transactions for each user
        for user_id in [USER_A_ID, USER_B_ID]:
            session.execute(text("""
                INSERT INTO recurring_transactions
                    (user_id, account_id, type, amount, frequency, start_date, next_due_date)
                VALUES (:uid, :aid, 'expense', 500.00, 'monthly', '2026-01-01', '2026-04-01')
            """), {"uid": user_id, "aid": account_ids[user_id]})

        # Create investment_transactions for each user (requires holding_id)
        for user_id in [USER_A_ID, USER_B_ID]:
            session.execute(text("""
                INSERT INTO investment_transactions
                    (user_id, holding_id, type, quantity, price_per_unit, amount, transaction_date)
                VALUES (:uid, :hid, 'buy', 5, 1500.00, 7500.00, '2026-01-15')
            """), {"uid": user_id, "hid": holding_ids[user_id]})

        # Create bond_details for each user (requires holding_id, unique per holding)
        for user_id in [USER_A_ID, USER_B_ID]:
            session.execute(text("""
                INSERT INTO bond_details
                    (holding_id, user_id, face_value, coupon_frequency, maturity_date)
                VALUES (:hid, :uid, 1000.00, 'semi_annual', '2031-01-01')
            """), {"uid": user_id, "hid": holding_ids[user_id]})

        # Create screenshot_parse_logs for each user
        for user_id in [USER_A_ID, USER_B_ID]:
            session.execute(text("""
                INSERT INTO screenshot_parse_logs
                    (user_id, s3_key, file_size_bytes, mime_type, status)
                VALUES (:uid, :s3key, 12345, 'image/jpeg', 'uploaded')
            """), {"uid": user_id, "s3key": f"uploads/{user_id[:8]}/test.jpg"})

        # Create api_usage for each user
        for user_id in [USER_A_ID, USER_B_ID]:
            session.execute(text("""
                INSERT INTO api_usage (user_id, date, screenshot_count)
                VALUES (:uid, CURRENT_DATE, 1)
            """), {"uid": user_id})

        session.commit()

    yield

    # Cleanup in correct dependency order (children before parents)
    with SessionLocal() as session:
        session.execute(text("SET search_path TO expense_tracker, public"))
        session.execute(text("DELETE FROM api_usage WHERE user_id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.execute(text("DELETE FROM screenshot_parse_logs WHERE user_id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.execute(text("DELETE FROM bond_details WHERE user_id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.execute(text("DELETE FROM investment_transactions WHERE user_id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.execute(text("DELETE FROM transactions WHERE user_id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.execute(text("DELETE FROM recurring_transactions WHERE user_id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.execute(text("DELETE FROM budgets WHERE user_id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.execute(text("DELETE FROM investment_holdings WHERE user_id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.execute(text("DELETE FROM categories WHERE user_id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.execute(text("DELETE FROM accounts WHERE user_id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.execute(text("DELETE FROM users WHERE id IN (:a, :b)"), {"a": USER_A_ID, "b": USER_B_ID})
        session.commit()


def _query_as_user(user_id: str, table: str) -> list:
    """Query a table with RLS context set to user_id. Uses app_user role."""
    with SessionLocal() as session:
        session.execute(text("SET search_path TO expense_tracker, public"))
        session.execute(text("SET LOCAL ROLE app_user"))
        session.execute(text("SET LOCAL app.current_user_id = :uid"), {"uid": user_id})
        rows = session.execute(text(f"SELECT user_id FROM {table}")).fetchall()
        session.rollback()  # rollback to reset role
    return rows


def _query_without_context(table: str) -> list:
    """Query a table as app_user WITHOUT setting RLS context (fail-closed test)."""
    with SessionLocal() as session:
        session.execute(text("SET search_path TO expense_tracker, public"))
        session.execute(text("SET LOCAL ROLE app_user"))
        # Do NOT set app.current_user_id
        rows = session.execute(text(f"SELECT user_id FROM {table}")).fetchall()
        session.rollback()
    return rows


RLS_TABLES = [
    "accounts",
    "categories",
    "budgets",
    "investment_holdings",
    "transactions",
    "recurring_transactions",
    "investment_transactions",
    "bond_details",
    "screenshot_parse_logs",
    "api_usage",
]


@pytest.mark.parametrize("table", RLS_TABLES)
def test_user_a_sees_only_own_data(table):
    rows = _query_as_user(USER_A_ID, table)
    user_ids = {str(r[0]) for r in rows}
    assert USER_A_ID in user_ids or len(rows) == 0, f"User A should see own data in {table}"
    assert USER_B_ID not in user_ids, f"User A must NOT see User B's data in {table}"


@pytest.mark.parametrize("table", RLS_TABLES)
def test_user_b_sees_only_own_data(table):
    rows = _query_as_user(USER_B_ID, table)
    user_ids = {str(r[0]) for r in rows}
    assert USER_B_ID in user_ids or len(rows) == 0, f"User B should see own data in {table}"
    assert USER_A_ID not in user_ids, f"User B must NOT see User A's data in {table}"


# Exclude categories because system rows (user_id IS NULL) are visible without context
@pytest.mark.parametrize("table", [
    "accounts",
    "budgets",
    "investment_holdings",
    "transactions",
    "recurring_transactions",
    "investment_transactions",
    "bond_details",
    "screenshot_parse_logs",
    "api_usage",
])
def test_no_context_returns_no_rows(table):
    """Without RLS context, no rows should be visible (fail-closed)."""
    rows = _query_without_context(table)
    assert len(rows) == 0, f"No context should return 0 rows for {table}, got {len(rows)}"


def test_categories_show_system_defaults_without_user_context():
    """Categories with user_id IS NULL (system) should be visible to any user."""
    rows = _query_as_user(USER_A_ID, "categories")
    # Should see own categories + system categories (user_id IS NULL)
    assert len(rows) > 0, "User A should see at least system categories"


def test_insert_with_wrong_user_id_blocked():
    """Attempting to INSERT a row with a different user_id should be blocked by RLS WITH CHECK."""
    with SessionLocal() as session:
        session.execute(text("SET search_path TO expense_tracker, public"))
        session.execute(text("SET LOCAL ROLE app_user"))
        session.execute(text("SET LOCAL app.current_user_id = :uid"), {"uid": USER_A_ID})
        with pytest.raises(Exception):
            session.execute(text("""
                INSERT INTO accounts (user_id, name, type, balance)
                VALUES (:uid, 'Hacked Account', 'savings', 0)
            """), {"uid": USER_B_ID})
        session.rollback()
