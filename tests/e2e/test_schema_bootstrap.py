from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from core.schema import ensure_schema


def test_ensure_schema_repairs_legacy_user_table(tmp_path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async def _run() -> set[str]:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    CREATE TABLE user (
                        id VARCHAR PRIMARY KEY,
                        email VARCHAR NOT NULL
                    )
                    """
                )
            )

        await ensure_schema(engine)

        async with engine.begin() as conn:
            columns = await conn.run_sync(
                lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns("user")}
            )

        await engine.dispose()
        return columns

    columns = asyncio.run(_run())
    assert {"id", "email", "full_name", "password_hash", "role", "created_at", "vendor_id"} <= columns
