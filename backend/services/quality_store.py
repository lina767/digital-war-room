"""
Postgres persistence for quality_signals and ais_track_samples.
Schema created on first use (same pattern as analysis_audit_store).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

_SCHEMA_SQL = (Path(__file__).resolve().parent.parent / "migrations" / "002_quality_signals_ais_tracks.sql").read_text(
    encoding="utf-8"
)

AIS_TRACK_RETENTION_DAYS = int(os.getenv("AIS_TRACK_RETENTION_DAYS", "30"))


async def _connect():
    import asyncpg

    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return None
    return await asyncpg.connect(url, timeout=10.0)


async def ensure_quality_schema(conn) -> None:
    """Run migration DDL idempotently."""
    await conn.execute(_SCHEMA_SQL)


async def upsert_quality_signals(conflict: str, rows: Sequence[Dict[str, Any]]) -> None:
    """Insert or update fused signal rows."""
    if not rows:
        return
    conn = await _connect()
    if not conn:
        return
    try:
        await ensure_quality_schema(conn)
        for r in rows:
            await conn.execute(
                """
                INSERT INTO quality_signals (
                    conflict, signal_key, canonical_text, first_seen_utc, last_seen_utc,
                    source_agents, lat, lon, confidence, confirmation, decay_state, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, NOW())
                ON CONFLICT (conflict, signal_key) DO UPDATE SET
                    first_seen_utc = LEAST(quality_signals.first_seen_utc, EXCLUDED.first_seen_utc),
                    last_seen_utc = GREATEST(quality_signals.last_seen_utc, EXCLUDED.last_seen_utc),
                    source_agents = EXCLUDED.source_agents,
                    lat = COALESCE(EXCLUDED.lat, quality_signals.lat),
                    lon = COALESCE(EXCLUDED.lon, quality_signals.lon),
                    confidence = EXCLUDED.confidence,
                    confirmation = EXCLUDED.confirmation,
                    decay_state = CASE
                        WHEN EXCLUDED.confirmation = 'confirmed' THEN 'active'
                        ELSE EXCLUDED.decay_state
                    END,
                    updated_at = NOW()
                """,
                conflict,
                r["signal_key"],
                r["canonical_text"],
                r["first_seen_utc"],
                r["last_seen_utc"],
                json.dumps(r.get("source_agents") or []),
                r.get("lat"),
                r.get("lon"),
                float(r.get("confidence") or 0.0),
                r.get("confirmation") or "unconfirmed",
                r.get("decay_state") or "active",
            )
    except Exception as e:
        logger.warning("quality_signals upsert failed: %s", e)
    finally:
        await conn.close()


async def apply_signal_decay(conflict: str) -> None:
    """Downgrade unconfirmed signals: >24h low_confidence, >48h stale."""
    conn = await _connect()
    if not conn:
        return
    try:
        await ensure_quality_schema(conn)
        now = datetime.now(timezone.utc)
        await conn.execute(
            """
            UPDATE quality_signals
            SET decay_state = CASE
                WHEN confirmation = 'confirmed' THEN 'active'
                WHEN first_seen_utc < $2 THEN 'stale'
                WHEN first_seen_utc < $3 THEN 'low_confidence'
                ELSE 'active'
            END,
            updated_at = NOW()
            WHERE conflict = $1
              AND confirmation = 'unconfirmed'
            """,
            conflict,
            now - timedelta(hours=48),
            now - timedelta(hours=24),
        )
    except Exception as e:
        logger.warning("apply_signal_decay failed: %s", e)
    finally:
        await conn.close()


async def fetch_quality_signals_for_conflict(
    conflict: str, *, limit: int = 100
) -> List[Dict[str, Any]]:
    conn = await _connect()
    if not conn:
        return []
    try:
        await ensure_quality_schema(conn)
        recs = await conn.fetch(
            """
            SELECT signal_key, canonical_text, first_seen_utc, last_seen_utc,
                   source_agents, lat, lon, confidence, confirmation, decay_state
            FROM quality_signals
            WHERE conflict = $1
            ORDER BY last_seen_utc DESC
            LIMIT $2
            """,
            conflict,
            limit,
        )
        out = []
        for row in recs:
            out.append(
                {
                    "signal_key": row["signal_key"],
                    "canonical_text": row["canonical_text"],
                    "first_seen_utc": row["first_seen_utc"].isoformat() if row["first_seen_utc"] else None,
                    "last_seen_utc": row["last_seen_utc"].isoformat() if row["last_seen_utc"] else None,
                    "source_agents": row["source_agents"],
                    "lat": row["lat"],
                    "lon": row["lon"],
                    "confidence": row["confidence"],
                    "confirmation": row["confirmation"],
                    "decay_state": row["decay_state"],
                }
            )
        return out
    except Exception as e:
        logger.warning("fetch_quality_signals failed: %s", e)
        return []
    finally:
        await conn.close()


async def insert_ais_track_samples(conflict: str, samples: Sequence[Dict[str, Any]]) -> None:
    if not samples:
        return
    conn = await _connect()
    if not conn:
        return
    try:
        await ensure_quality_schema(conn)
        for s in samples:
            mmsi = str(s.get("mmsi") or "")
            if not mmsi:
                continue
            ts = s.get("observed_at")
            if isinstance(ts, (int, float)):
                observed = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            elif isinstance(ts, datetime):
                observed = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
            else:
                observed = datetime.now(timezone.utc)
            lat, lon = s.get("lat"), s.get("lon")
            if lat is None or lon is None:
                continue
            await conn.execute(
                """
                INSERT INTO ais_track_samples (mmsi, conflict, observed_at, lat, lon)
                VALUES ($1, $2, $3, $4, $5)
                """,
                mmsi[:32],
                conflict[:240],
                observed,
                float(lat),
                float(lon),
            )
    except Exception as e:
        logger.warning("insert_ais_track_samples failed: %s", e)
    finally:
        await conn.close()


async def fetch_ais_track_recent(
    conflict: str, mmsi: str, *, limit: int = 40
) -> List[Tuple[datetime, float, float]]:
    conn = await _connect()
    if not conn:
        return []
    try:
        await ensure_quality_schema(conn)
        cutoff = datetime.now(timezone.utc) - timedelta(days=AIS_TRACK_RETENTION_DAYS)
        rows = await conn.fetch(
            """
            SELECT observed_at, lat, lon
            FROM ais_track_samples
            WHERE conflict = $1 AND mmsi = $2 AND observed_at >= $3
            ORDER BY observed_at DESC
            LIMIT $4
            """,
            conflict[:240],
            mmsi[:32],
            cutoff,
            limit,
        )
        return [(r["observed_at"], float(r["lat"]), float(r["lon"])) for r in rows]
    except Exception as e:
        logger.warning("fetch_ais_track_recent failed: %s", e)
        return []
    finally:
        await conn.close()


async def prune_old_ais_tracks() -> None:
    conn = await _connect()
    if not conn:
        return
    try:
        await ensure_quality_schema(conn)
        cutoff = datetime.now(timezone.utc) - timedelta(days=AIS_TRACK_RETENTION_DAYS)
        await conn.execute("DELETE FROM ais_track_samples WHERE observed_at < $1", cutoff)
    except Exception as e:
        logger.debug("prune_old_ais_tracks: %s", e)
    finally:
        await conn.close()
