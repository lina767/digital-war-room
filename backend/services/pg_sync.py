"""Synchronous PostgreSQL access via psycopg when DATABASE_URL is set."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator

__all__ = ["postgres_url", "use_postgres", "connection"]


def postgres_url() -> str:
    return (os.getenv("DATABASE_URL") or "").strip()


def use_postgres() -> bool:
    return bool(postgres_url())


@contextmanager
def connection() -> Generator[Any, None, None]:
    import psycopg

    url = postgres_url()
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    conn = psycopg.connect(url)
    try:
        yield conn
    finally:
        conn.close()
