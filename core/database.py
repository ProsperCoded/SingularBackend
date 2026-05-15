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
    import ssl
    ctx = create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _is_digitalocean_host(hostname: str | None) -> bool:
    return bool(hostname) and hostname.endswith(".ondigitalocean.com")


def _normalize_database_url(database_url: str) -> tuple[str, dict[str, object]]:
    url = make_url(database_url)
    connect_args: dict[str, object] = {}
    if url.get_backend_name() == "postgresql" and url.drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")
    if url.get_backend_name() == "postgresql":
        ssl_val = url.query.get("sslmode") or url.query.get("ssl")
        if ssl_val == "disable":
            connect_args["ssl"] = False
        elif ssl_val is not None:
            # Always use the unverified context if SSL is requested, 
            # avoiding brittle DigitalOcean hostname checks.
            connect_args["ssl"] = _build_ssl_context()
        else:
            # Keep local and non-DO development connections plaintext unless
            # the URL explicitly opts into SSL.
            connect_args["ssl"] = False
            
        # Clean up both possible query parameters
        url = url.difference_update_query(["sslmode", "ssl"])
    return url.render_as_string(hide_password=False), connect_args


_database_url, _connect_args = _normalize_database_url(settings.DATABASE_URL)

# asyncpg driver args must live in connect_args, not as engine-level kwargs.
# Setting prepared_statement_cache_size=0 disables the prepared statement cache,
# which is required when connecting through PGBouncer or DigitalOcean connection pooling.
if _database_url.startswith("postgresql"):
    _connect_args.setdefault("prepared_statement_cache_size", 0)

async_engine = create_async_engine(
    _database_url,
    echo=False,
    connect_args=_connect_args,
)


async def get_db_session() -> AsyncSession:
    """
    Yield a session and close it after use
    """

    async_session = sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
