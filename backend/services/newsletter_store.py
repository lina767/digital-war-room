"""
Newsletter subscriber store (SQLite). Double opt-in: only rows with confirmed_at set receive the daily mail.
"""

import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("NEWSLETTER_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "newsletter.sqlite"))
DEFAULT_NEWSLETTER_CONFLICT = (os.getenv("NEWSLETTER_DEFAULT_CONFLICT") or "Global").strip() or "Global"


def _ensure_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            conflict TEXT NOT NULL DEFAULT 'Global',
            subscribed_at TEXT NOT NULL,
            unsubscribe_token TEXT NOT NULL UNIQUE,
            confirm_token TEXT NOT NULL UNIQUE,
            confirmed_at TEXT
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_newsletter_email ON newsletter_subscribers(email)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_newsletter_conflict ON newsletter_subscribers(conflict)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_newsletter_confirmed ON newsletter_subscribers(confirmed_at)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_daily_lock (
            day_utc TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            completed_at TEXT
        )
    """)
    conn.commit()
    return conn


def add_subscriber(email: str, conflict: str = DEFAULT_NEWSLETTER_CONFLICT) -> Tuple[Optional[str], Optional[str]]:
    """
    Add a new subscriber (unconfirmed). Returns (confirm_token, unsubscribe_token) or (None, None) if email already exists.
    """
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("email is required")
    conflict = (conflict or DEFAULT_NEWSLETTER_CONFLICT).strip() or DEFAULT_NEWSLETTER_CONFLICT
    confirm_token = str(uuid.uuid4())
    unsubscribe_token = str(uuid.uuid4())
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    conn = _ensure_db()
    try:
        conn.execute(
            """
            INSERT INTO newsletter_subscribers (email, conflict, subscribed_at, unsubscribe_token, confirm_token, confirmed_at)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (email, conflict, now, unsubscribe_token, confirm_token),
        )
        conn.commit()
        return (confirm_token, unsubscribe_token)
    except sqlite3.IntegrityError:
        # email unique constraint
        return (None, None)
    finally:
        conn.close()


def remove_unconfirmed_subscriber(email: str, confirm_token: str) -> bool:
    """
    Remove a newly created unconfirmed subscriber row.
    Used to roll back subscribe flow if confirmation email sending fails.
    """
    email = (email or "").strip().lower()
    token = (confirm_token or "").strip()
    if not email or not token:
        return False
    conn = _ensure_db()
    try:
        cur = conn.execute(
            """
            DELETE FROM newsletter_subscribers
            WHERE email = ? AND confirm_token = ? AND confirmed_at IS NULL
            """,
            (email, token),
        )
        conn.commit()
        if cur.rowcount > 0:
            logger.info("Newsletter: rolled back pending subscriber for %s after failed confirmation send", email)
        return cur.rowcount > 0
    finally:
        conn.close()


def confirm_subscription(confirm_token: str) -> dict | None:
    """
    Set confirmed_at for the subscriber with the given confirm_token.
    Returns {"email": ..., "conflict": ...} if updated, else None.
    """
    if not (confirm_token or "").strip():
        return None
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    tok = confirm_token.strip()
    conn = _ensure_db()
    try:
        cur = conn.execute(
            "SELECT email, conflict FROM newsletter_subscribers WHERE confirm_token = ? AND confirmed_at IS NULL",
            (tok,),
        )
        row = cur.fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE newsletter_subscribers SET confirmed_at = ? WHERE confirm_token = ? AND confirmed_at IS NULL",
            (now, tok),
        )
        conn.commit()
        return {"email": row[0], "conflict": row[1]}
    finally:
        conn.close()


def remove_by_unsubscribe_token(token: str) -> tuple[bool, str | None]:
    """
    Remove subscriber by unsubscribe_token.
    Returns (True, email) if a row was deleted, (False, None) otherwise.
    """
    if not (token or "").strip():
        return (False, None)
    conn = _ensure_db()
    try:
        cur = conn.execute(
            "SELECT email FROM newsletter_subscribers WHERE unsubscribe_token = ?",
            (token.strip(),),
        )
        row = cur.fetchone()
        if not row:
            return (False, None)
        email = row[0]
        del_cur = conn.execute("DELETE FROM newsletter_subscribers WHERE unsubscribe_token = ?", (token.strip(),))
        conn.commit()
        return (del_cur.rowcount > 0, email)
    finally:
        conn.close()


