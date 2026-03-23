"""
Daily agent score history for temporal reasoning (trends, day-over-day delta).

Stores one row per (conflict, agent, UTC calendar day). Uses PostgreSQL when
DATABASE_URL is set (see migrations/005_agent_score_history.sql); otherwise
SQLite under backend/data/agent_score_history.sqlite.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.pg_sync import connection, use_postgres

logger = logging.getLogger(__name__)

TRACKED_AGENT_KEYS: Tuple[str, ...] = (
    "finint",
    "sigint",
    "news",
    "geoint",
    "satintel",
    "socmint",
    "techint",
    "cyber",
    "energy",
    "protest",
    "diplo",
    "proximity",
    "chokepoint",
)

DB_PATH = Path(
    os.getenv("AGENT_SCORE_HISTORY_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "agent_score_history.sqlite")
)
RETENTION_DAYS = int(os.getenv("AGENT_SCORE_HISTORY_RETENTION_DAYS", "120"))


def normalize_conflict_key(conflict: str) -> str:
    s = (conflict or "").strip().lower()
    if len(s) > 240:
        s = s[:240]
    return s or "unknown"


def _ensure_sqlite() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_daily_scores (
            conflict_key TEXT NOT NULL,
            agent_key TEXT NOT NULL,
            day_utc TEXT NOT NULL,
            score REAL NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (conflict_key, agent_key, day_utc)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_daily_conflict_day ON agent_daily_scores(conflict_key, day_utc)"
    )
    conn.commit()
    return conn


def _prune_old_rows_sqlite(conn: sqlite3.Connection, conflict_key: str, keep_from_day: date) -> None:
    conn.execute(
        "DELETE FROM agent_daily_scores WHERE conflict_key = ? AND day_utc < ?",
        (conflict_key, keep_from_day.isoformat()),
    )


def _linear_slope(points: List[float]) -> float:
    """Least-squares slope for x = 0..n-1; empty -> 0.0."""
    n = len(points)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(points) / n
    num = sum((i - mean_x) * (points[i] - mean_y) for i in range(n))
    den = sum((i - mean_x) ** 2 for i in range(n))
    return float(num / den) if den else 0.0


def _consecutive_direction(series: List[Optional[float]], direction: str) -> int:
    """series oldest->newest; count consecutive steps from the last day backward."""
    if len(series) < 2:
        return 0
    count = 0
    for i in range(len(series) - 1, 0, -1):
        a, b = series[i], series[i - 1]
        if a is None or b is None:
            break
        if direction == "up" and a > b:
            count += 1
        elif direction == "down" and a < b:
            count += 1
        else:
            break
    return count


def _trend_label(slope: float, n_valid: int) -> str:
    if n_valid < 3:
        return "insufficient_data"
    if slope > 0.35:
        return "rising"
    if slope < -0.35:
        return "falling"
    return "stable"


def load_scores_for_days(conflict_key: str, days: List[date]) -> Dict[Tuple[str, str], float]:
    """Return map (agent_key, day_iso) -> score from DB."""
    if not days:
        return {}
    if use_postgres():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT agent_key, day_utc::text, score FROM agent_daily_scores
                    WHERE conflict_key = %s AND day_utc = ANY(%s::date[])
                    """,
                    (conflict_key, list(days)),
                )
                rows = cur.fetchall()
        out: Dict[Tuple[str, str], float] = {}
        for agent_key, day_utc, score in rows:
            out[(str(agent_key), str(day_utc))] = float(score)
        return out
    day_strs = [d.isoformat() for d in days]
    placeholders = ",".join("?" * len(day_strs))
    conn = _ensure_sqlite()
    try:
        cur = conn.execute(
            f"""
            SELECT agent_key, day_utc, score FROM agent_daily_scores
            WHERE conflict_key = ? AND day_utc IN ({placeholders})
            """,
            (conflict_key, *day_strs),
        )
        out = {}
        for agent_key, day_utc, score in cur.fetchall():
            out[(str(agent_key), str(day_utc))] = float(score)
        return out
    finally:
        conn.close()


