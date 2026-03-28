"""
User-defined alert rules and in-app notifications (SQLite).
Tenant-scoped. Used by alert_rules_engine after each analysis persist.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.tenant_constants import get_default_tenant_id

logger = logging.getLogger(__name__)

DB_PATH = Path(
    os.getenv("ALERT_RULES_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "alert_rules.sqlite")
)


def _tenant_str(tenant_id: Optional[str] = None) -> str:
    return tenant_id or str(get_default_tenant_id())


def _ensure_sqlite() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_rules (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            conflict_substring TEXT NOT NULL DEFAULT '',
            rule_kind TEXT NOT NULL,
            keyword TEXT,
            min_escalation REAL,
            threat_levels TEXT,
            notify_email TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_notifications (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            conflict TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            fingerprint TEXT,
            created_at TEXT NOT NULL,
            read_at TEXT,
            FOREIGN KEY (rule_id) REFERENCES alert_rules(id)
        )
        """
    )
    try:
        conn.execute("ALTER TABLE alert_notifications ADD COLUMN fingerprint TEXT")
    except sqlite3.OperationalError:
        pass
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_alert_notif_tenant_created ON alert_notifications(tenant_id, created_at DESC)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_rules_tenant ON alert_rules(tenant_id)")
    conn.commit()
    return conn


