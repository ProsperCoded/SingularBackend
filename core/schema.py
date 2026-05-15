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
