from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator

_DEFAULT_ENV = {
    "DATABASE_URL": "sqlite+aiosqlite:///./test_printpuf.db",
    "JWT_SECRET_KEY": "test_jwt_secret",
    "SQUAD_SECRET_KEY": "test_squad_secret",
    "SQUAD_BASE_URL": "https://squad.example.test",
    "DO_SPACES_REGION": "fra1",
    "DO_SPACES_KEY": "test_key",
    "DO_SPACES_SECRET": "test_secret",
    "DO_SPACES_BUCKET": "printpuf-test",
}

for key, value in _DEFAULT_ENV.items():
    os.environ[key] = value

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
