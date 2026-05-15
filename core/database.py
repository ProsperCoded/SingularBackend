from __future__ import annotations

from pathlib import Path
from ssl import SSLContext, create_default_context

from sqlalchemy.engine import make_url
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from core.config import settings

_CERT_PATH = Path(__file__).resolve().parents[1] / "certs" / "ca-certificate.crt"


def _build_ssl_context() -> SSLContext:
    if _CERT_PATH.exists():
        return create_default_context(cafile=str(_CERT_PATH))
    return create_default_context()


def _is_digitalocean_host(hostname: str | None) -> bool:
    return bool(hostname) and hostname.endswith(".ondigitalocean.com")


def _normalize_database_url(database_url: str) -> tuple[str, dict[str, object]]:
    url = make_url(database_url)
    connect_args: dict[str, object] = {}
    if url.get_backend_name() == "postgresql" and url.drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")
    if url.get_backend_name() == "postgresql":
        sslmode = url.query.get("sslmode")
        if sslmode == "disable":
            connect_args["ssl"] = False
        elif _is_digitalocean_host(url.host):
            connect_args["ssl"] = _build_ssl_context()
        elif sslmode is not None:
            connect_args["ssl"] = create_default_context()
        else:
            # Keep local and non-DO development connections plaintext unless
            # the URL explicitly opts into SSL.
            connect_args["ssl"] = False
        if sslmode is not None:
            url = url.difference_update_query(["sslmode"])
    return url.render_as_string(hide_password=False), connect_args


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
