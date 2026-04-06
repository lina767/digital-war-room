"""
Newsletter subscriber store. PostgreSQL when DATABASE_URL is set (migrations 003+004);
otherwise SQLite under backend/data/newsletter.sqlite.

Double opt-in: only rows with confirmed_at set receive the daily mail. Tenant-scoped via tenant_id.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.pg_sync import connection, use_postgres
from services.tenant_constants import get_default_tenant_id

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("NEWSLETTER_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "newsletter.sqlite"))
DEFAULT_NEWSLETTER_CONFLICT = (os.getenv("NEWSLETTER_DEFAULT_CONFLICT") or "Global").strip() or "Global"


def _default_tenant_str() -> str:
    return str(get_default_tenant_id())


def _lock_tenant_uuid() -> str:
    return str(get_default_tenant_id())


def _ensure_sqlite() -> sqlite3.Connection:
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
            confirmed_at TEXT,
            reminder_sent_at TEXT
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
    try:
        conn.execute("ALTER TABLE newsletter_subscribers ADD COLUMN reminder_sent_at TEXT")
    except sqlite3.OperationalError:
        pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_daily_lock (
            day_utc TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            completed_at TEXT
        )
    """)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS newsletter_engagement_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            event_source TEXT NOT NULL,
            campaign TEXT,
            utm_content TEXT,
            conflict TEXT,
            session_id TEXT,
            path TEXT,
            meta_json TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_newsletter_engagement_created ON newsletter_engagement_events(created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_newsletter_engagement_type ON newsletter_engagement_events(event_type)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_newsletter_engagement_campaign ON newsletter_engagement_events(campaign)"
    )
    conn.commit()
    return conn


def _ensure_postgres_engagement_table() -> None:
    if not use_postgres():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS newsletter_engagement_events (
                    id BIGSERIAL PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    event_source TEXT NOT NULL,
                    campaign TEXT,
                    utm_content TEXT,
                    conflict TEXT,
                    session_id TEXT,
                    path TEXT,
                    meta_json JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_newsletter_engagement_created ON newsletter_engagement_events(created_at)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_newsletter_engagement_type ON newsletter_engagement_events(event_type)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_newsletter_engagement_campaign ON newsletter_engagement_events(campaign)"
            )
        conn.commit()


