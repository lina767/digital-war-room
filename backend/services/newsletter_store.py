"""
Newsletter subscriber store (SQLite). Double opt-in: only rows with confirmed_at set receive the daily mail.
Tenant-scoped via tenant_id (see DEFAULT_TENANT_ID). For Postgres-backed newsletter, see migration 004
and set NEWSLETTER_USE_POSTGRES=true (not implemented — SQLite remains primary when unset).
"""

import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("NEWSLETTER_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "newsletter.sqlite"))
DEFAULT_NEWSLETTER_CONFLICT = (os.getenv("NEWSLETTER_DEFAULT_CONFLICT") or "Global").strip() or "Global"


def _default_tenant_str() -> str:
    from services.tenant_constants import get_default_tenant_id

    return str(get_default_tenant_id())


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
    try:
        conn.execute(
            """
            ALTER TABLE newsletter_subscribers ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '00000000-0000-4000-8000-000000000001'
            """
        )
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("DROP INDEX IF EXISTS idx_newsletter_email")
    except sqlite3.OperationalError:
        pass
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_newsletter_tenant_email ON newsletter_subscribers(tenant_id, email)"
    )
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


def add_subscriber(
    email: str, conflict: str = DEFAULT_NEWSLETTER_CONFLICT, *, tenant_id: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Add a new subscriber (unconfirmed). Returns (confirm_token, unsubscribe_token) or (None, None) if email exists.
    """
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("email is required")
    conflict = (conflict or DEFAULT_NEWSLETTER_CONFLICT).strip() or DEFAULT_NEWSLETTER_CONFLICT
    tid = tenant_id or _default_tenant_str()
    confirm_token = str(uuid.uuid4())
    unsubscribe_token = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _ensure_db()
    try:
        conn.execute(
            """
            INSERT INTO newsletter_subscribers (tenant_id, email, conflict, subscribed_at, unsubscribe_token, confirm_token, confirmed_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            (tid, email, conflict, now, unsubscribe_token, confirm_token),
        )
        conn.commit()
        return (confirm_token, unsubscribe_token)
    except sqlite3.IntegrityError:
        return (None, None)
    finally:
        conn.close()


def remove_unconfirmed_subscriber(email: str, confirm_token: str, *, tenant_id: Optional[str] = None) -> bool:
    email = (email or "").strip().lower()
    token = (confirm_token or "").strip()
    if not email or not token:
        return False
    tid = tenant_id or _default_tenant_str()
    conn = _ensure_db()
    try:
        cur = conn.execute(
            """
            DELETE FROM newsletter_subscribers
            WHERE tenant_id = ? AND email = ? AND confirm_token = ? AND confirmed_at IS NULL
            """,
            (tid, email, token),
        )
        conn.commit()
        if cur.rowcount > 0:
            logger.info("Newsletter: rolled back pending subscriber for %s after failed confirmation send", email)
        return cur.rowcount > 0
    finally:
        conn.close()


def confirm_subscription(confirm_token: str) -> dict | None:
    if not (confirm_token or "").strip():
        return None
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


def apply_resend_contact_sync(
    email: str, conflict: str, *, unsubscribed: bool, tenant_id: Optional[str] = None
) -> str:
    em = (email or "").strip().lower()
    if not em:
        return "noop"
    tid = tenant_id or _default_tenant_str()
    conn = _ensure_db()
    now = datetime.now(timezone.utc).isoformat()
    try:
        if unsubscribed:
            cur = conn.execute("DELETE FROM newsletter_subscribers WHERE tenant_id = ? AND email = ?", (tid, em))
            conn.commit()
            return "removed" if cur.rowcount else "noop"
        cur = conn.execute(
            "SELECT confirmed_at, conflict FROM newsletter_subscribers WHERE tenant_id = ? AND email = ?",
            (tid, em),
        )
        row = cur.fetchone()
        if row:
            confirmed_at, existing_conflict = row[0], row[1]
            if confirmed_at is None:
                conn.execute(
                    "UPDATE newsletter_subscribers SET confirmed_at = ?, conflict = ? WHERE tenant_id = ? AND email = ?",
                    (now, conflict, tid, em),
                )
                conn.commit()
                return "updated"
            if existing_conflict != conflict:
                conn.execute("UPDATE newsletter_subscribers SET conflict = ? WHERE tenant_id = ? AND email = ?", (conflict, tid, em))
                conn.commit()
                return "updated"
            return "noop"
        confirm_token = str(uuid.uuid4())
        unsubscribe_token = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO newsletter_subscribers (tenant_id, email, conflict, subscribed_at, unsubscribe_token, confirm_token, confirmed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (tid, em, conflict, now, unsubscribe_token, confirm_token, now),
        )
        conn.commit()
        return "inserted"
    finally:
        conn.close()


def list_confirmed_subscribers(
    conflict: Optional[str] = None, *, tenant_id: Optional[str] = None
) -> List[dict]:
    """
    If tenant_id is set, scope to that tenant. If tenant_id is None, include all tenants
    (used by the daily send job so every confirmed subscriber for a conflict receives mail).
    """
    conn = _ensure_db()
    try:
        if tenant_id is None:
            if conflict:
                cur = conn.execute(
                    "SELECT email, conflict, unsubscribe_token FROM newsletter_subscribers WHERE confirmed_at IS NOT NULL AND conflict = ?",
                    (conflict,),
                )
            else:
                cur = conn.execute(
                    "SELECT email, conflict, unsubscribe_token FROM newsletter_subscribers WHERE confirmed_at IS NOT NULL"
                )
        else:
            if conflict:
                cur = conn.execute(
                    "SELECT email, conflict, unsubscribe_token FROM newsletter_subscribers WHERE tenant_id = ? AND confirmed_at IS NOT NULL AND conflict = ?",
                    (tenant_id, conflict),
                )
            else:
                cur = conn.execute(
                    "SELECT email, conflict, unsubscribe_token FROM newsletter_subscribers WHERE tenant_id = ? AND confirmed_at IS NOT NULL",
                    (tenant_id,),
                )
        rows = cur.fetchall()
        return [{"email": r[0], "conflict": r[1], "unsubscribe_token": r[2]} for r in rows]
    finally:
        conn.close()


def get_conflicts_with_subscribers() -> List[str]:
    conn = _ensure_db()
    try:
        cur = conn.execute(
            "SELECT DISTINCT conflict FROM newsletter_subscribers WHERE confirmed_at IS NOT NULL ORDER BY conflict"
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def get_subscriber_stats() -> Dict[str, Any]:
    conn = _ensure_db()
    try:
        total = int(conn.execute("SELECT COUNT(*) FROM newsletter_subscribers").fetchone()[0])
        confirmed = int(
            conn.execute("SELECT COUNT(*) FROM newsletter_subscribers WHERE confirmed_at IS NOT NULL").fetchone()[0]
        )
        pending = total - confirmed
        cur = conn.execute(
            """
            SELECT conflict, COUNT(*) FROM newsletter_subscribers
            WHERE confirmed_at IS NOT NULL
            GROUP BY conflict ORDER BY conflict
            """
        )
        by_conflict = [{"conflict": r[0], "confirmed": int(r[1])} for r in cur.fetchall()]
        return {
            "db_path": str(DB_PATH.resolve()),
            "total_rows": total,
            "confirmed": confirmed,
            "pending": pending,
            "confirmed_by_conflict": by_conflict,
        }
    finally:
        conn.close()


def try_acquire_daily_newsletter_lock() -> bool:
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
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = _ensure_db()
    try:
        conn.execute("DELETE FROM newsletter_daily_lock WHERE day_utc = ?", (day,))
        conn.commit()
    finally:
        conn.close()


def remove_subscriber_by_email(email: str, *, tenant_id: Optional[str] = None) -> bool:
    em = (email or "").strip().lower()
    if not em:
        return False
    tid = tenant_id or _default_tenant_str()
    conn = _ensure_db()
    try:
        cur = conn.execute("DELETE FROM newsletter_subscribers WHERE tenant_id = ? AND email = ?", (tid, em))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