def list_confirmed_subscribers(conflict: Optional[str] = None) -> List[dict]:
    """
    Return list of confirmed subscribers. Each item: {email, conflict, unsubscribe_token}.
    If conflict is set, filter by that conflict only.
    """
    conn = _ensure_db()
    try:
        if conflict:
            cur = conn.execute(
                "SELECT email, conflict, unsubscribe_token FROM newsletter_subscribers WHERE confirmed_at IS NOT NULL AND conflict = ?",
                (conflict,),
            )
        else:
            cur = conn.execute(
                "SELECT email, conflict, unsubscribe_token FROM newsletter_subscribers WHERE confirmed_at IS NOT NULL"
            )
        rows = cur.fetchall()
        return [{"email": r[0], "conflict": r[1], "unsubscribe_token": r[2]} for r in rows]
    finally:
        conn.close()


def get_conflicts_with_subscribers() -> List[str]:
    """Return distinct conflict values that have at least one confirmed subscriber."""
    conn = _ensure_db()
    try:
        cur = conn.execute(
            "SELECT DISTINCT conflict FROM newsletter_subscribers WHERE confirmed_at IS NOT NULL ORDER BY conflict"
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def try_acquire_daily_newsletter_lock() -> bool:
    """
    Mutex for the daily send so overlapping cron + in-process runs do not duplicate mail the same UTC day.
    Returns True if this invocation should run the job; False if already completed today or another run in progress.
    """
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    conn = _ensure_db()
    try:
        cur = conn.execute(
            "SELECT started_at, completed_at FROM newsletter_daily_lock WHERE day_utc = ?",
            (day,),
        )
        row = cur.fetchone()
        if row:
            started_s, completed_s = row[0], row[1]
            if completed_s:
                logger.info("Newsletter daily: already completed for %s", day)
                return False
            try:
                started = datetime.fromisoformat(started_s.replace("Z", "+00:00"))
            except ValueError:
                started = now
            if now - started < timedelta(minutes=30):
                logger.info("Newsletter daily: another run in progress for %s", day)
                return False
            conn.execute("DELETE FROM newsletter_daily_lock WHERE day_utc = ?", (day,))
            conn.commit()
        now_iso = now.isoformat()
        conn.execute(
            "INSERT INTO newsletter_daily_lock (day_utc, started_at, completed_at) VALUES (?, ?, NULL)",
            (day, now_iso),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        conn.rollback()
        logger.info("Newsletter daily: lock contention for %s", day)
        return False
    finally:
        conn.close()


def mark_daily_newsletter_completed() -> None:
    """Mark today's daily newsletter run as finished (prevents duplicate sends same UTC day)."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = _ensure_db()
    try:
        conn.execute(
            "UPDATE newsletter_daily_lock SET completed_at = ? WHERE day_utc = ?",
            (now_iso, day),
        )
        conn.commit()
    finally:
        conn.close()


def clear_daily_newsletter_lock_today() -> None:
    """
    Remove today's lock row (incomplete run). Use when the job acquired the lock but sent zero
    emails so cron / a later attempt can retry the same UTC day.
    """
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = _ensure_db()
    try:
        conn.execute("DELETE FROM newsletter_daily_lock WHERE day_utc = ?", (day,))
        conn.commit()
    finally:
        conn.close()


def remove_subscriber_by_email(email: str) -> bool:
    """
    Remove a subscriber row by email (e.g. bounce/complaint webhook). Returns True if a row was deleted.
    """
    em = (email or "").strip().lower()
    if not em:
        return False
    conn = _ensure_db()
    try:
        cur = conn.execute("DELETE FROM newsletter_subscribers WHERE email = ?", (em,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
