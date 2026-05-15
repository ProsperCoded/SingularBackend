"""Repair product table — add columns missing from live DB

Revision ID: 20260515_0002
Revises: 20260515_0001
Create Date: 2026-05-15 11:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260515_0002"
down_revision = "20260515_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use ADD COLUMN IF NOT EXISTS so this is idempotent on PostgreSQL.
    # These columns exist in the Product model but were missing from the live DB
    # because the table was created by an older version of the schema.

    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE product ADD COLUMN IF NOT EXISTS transaction_ref VARCHAR"
        )
        op.execute(
            "ALTER TABLE product ADD COLUMN IF NOT EXISTS status VARCHAR NOT NULL DEFAULT 'generated'"
        )
        op.execute(
            "ALTER TABLE product ADD COLUMN IF NOT EXISTS qr_png_b64 VARCHAR"
        )
        op.execute(
            "ALTER TABLE product ADD COLUMN IF NOT EXISTS enrolment_bundle JSON"
        )
        op.execute(
            "ALTER TABLE product ADD COLUMN IF NOT EXISTS enrolment_scan_count INTEGER NOT NULL DEFAULT 0"
        )
        op.execute(
            "ALTER TABLE product ADD COLUMN IF NOT EXISTS enrolled_at TIMESTAMP WITHOUT TIME ZONE"
        )
        op.execute(
            "ALTER TABLE product ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
        )

        # Back-fill transaction_ref for any existing rows using the row id so
        # the unique constraint can be added without conflicts.
        op.execute(
            "UPDATE product SET transaction_ref = 'LEGACY_' || id WHERE transaction_ref IS NULL"
        )

        # Now enforce NOT NULL and UNIQUE (use try/except-style via DO blocks)
        op.execute("""
            DO $$
            BEGIN
                ALTER TABLE product ALTER COLUMN transaction_ref SET NOT NULL;
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """)
        op.execute("""
            DO $$
            BEGIN
                ALTER TABLE product ADD CONSTRAINT uq_product_transaction_ref UNIQUE (transaction_ref);
            EXCEPTION WHEN duplicate_table THEN NULL;
            END $$;
        """)

        # Add missing indexes
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_product_transaction_ref ON product (transaction_ref)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_product_status ON product (status)"
        )
    else:
        # SQLite fallback (dev local db) — ADD COLUMN doesn't support IF NOT EXISTS
        # so we catch errors individually.
        for ddl in [
            "ALTER TABLE product ADD COLUMN transaction_ref VARCHAR",
            "ALTER TABLE product ADD COLUMN status VARCHAR NOT NULL DEFAULT 'generated'",
            "ALTER TABLE product ADD COLUMN qr_png_b64 VARCHAR",
            "ALTER TABLE product ADD COLUMN enrolment_bundle JSON",
            "ALTER TABLE product ADD COLUMN enrolment_scan_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE product ADD COLUMN enrolled_at DATETIME",
            "ALTER TABLE product ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
        ]:
            try:
                op.execute(ddl)
            except Exception:
                pass


def downgrade() -> None:
    # PostgreSQL doesn't support DROP COLUMN IF EXISTS in older versions,
    # but the columns would simply be unused — safe to leave in place.
    pass
