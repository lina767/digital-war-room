"""
Layer 2 entity resolver with durable UUIDs.

Starts with vessel resolution:
- canonical key priority: IMO -> MMSI -> normalized name
- Postgres when DATABASE_URL is usable
- SQLite fallback for local/dev
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from services.pg_sync import connection, use_postgres
from services.tenant_constants import get_default_tenant_id

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("ENTITY_RESOLVER_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "entities.sqlite"))

_IMO_RE = re.compile(r"\b\d{7}\b")
_MMSI_RE = re.compile(r"\b\d{9}\b")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_name(name: Any) -> str:
    s = str(name or "").strip()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    return s[:240]


def _extract_imo(vessel: dict[str, Any]) -> Optional[str]:
    for key in ("imo", "imo_number", "imoNo"):
        v = vessel.get(key)
        if v is None:
            continue
        m = _IMO_RE.search(str(v))
        if m:
            return m.group(0)
    return None


def _extract_mmsi(vessel: dict[str, Any]) -> Optional[str]:
    for key in ("mmsi", "MMSI"):
        v = vessel.get(key)
        if v is None:
            continue
        m = _MMSI_RE.search(str(v))
        if m:
            return m.group(0)
    return None


def _ensure_sqlite() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            canonical_name TEXT NOT NULL,
            identifiers_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_entities_tenant_type_name
        ON entities (tenant_id, entity_type, canonical_name)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_tenant_type_imo
        ON entities (tenant_id, entity_type, json_extract(identifiers_json, '$.imo'))
        WHERE json_extract(identifiers_json, '$.imo') IS NOT NULL
          AND json_extract(identifiers_json, '$.imo') <> ''
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_tenant_type_mmsi
        ON entities (tenant_id, entity_type, json_extract(identifiers_json, '$.mmsi'))
        WHERE json_extract(identifiers_json, '$.mmsi') IS NOT NULL
          AND json_extract(identifiers_json, '$.mmsi') <> ''
        """
    )
    conn.commit()
    return conn


