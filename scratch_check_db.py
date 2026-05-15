import asyncio
from sqlmodel import select, text
from core.database import async_engine

async def check_db():
    async with async_engine.connect() as conn:
        result = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
        tables = result.all()
        print(f"Tables in DB: {tables}")

if __name__ == "__main__":
    asyncio.run(check_db())
