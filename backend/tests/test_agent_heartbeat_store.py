"""Tests for agent heartbeat store (24h error rate, snapshots)."""

import time

from services import agent_heartbeat_store as hbs


def test_error_rate_and_last_run():
    hbs._events.clear()
    now = time.time()
    for i in range(4):
        hbs._events.append(
            (
                now - i * 60,
                {
                    "agent": "finint",
                    "conflict": "Iran",
                    "outcome": "failed" if i == 0 else "ok",
                    "duration_ms": 100.0,
                    "sources_ok_ratio": 0.9,
                    "sources": [],
                },
            )
        )
    r = hbs._error_rate_for_agent("finint", 86400)
    assert r == 0.25
    last = hbs._last_run("finint")
    assert last is not None
    assert last["outcome"] == "ok"
    snap = hbs.get_ops_snapshot()
    assert snap["window_error_rate_sec"] == 86400
    fin = next(a for a in snap["agents"] if a["agent"] == "finint")
    assert fin["error_rate_24h"] == 0.25
    assert fin["runs_24h_sample"] == 4
