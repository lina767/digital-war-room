"""
Newsletter subscriber store (PostgreSQL). Double opt-in: only rows with confirmed_at set receive the daily mail.

Uses asyncpg with a module-level connection pool (initialised lazily on first use). All public
functions remain synchronous so call-sites in routes and the scheduler do not need to be changed;
they run the async helpers via asyncio.get_event_loop().run_until_complete() when called from a
sync context, or are awaited directly when called from an async context via the thin wrappers below.

Environment variables:
  DATABASE_URL  — asyncpg-compatible PostgreSQL DSN (required).
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

logger = logging.getLogger(__name__)

DEFAULT_NEWSLETTER_CONFLICT = (os.getenv("NEWSLETTER_DEFAULT_CONFLICT") or "Global").strip() or "Global"

# ---------------------------------------------------------------------------
# Connection pool
# ---------------------------------------------------------------------------

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is not None:
            return _pool
        url = (os.getenv("DATABASE_URL") or "").strip()
        if not url:
            raise RuntimeError(
                "DATABASE_URL is not set. PostgreSQL is required for the newsletter store."
            )
        _pool = await asyncpg.create_pool(
            url,
            min_size=1,
            max_size=5,
            command_timeout=30,
        )
        logger.info("[newsletter_store] PostgreSQL connection pool created")
    return _pool


def _run(coro):
    """Run an async coroutine from synchronous call-sites."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Inside an async context (e.g. FastAPI route) — schedule and block via a new thread.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(asyncio.run, coro)
                return fut.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Internal async helpers
# ---------------------------------------------------------------------------

async def _add_subscriber_async(email: str, conflict: str) -> Tuple[Optional[str], Optional[str]]:
    confirm_token = str(uuid.uuid4())
    unsubscribe_token = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    pool = await _get_pool()
    try:
        await pool.execute(
            """
            INSERT INTO newsletter_subscribers
                (email, conflict, subscribed_at, unsubscribe_token, confirm_token, confirmed_at)
            VALUES ($1, $2, $3, $4, $5, NULL)
            """,
            email, conflict, now, unsubscribe_token, confirm_token,
        )
        return (confirm_token, unsubscribe_token)
    except asyncpg.UniqueViolationError:
        return (None, None)


async def _remove_unconfirmed_subscriber_async(email: str, confirm_token: str) -> bool:
    pool = await _get_pool()
    result = await pool.execute(
        """
        DELETE FROM newsletter_subscribers
        WHERE email = $1 AND confirm_token = $2 AND confirmed_at IS NULL
        """,
        email, confirm_token,
    )
    rows = int(result.split()[-1])
    if rows > 0:
        logger.info(
            "Newsletter: rolled back pending subscriber for %s after failed confirmation send", email
        )
    return rows > 0


async def _confirm_subscription_async(confirm_token: str) -> dict | None:
    now = datetime.now(timezone.utc)
    tok = confirm_token.strip()
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT email, conflict FROM newsletter_subscribers"
                " WHERE confirm_token = $1 AND confirmed_at IS NULL",
                tok,
            )
            if not row:
                return None
            await conn.execute(
                "UPDATE newsletter_subscribers SET confirmed_at = $1"
                " WHERE confirm_token = $2 AND confirmed_at IS NULL",
                now, tok,
            )
    return {"email": row["email"], "conflict": row["conflict"]}


async def _remove_by_unsubscribe_token_async(token: str) -> tuple[bool, str | None]:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT email FROM newsletter_subscribers WHERE unsubscribe_token = $1",
                token.strip(),
            )
            if not row:
                return (False, None)
            email = row["email"]
            result = await conn.execute(
                "DELETE FROM newsletter_subscribers WHERE unsubscribe_token = $1",
                token.strip(),
            )
    rows = int(result.split()[-1])
    return (rows > 0, email)


