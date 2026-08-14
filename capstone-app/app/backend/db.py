"""Lakebase (Postgres) access, always as the service principal.

An async helper, ``lakebase_sp()``, yields a pooled psycopg connection to
Lakebase authenticated as the app SP (see ``auth.sp_client``).

Token lifecycle: Lakebase OAuth tokens expire ~1h. Rather than refresh a
shared secret, we mint a **fresh token every time a physical connection is
opened** (``_TokenConnection.connect``) and cap connection ``max_lifetime``
below the token TTL so pooled connections recycle before their token expires.
Reused connections are therefore always backed by a valid token, with no
background refresh thread to manage.

Async (``AsyncConnectionPool``) so FastAPI handlers can ``await`` DB work and
fan out independent queries concurrently (T3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from .auth import sp_client
from .config import get_settings

# Recycle connections well before the ~1h token TTL.
_MAX_LIFETIME_S = 45 * 60

_pool: AsyncConnectionPool | None = None


def _fresh_token() -> str:
    """Mint a short-lived Lakebase OAuth token via the SP client."""
    endpoint = get_settings().lakebase_endpoint
    return sp_client().postgres.generate_database_credential(endpoint=endpoint).token


def _pg_user() -> str:
    """The Postgres role to connect as.

    Deployed: the injected ``PGUSER`` (the SP's client id). Local: the
    developer identity the SP client authenticates as.
    """
    settings = get_settings()
    if settings.deployed and settings.pguser:
        return settings.pguser
    return sp_client().current_user.me().user_name


class _TokenConnection(AsyncConnection):
    """Async connection that injects a fresh OAuth token as its password."""

    @classmethod
    async def connect(cls, conninfo: str = "", **kwargs) -> _TokenConnection:
        kwargs["password"] = _fresh_token()
        return await super().connect(conninfo, **kwargs)


async def _get_pool() -> AsyncConnectionPool:
    """Lazily build + open the pool (import must not require connectivity)."""
    global _pool
    if _pool is None:
        settings = get_settings()
        pool = AsyncConnectionPool(
            connection_class=_TokenConnection,
            kwargs={
                "host": settings.pghost,
                "port": settings.pgport,
                "dbname": settings.pgdatabase,
                "user": _pg_user(),
                "sslmode": "require",
            },
            min_size=1,
            max_size=5,
            max_lifetime=_MAX_LIFETIME_S,
            check=AsyncConnectionPool.check_connection,  # pre-ping; survives scale-to-zero
            open=False,
        )
        await pool.open()
        _pool = pool
    return _pool


@asynccontextmanager
async def lakebase_sp() -> AsyncIterator[AsyncConnection]:
    """Yield a pooled Lakebase connection acting as the service principal.

    async with lakebase_sp() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1")
    """
    pool = await _get_pool()
    async with pool.connection() as conn:
        yield conn


async def close_pool() -> None:
    """Close the connection pool. Wire into the app's shutdown/lifespan."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