def list_rules(*, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    tid = _tenant_str(tenant_id)
    with _ensure_sqlite() as conn:
        cur = conn.execute(
            "SELECT * FROM alert_rules WHERE tenant_id = ? ORDER BY updated_at DESC",
            (tid,),
        )
        return [_row_to_rule(dict(r)) for r in cur.fetchall()]


def _row_to_rule(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "enabled": bool(row["enabled"]),
        "conflict_substring": row.get("conflict_substring") or "",
        "rule_kind": row["rule_kind"],
        "keyword": row.get("keyword"),
        "min_escalation": row.get("min_escalation"),
        "threat_levels": row.get("threat_levels"),
        "notify_email": row.get("notify_email"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def create_rule(
    *,
    name: str,
    rule_kind: str,
    conflict_substring: str = "",
    keyword: Optional[str] = None,
    min_escalation: Optional[float] = None,
    threat_levels: Optional[str] = None,
    notify_email: Optional[str] = None,
    enabled: bool = True,
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    tid = _tenant_str(tenant_id)
    rid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _ensure_sqlite() as conn:
        conn.execute(
            """
            INSERT INTO alert_rules (
                id, tenant_id, name, enabled, conflict_substring, rule_kind,
                keyword, min_escalation, threat_levels, notify_email, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rid,
                tid,
                name.strip() or "Untitled rule",
                1 if enabled else 0,
                (conflict_substring or "").strip(),
                rule_kind,
                (keyword or "").strip() or None,
                min_escalation,
                (threat_levels or "").strip() or None,
                (notify_email or "").strip() or None,
                now,
                now,
            ),
        )
        conn.commit()
    return get_rule(rid, tenant_id=tid)  # type: ignore


def get_rule(rule_id: str, *, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    tid = _tenant_str(tenant_id)
    with _ensure_sqlite() as conn:
        cur = conn.execute(
            "SELECT * FROM alert_rules WHERE id = ? AND tenant_id = ?",
            (rule_id, tid),
        )
        row = cur.fetchone()
        if not row:
            return None
        return _row_to_rule(dict(row))


def update_rule(
    rule_id: str,
    *,
    name: Optional[str] = None,
    enabled: Optional[bool] = None,
    conflict_substring: Optional[str] = None,
    rule_kind: Optional[str] = None,
    keyword: Optional[str] = None,
    min_escalation: Optional[float] = None,
    threat_levels: Optional[str] = None,
    notify_email: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    tid = _tenant_str(tenant_id)
    existing = get_rule(rule_id, tenant_id=tid)
    if not existing:
        return None
    fields: List[str] = []
    vals: List[Any] = []
    if name is not None:
        fields.append("name = ?")
        vals.append(name.strip() or "Untitled rule")
    if enabled is not None:
        fields.append("enabled = ?")
        vals.append(1 if enabled else 0)
    if conflict_substring is not None:
        fields.append("conflict_substring = ?")
        vals.append(conflict_substring.strip())
    if rule_kind is not None:
        fields.append("rule_kind = ?")
        vals.append(rule_kind)
    if keyword is not None:
        fields.append("keyword = ?")
        vals.append(keyword.strip() or None)
    if min_escalation is not None:
        fields.append("min_escalation = ?")
        vals.append(min_escalation)
    if threat_levels is not None:
        fields.append("threat_levels = ?")
        vals.append(threat_levels.strip() or None)
    if notify_email is not None:
        fields.append("notify_email = ?")
        vals.append(notify_email.strip() or None)
    if not fields:
        return existing
    fields.append("updated_at = ?")
    vals.append(datetime.now(timezone.utc).isoformat())
    vals.extend([rule_id, tid])
    with _ensure_sqlite() as conn:
        conn.execute(
            f"UPDATE alert_rules SET {', '.join(fields)} WHERE id = ? AND tenant_id = ?",
            vals,
        )
        conn.commit()
    return get_rule(rule_id, tenant_id=tid)


def delete_rule(rule_id: str, *, tenant_id: Optional[str] = None) -> bool:
    tid = _tenant_str(tenant_id)
    with _ensure_sqlite() as conn:
        conn.execute("DELETE FROM alert_notifications WHERE rule_id = ? AND tenant_id = ?", (rule_id, tid))
        cur = conn.execute("DELETE FROM alert_rules WHERE id = ? AND tenant_id = ?", (rule_id, tid))
        conn.commit()
        return cur.rowcount > 0


def list_enabled_rules(*, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    tid = _tenant_str(tenant_id)
    with _ensure_sqlite() as conn:
        cur = conn.execute(
            "SELECT * FROM alert_rules WHERE tenant_id = ? AND enabled = 1",
            (tid,),
        )
        return [_row_to_rule(dict(r)) for r in cur.fetchall()]


def insert_notification(
    *,
    rule_id: str,
    conflict: str,
    title: str,
    body: str,
    payload: Dict[str, Any],
    fingerprint: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> str:
    tid = _tenant_str(tenant_id)
    nid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    fp = fingerprint or (payload.get("fingerprint") if isinstance(payload.get("fingerprint"), str) else None)
    with _ensure_sqlite() as conn:
        conn.execute(
            """
            INSERT INTO alert_notifications (
                id, tenant_id, rule_id, conflict, title, body, payload_json, fingerprint, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (nid, tid, rule_id, conflict, title, body, json.dumps(payload, default=str), fp, now),
        )
        conn.commit()
    return nid


def notification_exists_fingerprint(
    *,
    rule_id: str,
    conflict: str,
    fingerprint: str,
    tenant_id: Optional[str] = None,
    within_seconds: int = 3600,
) -> bool:
    """Dedupe: same rule+conflict+fingerprint within window."""
    tid = _tenant_str(tenant_id)
    mod = f"-{int(within_seconds)} seconds"
    with _ensure_sqlite() as conn:
        cur = conn.execute(
            """
            SELECT id FROM alert_notifications
            WHERE tenant_id = ? AND rule_id = ? AND conflict = ?
            AND fingerprint = ?
            AND datetime(created_at) > datetime('now', ?)
            LIMIT 1
            """,
            (tid, rule_id, conflict, fingerprint, mod),
        )
        return cur.fetchone() is not None


def list_notifications(*, limit: int = 50, unread_only: bool = False, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    tid = _tenant_str(tenant_id)
    q = """
        SELECT * FROM alert_notifications
        WHERE tenant_id = ?
    """
    args: List[Any] = [tid]
    if unread_only:
        q += " AND read_at IS NULL"
    q += " ORDER BY datetime(created_at) DESC LIMIT ?"
    args.append(limit)
    with _ensure_sqlite() as conn:
        cur = conn.execute(q, args)
        out = []
        for r in cur.fetchall():
            row = dict(r)
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except json.JSONDecodeError:
                payload = {}
            out.append(
                {
                    "id": row["id"],
                    "rule_id": row["rule_id"],
                    "conflict": row["conflict"],
                    "title": row["title"],
                    "body": row["body"],
                    "payload": payload,
                    "created_at": row["created_at"],
                    "read_at": row["read_at"],
                }
            )
        return out


def mark_read(notification_id: str, *, tenant_id: Optional[str] = None) -> bool:
    tid = _tenant_str(tenant_id)
    now = datetime.now(timezone.utc).isoformat()
    with _ensure_sqlite() as conn:
        cur = conn.execute(
            "UPDATE alert_notifications SET read_at = ? WHERE id = ? AND tenant_id = ? AND read_at IS NULL",
            (now, notification_id, tid),
        )
        conn.commit()
        return cur.rowcount > 0


def mark_all_read(*, tenant_id: Optional[str] = None) -> int:
    tid = _tenant_str(tenant_id)
    now = datetime.now(timezone.utc).isoformat()
    with _ensure_sqlite() as conn:
        cur = conn.execute(
            "UPDATE alert_notifications SET read_at = ? WHERE tenant_id = ? AND read_at IS NULL",
            (now, tid),
        )
        conn.commit()
        return cur.rowcount


def unread_count(*, tenant_id: Optional[str] = None) -> int:
    tid = _tenant_str(tenant_id)
    with _ensure_sqlite() as conn:
        cur = conn.execute(
            "SELECT COUNT(*) FROM alert_notifications WHERE tenant_id = ? AND read_at IS NULL",
            (tid,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0
