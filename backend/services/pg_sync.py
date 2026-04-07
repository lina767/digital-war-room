"""Synchronous PostgreSQL access via psycopg when DATABASE_URL is usable."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator
from urllib.parse import urlparse

__all__ = ["postgres_url", "effective_postgres_url", "use_postgres", "connection"]


def postgres_url() -> str:
    return (os.getenv("DATABASE_URL") or "").strip()


def _env_is_production() -> bool:
    return (os.getenv("ENVIRONMENT") or "").strip().lower() in {"prod", "production"}


def _is_internal_only_host(db_url: str) -> bool:
    try:
        host = (urlparse(db_url).hostname or "").strip().lower()
    except Exception:
        return False
    return bool(host) and (host.endswith(".internal") or host == "localhost.internal")


def use_postgres() -> bool:
    url = postgres_url()
    if not url:
        return False
    # Local/dev machines cannot resolve provider-internal hostnames (e.g. railway.internal).
    # In that case we intentionally disable Postgres usage and fall back to local stores.
    if not _env_is_production() and _is_internal_only_host(url):
        return False
    return True


def effective_postgres_url() -> str:
    return postgres_url() if use_postgres() else ""


@contextmanager
def connection() -> Generator[Any, None, None]:
    import psycopg

    url = postgres_url()
    if not use_postgres():
        raise RuntimeError("DATABASE_URL not set or not usable in this environment")
    conn = psycopg.connect(url)
    try:
        yield conn
    finally:
        conn.close()
