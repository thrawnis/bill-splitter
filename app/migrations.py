"""Idempotent forward migrations for schema changes that create_all can't apply.

create_all only creates missing tables; it never alters existing ones. Each
statement here must be safe to run repeatedly on both fresh and existing
databases.
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine

STATEMENTS = [
    # Guests can be assigned items, so an assignment references a user OR a guest.
    "ALTER TABLE item_assignments ALTER COLUMN user_id DROP NOT NULL",
    "ALTER TABLE item_assignments ADD COLUMN IF NOT EXISTS guest_id UUID "
    "REFERENCES bill_guests(id) ON DELETE CASCADE",
]


def run_migrations(engine: Engine) -> None:
    with engine.begin() as conn:
        for statement in STATEMENTS:
            conn.execute(text(statement))
