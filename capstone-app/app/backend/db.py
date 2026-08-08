"""T2 — Lakebase (Postgres) access, always as the service principal.

A single helper, ``lakebase_sp()``, yields a pooled psycopg connection to
Lakebase authenticated as the app SP (see ``auth.sp_client``).

Token lifecycle: Lakebase OAuth tokens expire ~1h. Rather than refresh a
shared secret, we mint a **fresh token every time a physical connection is
opened** (``_TokenConnection.connect``) and cap connection ``max_lifetime``
below the token TTL so pooled connections recycle before their token expires.
Reused connections are therefore always backed by a valid token, with no
background refresh thread to manage.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool

from .auth import sp_client
from .config import deployed, load_env

# Recycle connections well before the ~1h token TTL.
_MAX_LIFETIME_S = 45 * 60

_pool: ConnectionPool | None = None


def _endpoint() -> str:
    return load_env()["LAKEBASE_ENDPOINT"]


def _fresh_token() -> str:
    """Mint a short-lived Lakebase OAuth token via the SP client."""
    return sp_client().postgres.generate_database_credential(endpoint=_endpoint()).token


def _pg_user() -> str:
    """The Postgres role to connect as.

    Deployed: the injected ``PGUSER`` (the SP's client id). Local: the
    developer identity the SP client authenticates as.
    """
    cfg = load_env()
    if deployed() and cfg.get("PGUSER"):
        return cfg["PGUSER"]
    return sp_client().current_user.me().user_name


class _TokenConnection(psycopg.Connection):
    """psycopg connection that injects a fresh OAuth token as its password."""

    @classmethod
    def connect(cls, conninfo: str = "", **kwargs) -> _TokenConnection:
        kwargs["password"] = _fresh_token()
        return super().connect(conninfo, **kwargs)


def _get_pool() -> ConnectionPool:
    """Lazily build the connection pool (import must not require connectivity)."""
    global _pool
    if _pool is None:
        cfg = load_env()
        _pool = ConnectionPool(
            connection_class=_TokenConnection,
            kwargs={
                "host": cfg["PGHOST"],
                "port": int(cfg.get("PGPORT", "5432")),
                "dbname": cfg["PGDATABASE"],
                "user": _pg_user(),
                "sslmode": "require",
            },
            min_size=1,
            max_size=5,
            max_lifetime=_MAX_LIFETIME_S,
            check=ConnectionPool.check_connection,  # pre-ping; survives scale-to-zero
            open=True,
        )
    return _pool


@contextmanager
def lakebase_sp() -> Iterator[psycopg.Connection]:
    """Yield a pooled Lakebase connection acting as the service principal.

        with lakebase_sp() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    """
    with _get_pool().connection() as conn:
        yield conn


def close_pool() -> None:
    """Close the connection pool. Wire into the app's shutdown/lifespan."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
