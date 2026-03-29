"""Seed default Indian categories

Revision ID: 010
Revises: 009
Create Date: 2026-03-29
"""
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # System categories have user_id = NULL, is_system = true
    op.execute("""
    -- ── EXPENSE categories ──
    INSERT INTO expense_tracker.categories (user_id, parent_id, name, type, icon, is_system, sort_order) VALUES
    (NULL, NULL, 'Food & Dining', 'expense', '🍽️', true, 1),
    (NULL, NULL, 'Transport', 'expense', '🚗', true, 2),
    (NULL, NULL, 'Shopping', 'expense', '🛍️', true, 3),
    (NULL, NULL, 'Bills & Utilities', 'expense', '💡', true, 4),
    (NULL, NULL, 'Housing', 'expense', '🏠', true, 5),
    (NULL, NULL, 'Health', 'expense', '🏥', true, 6),
    (NULL, NULL, 'Education', 'expense', '📚', true, 7),
    (NULL, NULL, 'Entertainment', 'expense', '🎬', true, 8),
    (NULL, NULL, 'Personal Care', 'expense', '💇', true, 9),
    (NULL, NULL, 'Travel / Holiday', 'expense', '✈️', true, 10),
    (NULL, NULL, 'Gifts & Donations', 'expense', '🎁', true, 11),
    (NULL, NULL, 'EMI & Loans', 'expense', '🏦', true, 12),
    (NULL, NULL, 'Taxes', 'expense', '📋', true, 13),
    (NULL, NULL, 'Insurance', 'expense', '🛡️', true, 14),
    (NULL, NULL, 'Domestic Help', 'expense', '🏠', true, 15),
    (NULL, NULL, 'Miscellaneous', 'expense', '📦', true, 16);

    -- Subcategories for Food & Dining
    INSERT INTO expense_tracker.categories (user_id, parent_id, name, type, icon, is_system, sort_order)
    SELECT NULL, id, sub.name, 'expense', sub.icon, true, sub.sort_order
    FROM expense_tracker.categories parent,
    (VALUES
        ('Groceries', '🛒', 1), ('Restaurants', '🍴', 2),
        ('Swiggy / Zomato', '📱', 3), ('Chai / Snacks', '☕', 4)
    ) AS sub(name, icon, sort_order)
    WHERE parent.name = 'Food & Dining' AND parent.parent_id IS NULL AND parent.is_system = true;

    -- Subcategories for Transport
    INSERT INTO expense_tracker.categories (user_id, parent_id, name, type, icon, is_system, sort_order)
    SELECT NULL, id, sub.name, 'expense', sub.icon, true, sub.sort_order
    FROM expense_tracker.categories parent,
    (VALUES
        ('Petrol / Diesel', '⛽', 1), ('Ola / Uber', '🚕', 2),
        ('Metro / Bus', '🚇', 3), ('Auto', '🛺', 4)
    ) AS sub(name, icon, sort_order)
    WHERE parent.name = 'Transport' AND parent.parent_id IS NULL AND parent.is_system = true;

    -- Subcategories for Bills & Utilities
    INSERT INTO expense_tracker.categories (user_id, parent_id, name, type, icon, is_system, sort_order)
    SELECT NULL, id, sub.name, 'expense', sub.icon, true, sub.sort_order
    FROM expense_tracker.categories parent,
    (VALUES
        ('Electricity', '⚡', 1), ('Mobile Recharge', '📱', 2),
        ('Internet / WiFi', '🌐', 3), ('Gas', '🔥', 4),
        ('Water', '💧', 5), ('DTH', '📡', 6)
    ) AS sub(name, icon, sort_order)
    WHERE parent.name = 'Bills & Utilities' AND parent.parent_id IS NULL AND parent.is_system = true;

    -- ── INCOME categories ──
    INSERT INTO expense_tracker.categories (user_id, parent_id, name, type, icon, is_system, sort_order) VALUES
    (NULL, NULL, 'Salary', 'income', '💰', true, 1),
    (NULL, NULL, 'Freelance / Consulting', 'income', '💻', true, 2),
    (NULL, NULL, 'Business Income', 'income', '🏢', true, 3),
    (NULL, NULL, 'Interest Income', 'income', '🏦', true, 4),
    (NULL, NULL, 'Dividend Income', 'income', '📈', true, 5),
    (NULL, NULL, 'Rental Income', 'income', '🏠', true, 6),
    (NULL, NULL, 'Capital Gains', 'income', '📊', true, 7),
    (NULL, NULL, 'Cashback / Rewards', 'income', '🎯', true, 8),
    (NULL, NULL, 'Other Income', 'income', '💵', true, 9);
    """)

def downgrade() -> None:
    op.execute("DELETE FROM expense_tracker.categories WHERE is_system = true;")
