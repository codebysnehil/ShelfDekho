from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import get_settings


def normalize_database_url(url: str) -> tuple[str, dict]:
    """Turn a provider URL (Neon, Supabase, Render) into an asyncpg URL plus connect args.

    Hosted Postgres URLs usually look like ``postgres://...?sslmode=require``, which
    asyncpg does not understand, so the SSL flag moves into ``connect_args``.
    """
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"

    query = dict(parse_qsl(parts.query))
    connect_args: dict = {}
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    if sslmode in ("require", "verify-ca", "verify-full"):
        connect_args["ssl"] = "require"
    # PgBouncer in transaction mode (Neon's "-pooler" hosts) breaks prepared statements.
    if parts.hostname and "-pooler" in parts.hostname:
        connect_args["statement_cache_size"] = 0

    clean = urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return clean, connect_args


def make_engine(url: str) -> AsyncEngine:
    settings = get_settings()
    clean_url, connect_args = normalize_database_url(url)
    kwargs: dict = {"connect_args": connect_args, "pool_pre_ping": True}
    if settings.is_test:
        # Each pytest-asyncio test runs in its own event loop; pooled asyncpg
        # connections cannot cross loops.
        kwargs["poolclass"] = NullPool
    else:
        kwargs.update(pool_size=5, max_overflow=5, pool_recycle=300)
    return create_async_engine(clean_url, **kwargs)


_settings = get_settings()
engine = make_engine(_settings.database_url)
analyst_engine = (
    make_engine(_settings.analyst_database_url) if _settings.analyst_database_url else engine
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