def _upsert_postgres(
    *,
    tenant_id: str,
    canonical_name: str,
    identifiers: dict[str, Any],
    metadata: dict[str, Any],
) -> Optional[str]:
    imo = str(identifiers.get("imo") or "").strip() or None
    mmsi = str(identifiers.get("mmsi") or "").strip() or None
    now_iso = _utc_now_iso()

    try:
        from psycopg.types.json import Jsonb

        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.active_tenant_id', %s, true)", (tenant_id,))
                # Lookup precedence: IMO -> MMSI -> canonical_name
                if imo:
                    cur.execute(
                        """
                        SELECT id::text FROM entities
                        WHERE tenant_id = %s::uuid
                          AND entity_type = 'vessel'
                          AND identifiers->>'imo' = %s
                        LIMIT 1
                        """,
                        (tenant_id, imo),
                    )
                    row = cur.fetchone()
                    if row:
                        cur.execute(
                            """
                            UPDATE entities
                            SET canonical_name = CASE WHEN canonical_name = '' THEN %s ELSE canonical_name END,
                                identifiers = entities.identifiers || %s::jsonb,
                                metadata_json = entities.metadata_json || %s::jsonb,
                                last_seen_at = %s::timestamptz
                            WHERE id = %s::uuid
                            """,
                            (canonical_name, Jsonb(identifiers), Jsonb(metadata), now_iso, row[0]),
                        )
                        conn.commit()
                        return str(row[0])
                if mmsi:
                    cur.execute(
                        """
                        SELECT id::text FROM entities
                        WHERE tenant_id = %s::uuid
                          AND entity_type = 'vessel'
                          AND identifiers->>'mmsi' = %s
                        LIMIT 1
                        """,
                        (tenant_id, mmsi),
                    )
                    row = cur.fetchone()
                    if row:
                        cur.execute(
                            """
                            UPDATE entities
                            SET canonical_name = CASE WHEN canonical_name = '' THEN %s ELSE canonical_name END,
                                identifiers = entities.identifiers || %s::jsonb,
                                metadata_json = entities.metadata_json || %s::jsonb,
                                last_seen_at = %s::timestamptz
                            WHERE id = %s::uuid
                            """,
                            (canonical_name, Jsonb(identifiers), Jsonb(metadata), now_iso, row[0]),
                        )
                        conn.commit()
                        return str(row[0])
                if canonical_name:
                    cur.execute(
                        """
                        SELECT id::text FROM entities
                        WHERE tenant_id = %s::uuid
                          AND entity_type = 'vessel'
                          AND canonical_name = %s
                        LIMIT 1
                        """,
                        (tenant_id, canonical_name),
                    )
                    row = cur.fetchone()
                    if row:
                        cur.execute(
                            """
                            UPDATE entities
                            SET identifiers = entities.identifiers || %s::jsonb,
                                metadata_json = entities.metadata_json || %s::jsonb,
                                last_seen_at = %s::timestamptz
                            WHERE id = %s::uuid
                            """,
                            (Jsonb(identifiers), Jsonb(metadata), now_iso, row[0]),
                        )
                        conn.commit()
                        return str(row[0])

                entity_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO entities
                        (id, tenant_id, entity_type, canonical_name, identifiers, metadata_json, first_seen_at, last_seen_at)
                    VALUES
                        (%s::uuid, %s::uuid, 'vessel', %s, %s::jsonb, %s::jsonb, %s::timestamptz, %s::timestamptz)
                    """,
                    (entity_id, tenant_id, canonical_name, Jsonb(identifiers), Jsonb(metadata), now_iso, now_iso),
                )
            conn.commit()
        return entity_id
    except Exception as e:
        logger.warning("entity_resolver postgres upsert failed: %s", e)
        return None


def _upsert_sqlite(
    *,
    tenant_id: str,
    canonical_name: str,
    identifiers: dict[str, Any],
    metadata: dict[str, Any],
) -> Optional[str]:
    imo = str(identifiers.get("imo") or "").strip() or None
    mmsi = str(identifiers.get("mmsi") or "").strip() or None
    now_iso = _utc_now_iso()
    conn = _ensure_sqlite()
    try:
        row = None
        if imo:
            row = conn.execute(
                """
                SELECT id, identifiers_json, metadata_json FROM entities
                WHERE tenant_id = ? AND entity_type = 'vessel'
                  AND json_extract(identifiers_json, '$.imo') = ?
                LIMIT 1
                """,
                (tenant_id, imo),
            ).fetchone()
        if row is None and mmsi:
            row = conn.execute(
                """
                SELECT id, identifiers_json, metadata_json FROM entities
                WHERE tenant_id = ? AND entity_type = 'vessel'
                  AND json_extract(identifiers_json, '$.mmsi') = ?
                LIMIT 1
                """,
                (tenant_id, mmsi),
            ).fetchone()
        if row is None and canonical_name:
            row = conn.execute(
                """
                SELECT id, identifiers_json, metadata_json FROM entities
                WHERE tenant_id = ? AND entity_type = 'vessel' AND canonical_name = ?
                LIMIT 1
                """,
                (tenant_id, canonical_name),
            ).fetchone()

        if row is not None:
            entity_id = str(row[0])
            old_identifiers = json.loads(row[1]) if row[1] else {}
            old_metadata = json.loads(row[2]) if row[2] else {}
            merged_identifiers = {**old_identifiers, **identifiers}
            merged_metadata = {**old_metadata, **metadata}
            conn.execute(
                """
                UPDATE entities
                SET canonical_name = CASE WHEN canonical_name = '' THEN ? ELSE canonical_name END,
                    identifiers_json = ?,
                    metadata_json = ?,
                    last_seen_at = ?
                WHERE id = ?
                """,
                (
                    canonical_name,
                    json.dumps(merged_identifiers, separators=(",", ":"), sort_keys=True),
                    json.dumps(merged_metadata, separators=(",", ":"), sort_keys=True),
                    now_iso,
                    entity_id,
                ),
            )
            conn.commit()
            return entity_id

        entity_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO entities
                (id, tenant_id, entity_type, canonical_name, identifiers_json, metadata_json, first_seen_at, last_seen_at)
            VALUES (?, ?, 'vessel', ?, ?, ?, ?, ?)
            """,
            (
                entity_id,
                tenant_id,
                canonical_name,
                json.dumps(identifiers, separators=(",", ":"), sort_keys=True),
                json.dumps(metadata, separators=(",", ":"), sort_keys=True),
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        return entity_id
    except Exception as e:
        logger.warning("entity_resolver sqlite upsert failed: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass
        return None
    finally:
        conn.close()


def resolve_vessel_entity(
    vessel: dict[str, Any],
    tenant_id: uuid.UUID | str | None = None,
) -> Optional[str]:
    """
    Resolve one vessel to a stable entity UUID.

    Resolution precedence:
    1) IMO
    2) MMSI
    3) normalized vessel name
    """
    if not isinstance(vessel, dict):
        return None

    tid = str(tenant_id) if tenant_id else str(get_default_tenant_id())
    canonical_name = _normalize_name(vessel.get("name") or vessel.get("ship_name") or vessel.get("vessel_name"))
    if not canonical_name:
        canonical_name = _normalize_name(vessel.get("mmsi") or vessel.get("imo") or "unknown-vessel")

    identifiers: dict[str, Any] = {}
    imo = _extract_imo(vessel)
    mmsi = _extract_mmsi(vessel)
    if imo:
        identifiers["imo"] = imo
    if mmsi:
        identifiers["mmsi"] = mmsi

    metadata = {
        "last_observed_lat": vessel.get("lat"),
        "last_observed_lon": vessel.get("lon"),
        "last_observed_ts": vessel.get("timestamp") or vessel.get("seen"),
    }
    if vessel.get("flag"):
        metadata["flag"] = vessel.get("flag")
    if vessel.get("ship_type"):
        metadata["ship_type"] = vessel.get("ship_type")

    if use_postgres():
        entity_id = _upsert_postgres(
            tenant_id=tid,
            canonical_name=canonical_name,
            identifiers=identifiers,
            metadata=metadata,
        )
        if entity_id:
            return entity_id

    return _upsert_sqlite(
        tenant_id=tid,
        canonical_name=canonical_name,
        identifiers=identifiers,
        metadata=metadata,
    )
