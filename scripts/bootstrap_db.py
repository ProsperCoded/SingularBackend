from __future__ import annotations

import asyncio

from core.database import async_engine
from core.schema import ensure_schema


async def main() -> None:
    await ensure_schema(async_engine)
    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