async def _apply_resend_contact_sync_async(email: str, conflict: str, *, unsubscribed: bool) -> str:
    em = email
    now = datetime.now(timezone.utc)
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            if unsubscribed:
                result = await conn.execute(
                    "DELETE FROM newsletter_subscribers WHERE email = $1", em
                )
                return "removed" if int(result.split()[-1]) else "noop"
            row = await conn.fetchrow(
                "SELECT confirmed_at, conflict FROM newsletter_subscribers WHERE email = $1", em
            )
            if row:
                confirmed_at = row["confirmed_at"]
                existing_conflict = row["conflict"]
                if confirmed_at is None:
                    await conn.execute(
                        "UPDATE newsletter_subscribers SET confirmed_at = $1, conflict = $2 WHERE email = $3",
                        now, conflict, em,
                    )
                    return "updated"
                if existing_conflict != conflict:
                    await conn.execute(
                        "UPDATE newsletter_subscribers SET conflict = $1 WHERE email = $2",
                        conflict, em,
                    )
                    return "updated"
                return "noop"
            confirm_token = str(uuid.uuid4())
            unsubscribe_token = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO newsletter_subscribers
                    (email, conflict, subscribed_at, unsubscribe_token, confirm_token, confirmed_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                em, conflict, now, unsubscribe_token, confirm_token, now,
            )
            return "inserted"


async def _list_confirmed_subscribers_async(conflict: Optional[str]) -> List[dict]:
    pool = await _get_pool()
    if conflict:
        rows = await pool.fetch(
            "SELECT email, conflict, unsubscribe_token FROM newsletter_subscribers"
            " WHERE confirmed_at IS NOT NULL AND conflict = $1",
            conflict,
        )
    else:
        rows = await pool.fetch(
            "SELECT email, conflict, unsubscribe_token FROM newsletter_subscribers"
            " WHERE confirmed_at IS NOT NULL"
        )
    return [{"email": r["email"], "conflict": r["conflict"], "unsubscribe_token": r["unsubscribe_token"]} for r in rows]


async def _get_conflicts_with_subscribers_async() -> List[str]:
    pool = await _get_pool()
    rows = await pool.fetch(
        "SELECT DISTINCT conflict FROM newsletter_subscribers"
        " WHERE confirmed_at IS NOT NULL ORDER BY conflict"
    )
    return [r["conflict"] for r in rows]


async def _get_subscriber_stats_async() -> Dict[str, Any]:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM newsletter_subscribers")
        confirmed = await conn.fetchval(
            "SELECT COUNT(*) FROM newsletter_subscribers WHERE confirmed_at IS NOT NULL"
        )
        rows = await conn.fetch(
            """
            SELECT conflict, COUNT(*) AS cnt FROM newsletter_subscribers
            WHERE confirmed_at IS NOT NULL
            GROUP BY conflict ORDER BY conflict
            """
        )
    pending = int(total) - int(confirmed)
    by_conflict = [{"conflict": r["conflict"], "confirmed": int(r["cnt"])} for r in rows]
    return {
        "backend": "postgresql",
        "total_rows": int(total),
        "confirmed": int(confirmed),
        "pending": pending,
        "confirmed_by_conflict": by_conflict,
    }


async def _try_acquire_daily_newsletter_lock_async() -> bool:
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT started_at, completed_at FROM newsletter_daily_lock WHERE day_utc = $1",
                day,
            )
            if row:
                completed_at = row["completed_at"]
                started_at = row["started_at"]
                if completed_at is not None:
                    logger.info("Newsletter daily: already completed for %s", day)
                    return False
                if isinstance(started_at, datetime):
                    started = started_at.replace(tzinfo=timezone.utc) if started_at.tzinfo is None else started_at
                else:
                    try:
                        started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
                    except ValueError:
                        started = now
                if now - started < timedelta(minutes=30):
                    logger.info("Newsletter daily: another run in progress for %s", day)
                    return False
                await conn.execute("DELETE FROM newsletter_daily_lock WHERE day_utc = $1", day)
            try:
                await conn.execute(
                    "INSERT INTO newsletter_daily_lock (day_utc, started_at, completed_at)"
                    " VALUES ($1, $2, NULL)",
                    day, now,
                )
            except asyncpg.UniqueViolationError:
                logger.info("Newsletter daily: lock contention for %s", day)
                return False
    return True


async def _mark_daily_newsletter_completed_async() -> None:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc)
    pool = await _get_pool()
    await pool.execute(
        "UPDATE newsletter_daily_lock SET completed_at = $1 WHERE day_utc = $2",
        now, day,
    )


async def _clear_daily_newsletter_lock_today_async() -> None:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pool = await _get_pool()
    await pool.execute("DELETE FROM newsletter_daily_lock WHERE day_utc = $1", day)


