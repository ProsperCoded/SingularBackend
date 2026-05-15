from __future__ import annotations

from datetime import datetime

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncConnection
from sqlmodel import SQLModel


async def ensure_schema(async_engine: AsyncEngine) -> None:
    import models.user  # noqa: F401
    import models.product  # noqa: F401
    import models.scan_event  # noqa: F401

    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        await _repair_legacy_schema(conn)
        await _repair_product_schema(conn)


async def _repair_legacy_schema(conn: AsyncConnection) -> None:
    table_names = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    if "user" not in table_names:
        return

    columns = await conn.run_sync(
        lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns("user")}
    )
    dialect_name = conn.dialect.name

    missing_column_statements = {
        "full_name": _render_add_column_sql(
            dialect_name, '"user"', "full_name", "VARCHAR", "''", nullable=False
        ),
        "password_hash": _render_add_column_sql(
            dialect_name, '"user"', "password_hash", "VARCHAR", "''", nullable=False
        ),
        "role": _render_add_column_sql(
            dialect_name, '"user"', "role", "VARCHAR", "'brand'", nullable=False
        ),
        "created_at": _render_add_column_sql(
            dialect_name,
            '"user"',
            "created_at",
            _timestamp_type(dialect_name),
            _timestamp_default(dialect_name),
            nullable=False,
        ),
        "vendor_id": _render_add_column_sql(
            dialect_name, '"user"', "vendor_id", "VARCHAR", None, nullable=True
        ),
    }

    for column_name, statement in missing_column_statements.items():
        if column_name not in columns:
            await conn.execute(text(statement))


def _render_add_column_sql(
    dialect_name: str,
    table_name: str,
    column_name: str,
    column_type: str,
    default_sql: str | None,
    *,
    nullable: bool,
) -> str:
    if dialect_name == "postgresql":
        parts = [f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_type}"]
        if default_sql is not None:
            parts.append(f"DEFAULT {default_sql}")
        if not nullable:
            parts.append("NOT NULL")
        return " ".join(parts)

    if dialect_name == "sqlite":
        parts = [f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"]
        if default_sql is not None:
            parts.append(f"DEFAULT {default_sql}")
        if not nullable:
            parts.append("NOT NULL")
        return " ".join(parts)

    parts = [f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"]
    if default_sql is not None:
        parts.append(f"DEFAULT {default_sql}")
    if not nullable:
        parts.append("NOT NULL")
    return " ".join(parts)


def _timestamp_type(dialect_name: str) -> str:
    if dialect_name == "sqlite":
        return "DATETIME"
    return "TIMESTAMP WITHOUT TIME ZONE"


def _timestamp_default(dialect_name: str) -> str:
    if dialect_name == "sqlite":
        return f"'{datetime.utcnow().isoformat(sep=' ')}'"
    return "CURRENT_TIMESTAMP"


async def _repair_product_schema(conn: AsyncConnection) -> None:
    """Add columns that exist in the Product model but may be missing from the live DB."""
    table_names = await conn.run_sync(
        lambda sync_conn: inspect(sync_conn).get_table_names()
    )
    if "product" not in table_names:
        return

    columns = await conn.run_sync(
        lambda sync_conn: {
            col["name"] for col in inspect(sync_conn).get_columns("product")
        }
    )
    dialect_name = conn.dialect.name

    missing_columns = {
        "transaction_ref": _render_add_column_sql(
            dialect_name, "product", "transaction_ref", "VARCHAR", None, nullable=True
        ),
        "status": _render_add_column_sql(
            dialect_name, "product", "status", "VARCHAR", "'generated'", nullable=False
        ),
        "qr_png_b64": _render_add_column_sql(
            dialect_name, "product", "qr_png_b64", "VARCHAR", None, nullable=True
        ),
        "enrolment_bundle": _render_add_column_sql(
            dialect_name, "product", "enrolment_bundle", "JSON", None, nullable=True
        ),
        "enrolment_scan_count": _render_add_column_sql(
            dialect_name, "product", "enrolment_scan_count", "INTEGER", "0", nullable=False
        ),
        "enrolled_at": _render_add_column_sql(
            dialect_name,
            "product",
            "enrolled_at",
            _timestamp_type(dialect_name),
            None,
            nullable=True,
        ),
        "updated_at": _render_add_column_sql(
            dialect_name,
            "product",
            "updated_at",
            _timestamp_type(dialect_name),
            _timestamp_default(dialect_name),
            nullable=False,
        ),
    }

    for column_name, statement in missing_columns.items():
        if column_name not in columns:
            print(f"[schema] Adding missing column product.{column_name}")
            await conn.execute(text(statement))

    # Back-fill transaction_ref for any pre-existing rows (use id to guarantee uniqueness)
    if "transaction_ref" not in columns:
        await conn.execute(
            text("UPDATE product SET transaction_ref = 'LEGACY_' || id WHERE transaction_ref IS NULL")
        )

    # The old schema had batch_id NOT NULL; the current model doesn't include it.
    # Drop the NOT NULL constraint so new inserts (which don't supply batch_id) succeed.
    if "batch_id" in columns and dialect_name == "postgresql":
        await conn.execute(
            text("ALTER TABLE product ALTER COLUMN batch_id DROP NOT NULL")
        )


