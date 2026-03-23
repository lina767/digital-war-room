"""Tests for daily agent score history / temporal context."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services import agent_score_history as ash


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db = tmp_path / "t.sqlite"
    monkeypatch.setattr(ash, "DB_PATH", db)
    return db


def test_normalize_conflict_key():
    assert ash.normalize_conflict_key("  Iran–Gulf  ") == "iran–gulf"


def test_temporal_delta_and_trend(isolated_db: Path):
    conflict = "TestConflict"
    ck = ash.normalize_conflict_key(conflict)
    today = datetime.now(timezone.utc).date()
    y = today - timedelta(days=1)
    d6 = today - timedelta(days=6)

    conn = ash._ensure_db()
    try:
        for agent in ("socmint",):
            conn.execute(
                """
                INSERT INTO agent_daily_scores (conflict_key, agent_key, day_utc, score, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ck, agent, y.isoformat(), 40.0, "t"),
            )
            conn.execute(
                """
                INSERT INTO agent_daily_scores (conflict_key, agent_key, day_utc, score, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ck, agent, d6.isoformat(), 30.0, "t"),
            )
        conn.commit()
    finally:
        conn.close()

    ctx = ash.get_temporal_context(conflict, {"socmint": 45.0, **{k: 0.0 for k in ash.TRACKED_AGENT_KEYS if k != "socmint"}})
    soc = ctx["agents"]["socmint"]
    assert soc["delta_vs_prior_utc_day"] == 5.0
    assert soc["prior_utc_day_score"] == 40.0
    assert soc["trend_7d"] in ("rising", "stable", "insufficient_data")


def test_linear_slope():
    assert ash._linear_slope([0.0, 10.0]) == 10.0
    assert ash._linear_slope([10.0, 0.0]) == -10.0