def add_subscriber(
    email: str, conflict: str = DEFAULT_NEWSLETTER_CONFLICT, *, tenant_id: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("email is required")
    conflict = (conflict or DEFAULT_NEWSLETTER_CONFLICT).strip() or DEFAULT_NEWSLETTER_CONFLICT
    tid = tenant_id or _default_tenant_str()
    confirm_token = str(uuid.uuid4())
    unsubscribe_token = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    if use_postgres():
        from psycopg import errors

        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO newsletter_subscribers
                            (tenant_id, email, conflict, subscribed_at, unsubscribe_token, confirm_token, confirmed_at)
                        VALUES (%s::uuid, %s, %s, %s::timestamptz, %s, %s, NULL)
                        """,
                        (tid, email, conflict, now.isoformat(), unsubscribe_token, confirm_token),
                    )
                conn.commit()
            return (confirm_token, unsubscribe_token)
        except errors.UniqueViolation:
            return (None, None)
    conn = _ensure_sqlite()
    try:
        conn.execute(
            """
            INSERT INTO newsletter_subscribers (tenant_id, email, conflict, subscribed_at, unsubscribe_token, confirm_token, confirmed_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            (tid, email, conflict, now.isoformat(), unsubscribe_token, confirm_token),
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
    if use_postgres():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM newsletter_subscribers
                    WHERE tenant_id = %s::uuid AND email = %s AND confirm_token = %s AND confirmed_at IS NULL
                    """,
                    (tid, email, token),
                )
                n = cur.rowcount
            conn.commit()
        if n > 0:
            logger.info("Newsletter: rolled back pending subscriber for %s after failed confirmation send", email)
        return n > 0
    conn = _ensure_sqlite()
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
    now = datetime.now(timezone.utc)
    tok = confirm_token.strip()
    if use_postgres():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT email, conflict, confirmed_at FROM newsletter_subscribers WHERE confirm_token = %s",
                    (tok,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                if row[2] is not None:
                    return {"email": row[0], "conflict": row[1], "status": "already_confirmed"}
                cur.execute(
                    "UPDATE newsletter_subscribers SET confirmed_at = %s::timestamptz WHERE confirm_token = %s AND confirmed_at IS NULL",
                    (now.isoformat(), tok),
                )
            conn.commit()
            return {"email": row[0], "conflict": row[1], "status": "confirmed"}
    conn = _ensure_sqlite()
    try:
        cur = conn.execute(
            "SELECT email, conflict, confirmed_at FROM newsletter_subscribers WHERE confirm_token = ?",
            (tok,),
        )
        row = cur.fetchone()
        if not row:
            return None
        if row[2] is not None:
            return {"email": row[0], "conflict": row[1], "status": "already_confirmed"}
        conn.execute(
            "UPDATE newsletter_subscribers SET confirmed_at = ? WHERE confirm_token = ? AND confirmed_at IS NULL",
            (now.isoformat(), tok),
        )
        conn.commit()
        return {"email": row[0], "conflict": row[1], "status": "confirmed"}
    finally:
        conn.close()


def list_pending_reminder_candidates(*, min_age_hours: int = 6, limit: int = 100) -> List[dict]:
    """
    Pending (unconfirmed) subscribers older than N hours who have not received a reminder yet.
    """
    h = max(1, int(min_age_hours))
    lim = max(1, min(1000, int(limit)))
    if use_postgres():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT tenant_id::text, email, conflict, confirm_token
                    FROM newsletter_subscribers
                    WHERE confirmed_at IS NULL
                      AND reminder_sent_at IS NULL
                      AND subscribed_at <= NOW() - (%s::text || ' hours')::interval
                    ORDER BY subscribed_at ASC
                    LIMIT %s
                    """,
                    (h, lim),
                )
                rows = cur.fetchall()
        return [{"tenant_id": r[0], "email": r[1], "conflict": r[2], "confirm_token": r[3]} for r in rows]
    conn = _ensure_sqlite()
    try:
        cur = conn.execute(
            """
            SELECT tenant_id, email, conflict, confirm_token
            FROM newsletter_subscribers
            WHERE confirmed_at IS NULL
              AND reminder_sent_at IS NULL
              AND subscribed_at <= datetime('now', ?)
            ORDER BY subscribed_at ASC
            LIMIT ?
            """,
            (f"-{h} hours", lim),
        )
        rows = cur.fetchall()
        return [{"tenant_id": r[0], "email": r[1], "conflict": r[2], "confirm_token": r[3]} for r in rows]
    finally:
        conn.close()


def mark_confirmation_reminder_sent(email: str, confirm_token: str, *, tenant_id: Optional[str] = None) -> bool:
    em = (email or "").strip().lower()
    tok = (confirm_token or "").strip()
    if not em or not tok:
        return False
    tid = tenant_id or _default_tenant_str()
    now_iso = datetime.now(timezone.utc).isoformat()
    if use_postgres():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE newsletter_subscribers
                    SET reminder_sent_at = %s::timestamptz
                    WHERE tenant_id = %s::uuid
                      AND email = %s
                      AND confirm_token = %s
                      AND confirmed_at IS NULL
                      AND reminder_sent_at IS NULL
                    """,
                    (now_iso, tid, em, tok),
                )
                n = cur.rowcount
            conn.commit()
            return n > 0
    conn = _ensure_sqlite()
    try:
        cur = conn.execute(
            """
            UPDATE newsletter_subscribers
            SET reminder_sent_at = ?
            WHERE tenant_id = ?
              AND email = ?
              AND confirm_token = ?
              AND confirmed_at IS NULL
              AND reminder_sent_at IS NULL
            """,
            (now_iso, tid, em, tok),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_reminder_status(*, min_age_hours: int = 6, preview_limit: int = 20) -> Dict[str, Any]:
    """
    Operational status for one-time confirmation reminders.
    Returns aggregate counts plus a small preview list of currently eligible recipients.
    """
    h = max(1, int(min_age_hours))
    preview = max(1, min(100, int(preview_limit)))
    if use_postgres():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM newsletter_subscribers WHERE confirmed_at IS NULL")
                pending_total = int(cur.fetchone()[0] or 0)
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM newsletter_subscribers
                    WHERE confirmed_at IS NULL
                      AND reminder_sent_at IS NOT NULL
                    """
                )
                reminded_total = int(cur.fetchone()[0] or 0)
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM newsletter_subscribers
                    WHERE confirmed_at IS NULL
                      AND reminder_sent_at IS NULL
                      AND subscribed_at <= NOW() - (%s::text || ' hours')::interval
                    """,
                    (h,),
                )
                eligible_now = int(cur.fetchone()[0] or 0)
                cur.execute(
                    """
                    SELECT email, conflict, subscribed_at
                    FROM newsletter_subscribers
                    WHERE confirmed_at IS NULL
                      AND reminder_sent_at IS NULL
                      AND subscribed_at <= NOW() - (%s::text || ' hours')::interval
                    ORDER BY subscribed_at ASC
                    LIMIT %s
                    """,
                    (h, preview),
                )
                rows = cur.fetchall()
        return {
            "min_age_hours": h,
            "pending_total": pending_total,
            "pending_reminded_total": reminded_total,
            "pending_eligible_now": eligible_now,
            "eligible_preview": [
                {"email": r[0], "conflict": r[1], "subscribed_at": r[2].isoformat() if hasattr(r[2], "isoformat") else str(r[2])}
                for r in rows
            ],
        }
    conn = _ensure_sqlite()
    try:
        pending_total = int(
            conn.execute("SELECT COUNT(*) FROM newsletter_subscribers WHERE confirmed_at IS NULL").fetchone()[0] or 0
        )
        reminded_total = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM newsletter_subscribers
                WHERE confirmed_at IS NULL
                  AND reminder_sent_at IS NOT NULL
                """
            ).fetchone()[0]
            or 0
        )
        eligible_now = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM newsletter_subscribers
                WHERE confirmed_at IS NULL
                  AND reminder_sent_at IS NULL
                  AND subscribed_at <= datetime('now', ?)
                """,
                (f"-{h} hours",),
            ).fetchone()[0]
            or 0
        )
        cur = conn.execute(
            """
            SELECT email, conflict, subscribed_at
            FROM newsletter_subscribers
            WHERE confirmed_at IS NULL
              AND reminder_sent_at IS NULL
              AND subscribed_at <= datetime('now', ?)
            ORDER BY subscribed_at ASC
            LIMIT ?
            """,
            (f"-{h} hours", preview),
        )
        rows = cur.fetchall()
        return {
            "min_age_hours": h,
            "pending_total": pending_total,
            "pending_reminded_total": reminded_total,
            "pending_eligible_now": eligible_now,
            "eligible_preview": [{"email": r[0], "conflict": r[1], "subscribed_at": r[2]} for r in rows],
        }
    finally:
        conn.close()


def remove_by_unsubscribe_token(token: str) -> tuple[bool, str | None]:
    if not (token or "").strip():
        return (False, None)
    t = token.strip()
    if use_postgres():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT email FROM newsletter_subscribers WHERE unsubscribe_token = %s", (t,))
                row = cur.fetchone()
                if not row:
                    return (False, None)
                email = row[0]
                cur.execute("DELETE FROM newsletter_subscribers WHERE unsubscribe_token = %s", (t,))
                n = cur.rowcount
            conn.commit()
            return (n > 0, email)
    conn = _ensure_sqlite()
    try:
        cur = conn.execute(
            "SELECT email FROM newsletter_subscribers WHERE unsubscribe_token = ?",
            (t,),
        )
        row = cur.fetchone()
        if not row:
            return (False, None)
        email = row[0]
        del_cur = conn.execute("DELETE FROM newsletter_subscribers WHERE unsubscribe_token = ?", (t,))
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
    now = datetime.now(timezone.utc)
    if use_postgres():
        with connection() as conn:
            with conn.cursor() as cur:
                if unsubscribed:
                    cur.execute("DELETE FROM newsletter_subscribers WHERE tenant_id = %s::uuid AND email = %s", (tid, em))
                    n = cur.rowcount
                    conn.commit()
                    return "removed" if n else "noop"
                cur.execute(
                    "SELECT confirmed_at, conflict FROM newsletter_subscribers WHERE tenant_id = %s::uuid AND email = %s",
                    (tid, em),
                )
                row = cur.fetchone()
                if row:
                    confirmed_at, existing_conflict = row[0], row[1]
                    if confirmed_at is None:
                        cur.execute(
                            """
                            UPDATE newsletter_subscribers SET confirmed_at = %s::timestamptz, conflict = %s
                            WHERE tenant_id = %s::uuid AND email = %s
                            """,
                            (now.isoformat(), conflict, tid, em),
                        )
                        conn.commit()
                        return "updated"
                    if existing_conflict != conflict:
                        cur.execute(
                            "UPDATE newsletter_subscribers SET conflict = %s WHERE tenant_id = %s::uuid AND email = %s",
                            (conflict, tid, em),
                        )
                        conn.commit()
                        return "updated"
                    conn.commit()
                    return "noop"
                confirm_token = str(uuid.uuid4())
                unsubscribe_token = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO newsletter_subscribers
                        (tenant_id, email, conflict, subscribed_at, unsubscribe_token, confirm_token, confirmed_at)
                    VALUES (%s::uuid, %s, %s, %s::timestamptz, %s, %s, %s::timestamptz)
                    """,
                    (tid, em, conflict, now.isoformat(), unsubscribe_token, confirm_token, now.isoformat()),
                )
            conn.commit()
            return "inserted"
    conn = _ensure_sqlite()
    try:
        now_iso = now.isoformat()
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
                    (now_iso, conflict, tid, em),
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
            (tid, em, conflict, now_iso, unsubscribe_token, confirm_token, now_iso),
        )
        conn.commit()
        return "inserted"
    finally:
        conn.close()


