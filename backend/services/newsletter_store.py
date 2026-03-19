"""
Newsletter subscriber store (SQLite). Double opt-in: only rows with confirmed_at set receive the daily mail.
"""

import logging
import os
import sqlite3
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("NEWSLETTER_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "newsletter.sqlite"))


def _ensure_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            conflict TEXT NOT NULL DEFAULT 'Iran',
            subscribed_at TEXT NOT NULL,
            unsubscribe_token TEXT NOT NULL UNIQUE,
            confirm_token TEXT NOT NULL UNIQUE,
            confirmed_at TEXT
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_newsletter_email ON newsletter_subscribers(email)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_newsletter_conflict ON newsletter_subscribers(conflict)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_newsletter_confirmed ON newsletter_subscribers(confirmed_at)")
    conn.commit()
    return conn


def add_subscriber(email: str, conflict: str = "Iran") -> Tuple[Optional[str], Optional[str]]:
    """
    Add a new subscriber (unconfirmed). Returns (confirm_token, unsubscribe_token) or (None, None) if email already exists.
    """
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("email is required")
    conflict = (conflict or "Iran").strip() or "Iran"
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


def confirm_subscription(confirm_token: str) -> bool:
    """Set confirmed_at for the subscriber with the given confirm_token. Returns True if updated."""
    if not (confirm_token or "").strip():
        return False
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    conn = _ensure_db()
    try:
        cur = conn.execute(
            "UPDATE newsletter_subscribers SET confirmed_at = ? WHERE confirm_token = ? AND confirmed_at IS NULL",
            (now, confirm_token.strip()),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def remove_by_unsubscribe_token(token: str) -> bool:
    """Remove subscriber by unsubscribe_token. Returns True if a row was deleted."""
    if not (token or "").strip():
        return False
    conn = _ensure_db()
    try:
        cur = conn.execute("DELETE FROM newsletter_subscribers WHERE unsubscribe_token = ?", (token.strip(),))
        conn.commit()
        return cur.rowcount > 0
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
