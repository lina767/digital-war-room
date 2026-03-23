"""Run idempotent SQL migrations from backend/migrations on startup when DATABASE_URL is set."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
_ORDER = (
    "001_pgvector_setup.sql",
    "002_quality_signals_ais_tracks.sql",
    "003_multi_tenancy.sql",
    "004_newsletter_postgres.sql",
)


async def bootstrap_schema() -> None:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        return
    try:
        import asyncpg
    except ImportError:
        return
    for name in _ORDER:
        path = _MIGRATIONS_DIR / name
        if not path.is_file():
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            conn = await asyncpg.connect(url, timeout=30.0)
        except Exception as e:
            logger.warning("[schema] bootstrap connect failed: %s", e)
            return
        try:
            await conn.execute(sql)
            logger.info("[schema] applied %s", name)
        except Exception as e:
            logger.warning("[schema] bootstrap %s failed (may already be applied): %s", name, e)
        finally:
            await conn.close()
