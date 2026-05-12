from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from core.config import settings


async_engine = create_async_engine(settings.DATABASE_URL, echo=True)


async def get_db_session() -> AsyncSession:
    """
    Yield a session and close it after use
    """

    async_session = sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