async def _remove_subscriber_by_email_async(email: str) -> bool:
    pool = await _get_pool()
    result = await pool.execute(
        "DELETE FROM newsletter_subscribers WHERE email = $1", email
    )
    return int(result.split()[-1]) > 0


# ---------------------------------------------------------------------------
# Public synchronous API (unchanged signatures — drop-in replacement)
# ---------------------------------------------------------------------------

def add_subscriber(email: str, conflict: str = DEFAULT_NEWSLETTER_CONFLICT) -> Tuple[Optional[str], Optional[str]]:
    """
    Add a new subscriber (unconfirmed). Returns (confirm_token, unsubscribe_token) or (None, None) if email already exists.
    """
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("email is required")
    conflict = (conflict or DEFAULT_NEWSLETTER_CONFLICT).strip() or DEFAULT_NEWSLETTER_CONFLICT
    return _run(_add_subscriber_async(email, conflict))


def remove_unconfirmed_subscriber(email: str, confirm_token: str) -> bool:
    """
    Remove a newly created unconfirmed subscriber row.
    Used to roll back subscribe flow if confirmation email sending fails.
    """
    email = (email or "").strip().lower()
    token = (confirm_token or "").strip()
    if not email or not token:
        return False
    return _run(_remove_unconfirmed_subscriber_async(email, token))


def confirm_subscription(confirm_token: str) -> dict | None:
    """
    Set confirmed_at for the subscriber with the given confirm_token.
    Returns {"email": ..., "conflict": ...} if updated, else None.
    """
    if not (confirm_token or "").strip():
        return None
    return _run(_confirm_subscription_async(confirm_token))


def remove_by_unsubscribe_token(token: str) -> tuple[bool, str | None]:
    """
    Remove subscriber by unsubscribe_token.
    Returns (True, email) if a row was deleted, (False, None) otherwise.
    """
    if not (token or "").strip():
        return (False, None)
    return _run(_remove_by_unsubscribe_token_async(token))


def apply_resend_contact_sync(email: str, conflict: str, *, unsubscribed: bool) -> str:
    """
    Mirror one Resend contact into PostgreSQL: unsubscribed=True removes the row; unsubscribed=False
    ensures a confirmed subscription (insert or confirm pending / refresh conflict).

    Conflict must already be normalized (e.g. sanitize_conflict). Returns one of:
    inserted, updated, removed, noop.
    """
    em = (email or "").strip().lower()
    if not em:
        return "noop"
    return _run(_apply_resend_contact_sync_async(em, conflict, unsubscribed=unsubscribed))


def list_confirmed_subscribers(conflict: Optional[str] = None) -> List[dict]:
    """
    Return list of confirmed subscribers. Each item: {email, conflict, unsubscribe_token}.
    If conflict is set, filter by that conflict only.
    """
    return _run(_list_confirmed_subscribers_async(conflict))


def get_conflicts_with_subscribers() -> List[str]:
    """Return distinct conflict values that have at least one confirmed subscriber."""
    return _run(_get_conflicts_with_subscribers_async())


def get_subscriber_stats() -> Dict[str, Any]:
    """
    Aggregate subscriber counts for ops/debug. Does not expose email addresses.
    """
    return _run(_get_subscriber_stats_async())


def try_acquire_daily_newsletter_lock() -> bool:
    """
    Mutex for the daily send so overlapping cron + in-process runs do not duplicate mail the same UTC day.
    Returns True if this invocation should run the job; False if already completed today or another run in progress.
    """
    return _run(_try_acquire_daily_newsletter_lock_async())


def mark_daily_newsletter_completed() -> None:
    """Mark today's daily newsletter run as finished (prevents duplicate sends same UTC day)."""
    _run(_mark_daily_newsletter_completed_async())


def clear_daily_newsletter_lock_today() -> None:
    """
    Remove today's lock row (incomplete run). Use when the job acquired the lock but sent zero
    emails so cron / a later attempt can retry the same UTC day.
    """
    _run(_clear_daily_newsletter_lock_today_async())


def remove_subscriber_by_email(email: str) -> bool:
    """
    Remove a subscriber row by email (e.g. bounce/complaint webhook). Returns True if a row was deleted.
    """
    em = (email or "").strip().lower()
    if not em:
        return False
    return _run(_remove_subscriber_by_email_async(em))