def get_temporal_context(conflict: str, current_scores: Dict[str, float]) -> Dict[str, Any]:
    """
    Build supervisor-facing temporal summary: delta vs prior UTC day and 7-day trend
    per agent. Today's value uses current_scores (this run), not yet persisted.
    """
    conflict_key = normalize_conflict_key(conflict)
    today = datetime.now(timezone.utc).date()
    window_days = [today - timedelta(days=6 - i) for i in range(7)]
    prior_day = today - timedelta(days=1)

    try:
        raw = load_scores_for_days(conflict_key, window_days)
    except Exception as e:
        logger.warning("agent_score_history load failed: %s", e)
        raw = {}

    agents_out: Dict[str, Any] = {}
    for agent in TRACKED_AGENT_KEYS:
        cur = float(current_scores.get(agent, 0.0))
        series: List[Optional[float]] = []
        for d in window_days:
            if d == today:
                series.append(cur)
            else:
                key = (agent, d.isoformat())
                series.append(raw.get(key))
        prior_val = raw.get((agent, prior_day.isoformat()))
        if prior_val is not None:
            delta_prior_day = round(cur - prior_val, 2)
        else:
            delta_prior_day = None

        numeric = [x for x in series if x is not None]
        slope = _linear_slope(numeric) if len(numeric) >= 2 else 0.0
        n_valid = len(numeric)
        trend_7d = _trend_label(slope, n_valid)

        agents_out[agent] = {
            "score_now": round(cur, 2),
            "delta_vs_prior_utc_day": delta_prior_day,
            "prior_utc_day_score": round(prior_val, 2) if prior_val is not None else None,
            "trend_7d": trend_7d,
            "slope_7d_per_day": round(slope, 3) if n_valid >= 3 else None,
            "consecutive_days_up": _consecutive_direction(series, "up"),
            "consecutive_days_down": _consecutive_direction(series, "down"),
            "daily_scores_7d": [
                {"day_utc": window_days[i].isoformat(), "score": (round(s, 2) if s is not None else None)}
                for i, s in enumerate(series)
            ],
        }

    return {
        "as_of_utc_day": today.isoformat(),
        "prior_utc_day": prior_day.isoformat(),
        "agents": agents_out,
    }


def record_daily_scores(conflict: str, scores: Dict[str, float]) -> None:
    """Upsert today's UTC daily scores for each tracked agent (last write wins)."""
    conflict_key = normalize_conflict_key(conflict)
    day = datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc).isoformat()
    keep_from = datetime.now(timezone.utc).date() - timedelta(days=RETENTION_DAYS)

    if use_postgres():
        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    for agent in TRACKED_AGENT_KEYS:
                        if agent not in scores:
                            continue
                        try:
                            v = float(scores[agent])
                        except (TypeError, ValueError):
                            continue
                        cur.execute(
                            """
                            INSERT INTO agent_daily_scores (conflict_key, agent_key, day_utc, score, updated_at)
                            VALUES (%s, %s, %s, %s, %s::timestamptz)
                            ON CONFLICT (conflict_key, agent_key, day_utc) DO UPDATE SET
                                score = EXCLUDED.score,
                                updated_at = EXCLUDED.updated_at
                            """,
                            (conflict_key, agent, day, v, now),
                        )
                    cur.execute(
                        "DELETE FROM agent_daily_scores WHERE conflict_key = %s AND day_utc < %s::date",
                        (conflict_key, keep_from),
                    )
                conn.commit()
        except Exception as e:
            logger.warning("agent_score_history record failed: %s", e)
        return

    conn = _ensure_sqlite()
    try:
        for agent in TRACKED_AGENT_KEYS:
            if agent not in scores:
                continue
            try:
                v = float(scores[agent])
            except (TypeError, ValueError):
                continue
            conn.execute(
                """
                INSERT INTO agent_daily_scores (conflict_key, agent_key, day_utc, score, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(conflict_key, agent_key, day_utc) DO UPDATE SET
                    score = excluded.score,
                    updated_at = excluded.updated_at
                """,
                (conflict_key, agent, day.isoformat(), v, now),
            )
        _prune_old_rows_sqlite(conn, conflict_key, keep_from)
        conn.commit()
    except Exception as e:
        logger.warning("agent_score_history record failed: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()


# Backwards-compatible name for tests
def _ensure_db() -> sqlite3.Connection:
    return _ensure_sqlite()
