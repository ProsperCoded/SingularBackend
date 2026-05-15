from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from core.database import async_engine
from core.schema import ensure_schema
from main import app


@pytest.fixture(autouse=True)
def reset_database() -> Iterator[None]:
    async def _reset() -> None:
        import models.user  # noqa: F401
        import models.product  # noqa: F401
        import models.scan_event  # noqa: F401

        async with async_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await ensure_schema(async_engine)
        await async_engine.dispose()

    asyncio.run(_reset())
    yield
    asyncio.run(async_engine.dispose())


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
