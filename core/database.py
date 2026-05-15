from sqlalchemy.engine import make_url
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from core.config import settings


def _normalize_database_url(database_url: str) -> tuple[str, dict[str, object]]:
    url = make_url(database_url)
    connect_args: dict[str, object] = {}
    if url.get_backend_name() == "postgresql" and url.drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")
    sslmode = url.query.get("sslmode")
    if sslmode:
        connect_args["ssl"] = sslmode != "disable"
        url = url.difference_update_query(["sslmode"])
    return str(url), connect_args


_database_url, _connect_args = _normalize_database_url(settings.DATABASE_URL)
async_engine = create_async_engine(_database_url, echo=True, connect_args=_connect_args)


async def get_db_session() -> AsyncSession:
    """
    Yield a session and close it after use
    """

    async_session = sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