def list_confirmed_subscribers(
    conflict: Optional[str] = None, *, tenant_id: Optional[str] = None
) -> List[dict]:
    if use_postgres():
        with connection() as conn:
            with conn.cursor() as cur:
                if tenant_id is None:
                    if conflict:
                        cur.execute(
                            "SELECT email, conflict, unsubscribe_token FROM newsletter_subscribers WHERE confirmed_at IS NOT NULL AND conflict = %s",
                            (conflict,),
                        )
                    else:
                        cur.execute(
                            "SELECT email, conflict, unsubscribe_token FROM newsletter_subscribers WHERE confirmed_at IS NOT NULL"
                        )
                else:
                    if conflict:
                        cur.execute(
                            """
                            SELECT email, conflict, unsubscribe_token FROM newsletter_subscribers
                            WHERE tenant_id = %s::uuid AND confirmed_at IS NOT NULL AND conflict = %s
                            """,
                            (tenant_id, conflict),
                        )
                    else:
                        cur.execute(
                            """
                            SELECT email, conflict, unsubscribe_token FROM newsletter_subscribers
                            WHERE tenant_id = %s::uuid AND confirmed_at IS NOT NULL
                            """,
                            (tenant_id,),
                        )
                rows = cur.fetchall()
        return [{"email": r[0], "conflict": r[1], "unsubscribe_token": r[2]} for r in rows]
    conn = _ensure_sqlite()
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
    if use_postgres():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT conflict FROM newsletter_subscribers WHERE confirmed_at IS NOT NULL ORDER BY conflict"
                )
                return [row[0] for row in cur.fetchall()]
    conn = _ensure_sqlite()
    try:
        cur = conn.execute(
            "SELECT DISTINCT conflict FROM newsletter_subscribers WHERE confirmed_at IS NOT NULL ORDER BY conflict"
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def get_subscriber_stats() -> Dict[str, Any]:
    if use_postgres():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM newsletter_subscribers")
                total = int(cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM newsletter_subscribers WHERE confirmed_at IS NOT NULL")
                confirmed = int(cur.fetchone()[0])
                pending = total - confirmed
                cur.execute(
                    """
                    SELECT conflict, COUNT(*) FROM newsletter_subscribers
                    WHERE confirmed_at IS NOT NULL
                    GROUP BY conflict ORDER BY conflict
                    """
                )
                by_conflict = [{"conflict": r[0], "confirmed": int(r[1])} for r in cur.fetchall()]
        return {
            "db_path": "(postgresql)",
            "db_backend": "postgresql",
            "total_rows": total,
            "confirmed": confirmed,
            "pending": pending,
            "confirmed_by_conflict": by_conflict,
        }
    conn = _ensure_sqlite()
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
            "db_backend": "sqlite",
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
    tid = _lock_tenant_uuid()
    if use_postgres():
        from psycopg import errors

        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT started_at, completed_at FROM newsletter_daily_lock WHERE tenant_id = %s::uuid AND day_utc = %s",
                        (tid, day),
                    )
                    row = cur.fetchone()
                    if row:
                        started_s, completed_s = row[0], row[1]
                        if completed_s:
                            logger.info("Newsletter daily: already completed for %s", day)
                            return False
                        if isinstance(started_s, datetime):
                            started = started_s
                            if started.tzinfo is None:
                                started = started.replace(tzinfo=timezone.utc)
                        else:
                            try:
                                started = datetime.fromisoformat(str(started_s).replace("Z", "+00:00"))
                            except ValueError:
                                started = now
                        if now - started < timedelta(minutes=30):
                            logger.info("Newsletter daily: another run in progress for %s", day)
                            return False
                        cur.execute(
                            "DELETE FROM newsletter_daily_lock WHERE tenant_id = %s::uuid AND day_utc = %s",
                            (tid, day),
                        )
                    cur.execute(
                        """
                        INSERT INTO newsletter_daily_lock (tenant_id, day_utc, started_at, completed_at)
                        VALUES (%s::uuid, %s, %s::timestamptz, NULL)
                        """,
                        (tid, day, now.isoformat()),
                    )
                conn.commit()
            return True
        except errors.UniqueViolation:
            logger.info("Newsletter daily: lock contention for %s", day)
            return False
    conn = _ensure_sqlite()
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
        try:
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
    tid = _lock_tenant_uuid()
    if use_postgres():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE newsletter_daily_lock SET completed_at = %s::timestamptz WHERE tenant_id = %s::uuid AND day_utc = %s",
                    (now_iso, tid, day),
                )
            conn.commit()
        return
    conn = _ensure_sqlite()
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
    tid = _lock_tenant_uuid()
    if use_postgres():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM newsletter_daily_lock WHERE tenant_id = %s::uuid AND day_utc = %s",
                    (tid, day),
                )
            conn.commit()
        return
    conn = _ensure_sqlite()
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
    if use_postgres():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM newsletter_subscribers WHERE tenant_id = %s::uuid AND email = %s", (tid, em))
                n = cur.rowcount
            conn.commit()
            return n > 0
    conn = _ensure_sqlite()
    try:
        cur = conn.execute("DELETE FROM newsletter_subscribers WHERE tenant_id = ? AND email = ?", (tid, em))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def purge_pending_subscribers_older_than(days: int) -> int:
    """Delete newsletter rows that were never confirmed and are older than N days."""
    d = max(1, int(days))
    if use_postgres():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM newsletter_subscribers
                    WHERE confirmed_at IS NULL
                      AND subscribed_at < NOW() - (%s::text || ' days')::interval
                    """,
                    (d,),
                )
                n = cur.rowcount
            conn.commit()
            return int(n or 0)
    conn = _ensure_sqlite()
    try:
        cur = conn.execute(
            """
            DELETE FROM newsletter_subscribers
            WHERE confirmed_at IS NULL
              AND subscribed_at < datetime('now', ?)
            """,
            (f"-{d} days",),
        )
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def record_newsletter_engagement_event(
    *,
    event_type: str,
    event_source: str,
    campaign: Optional[str] = None,
    utm_content: Optional[str] = None,
    conflict: Optional[str] = None,
    session_id: Optional[str] = None,
    path: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    et = (event_type or "").strip().lower()
    es = (event_source or "").strip().lower()
    if not et or not es:
        return
    created_at = datetime.now(timezone.utc).isoformat()
    meta_dict = meta if isinstance(meta, dict) else {}
    if use_postgres():
        _ensure_postgres_engagement_table()
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO newsletter_engagement_events
                        (event_type, event_source, campaign, utm_content, conflict, session_id, path, meta_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::timestamptz)
                    """,
                    (
                        et,
                        es,
                        (campaign or "").strip() or None,
                        (utm_content or "").strip() or None,
                        (conflict or "").strip() or None,
                        (session_id or "").strip() or None,
                        (path or "").strip() or None,
                        json.dumps(meta_dict),
                        created_at,
                    ),
                )
            conn.commit()
        return
    conn = _ensure_sqlite()
    try:
        conn.execute(
            """
            INSERT INTO newsletter_engagement_events
                (event_type, event_source, campaign, utm_content, conflict, session_id, path, meta_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                et,
                es,
                (campaign or "").strip() or None,
                (utm_content or "").strip() or None,
                (conflict or "").strip() or None,
                (session_id or "").strip() or None,
                (path or "").strip() or None,
                json.dumps(meta_dict),
                created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_newsletter_kpi_baseline(*, days: int = 14) -> Dict[str, Any]:
    lookback_days = max(1, min(90, int(days)))
    window_start = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
    if use_postgres():
        _ensure_postgres_engagement_table()
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT event_type, COUNT(*)
                    FROM newsletter_engagement_events
                    WHERE created_at >= %s::timestamptz
                    GROUP BY event_type
                    """,
                    (window_start,),
                )
                rows = cur.fetchall()
                counts = {str(r[0]): int(r[1]) for r in rows}
                cur.execute(
                    """
                    SELECT campaign, utm_content, COUNT(*)
                    FROM newsletter_engagement_events
                    WHERE created_at >= %s::timestamptz
                      AND event_type = 'newsletter_slot_click'
                    GROUP BY campaign, utm_content
                    ORDER BY COUNT(*) DESC, campaign NULLS LAST, utm_content NULLS LAST
                    """,
                    (window_start,),
                )
                slot_rows = cur.fetchall()
                cur.execute(
                    """
                    SELECT COUNT(*), AVG((meta_json->>'ttv_seconds')::numeric)
                    FROM newsletter_engagement_events
                    WHERE created_at >= %s::timestamptz
                      AND event_type = 'ttv_recorded'
                    """,
                    (window_start,),
                )
                ttv = cur.fetchone() or (0, None)
        return {
            "window_days": lookback_days,
            "window_start_utc": window_start,
            "counts": counts,
            "ttv_samples": int(ttv[0] or 0),
            "ttv_avg_seconds": float(ttv[1]) if ttv[1] is not None else None,
            "slot_clicks": [
                {"campaign": r[0], "utm_content": r[1], "clicks": int(r[2])}
                for r in slot_rows
            ],
            "kpi_definitions": {
                "ttv_recorded": "Time from daily briefing load to first meaningful action.",
                "briefing_to_dashboard_click": "Clicks from briefing into dashboard context.",
                "newsletter_slot_click": "Briefing sessions opened from newsletter links grouped by utm_content.",
                "return_24h_after_newsletter": "User returned to briefing/dashboard within 24h after newsletter-origin session.",
            },
        }
    conn = _ensure_sqlite()
    try:
        cur = conn.execute(
            """
            SELECT event_type, COUNT(*)
            FROM newsletter_engagement_events
            WHERE created_at >= ?
            GROUP BY event_type
            """,
            (window_start,),
        )
        counts = {str(r[0]): int(r[1]) for r in cur.fetchall()}
        slot_cur = conn.execute(
            """
            SELECT campaign, utm_content, COUNT(*)
            FROM newsletter_engagement_events
            WHERE created_at >= ?
              AND event_type = 'newsletter_slot_click'
            GROUP BY campaign, utm_content
            ORDER BY COUNT(*) DESC, campaign, utm_content
            """,
            (window_start,),
        )
        ttv_cur = conn.execute(
            """
            SELECT COUNT(*), AVG(CAST(json_extract(meta_json, '$.ttv_seconds') AS REAL))
            FROM newsletter_engagement_events
            WHERE created_at >= ?
              AND event_type = 'ttv_recorded'
            """,
            (window_start,),
        )
        ttv_count, ttv_avg = ttv_cur.fetchone() or (0, None)
        return {
            "window_days": lookback_days,
            "window_start_utc": window_start,
            "counts": counts,
            "ttv_samples": int(ttv_count or 0),
            "ttv_avg_seconds": float(ttv_avg) if ttv_avg is not None else None,
            "slot_clicks": [
                {"campaign": r[0], "utm_content": r[1], "clicks": int(r[2])}
                for r in slot_cur.fetchall()
            ],
            "kpi_definitions": {
                "ttv_recorded": "Time from daily briefing load to first meaningful action.",
                "briefing_to_dashboard_click": "Clicks from briefing into dashboard context.",
                "newsletter_slot_click": "Briefing sessions opened from newsletter links grouped by utm_content.",
                "return_24h_after_newsletter": "User returned to briefing/dashboard within 24h after newsletter-origin session.",
            },
        }
    finally:
        conn.close()


def _ensure_db() -> sqlite3.Connection:
    """SQLite bootstrap; tests may monkeypatch DB_PATH. Not used when DATABASE_URL is set."""
    return _ensure_sqlite()
