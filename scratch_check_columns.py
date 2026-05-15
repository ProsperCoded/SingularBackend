import asyncio
from sqlmodel import text
from core.database import async_engine


async def check_columns():
    async with async_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'product'"
            )
        )
        columns = result.all()
        print(f"Columns in 'product' table: {columns}")


if __name__ == "__main__":
    asyncio.run(check_columns())
