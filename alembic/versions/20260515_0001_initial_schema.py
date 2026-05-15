"""Initial application schema

Revision ID: 20260515_0001
Revises:
Create Date: 2026-05-15 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260515_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("vendor_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("vendor_id"),
    )
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=False)
    op.create_index(op.f("ix_user_full_name"), "user", ["full_name"], unique=False)

    op.create_table(
        "product",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("brand_id", sa.String(), nullable=False),
        sa.Column("vendor_id", sa.String(), nullable=True),
        sa.Column("product_type", sa.String(), nullable=False),
        sa.Column("transaction_ref", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("qr_png_b64", sa.String(), nullable=True),
        sa.Column("enrolment_bundle", sa.JSON(), nullable=True),
        sa.Column("enrolment_scan_count", sa.Integer(), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_ref"),
    )
    op.create_index(op.f("ix_product_brand_id"), "product", ["brand_id"], unique=False)
    op.create_index(op.f("ix_product_product_type"), "product", ["product_type"], unique=False)
    op.create_index(op.f("ix_product_status"), "product", ["status"], unique=False)
    op.create_index(op.f("ix_product_transaction_ref"), "product", ["transaction_ref"], unique=False)
    op.create_index(op.f("ix_product_vendor_id"), "product", ["vendor_id"], unique=False)

    op.create_table(
        "scanevent",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("vendor_id", sa.String(), nullable=True),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("device_hash", sa.String(), nullable=True),
        sa.Column("scanned_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scanevent_product_id"), "scanevent", ["product_id"], unique=False)
    op.create_index(op.f("ix_scanevent_vendor_id"), "scanevent", ["vendor_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_scanevent_vendor_id"), table_name="scanevent")
    op.drop_index(op.f("ix_scanevent_product_id"), table_name="scanevent")
    op.drop_table("scanevent")

    op.drop_index(op.f("ix_product_vendor_id"), table_name="product")
    op.drop_index(op.f("ix_product_transaction_ref"), table_name="product")
    op.drop_index(op.f("ix_product_status"), table_name="product")
    op.drop_index(op.f("ix_product_product_type"), table_name="product")
    op.drop_index(op.f("ix_product_brand_id"), table_name="product")
    op.drop_table("product")

    op.drop_index(op.f("ix_user_full_name"), table_name="user")
    op.drop_index(op.f("ix_user_email"), table_name="user")
    op.drop_table("user")
