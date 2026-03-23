"""Tests for source tiers, fusion scoring helpers, AIS anomaly heuristics."""

import time
from unittest.mock import patch

import pytest

from compliance.ais_anomaly import (
    MAX_SPEED_KN,
    analyze_ais_anomalies,
    detect_spoofing,
    detect_track_dark_gaps,
)
from quality import fusion
from quality.fusion import _Cand, _cluster_indices, _collect_candidates, _score_cluster
from quality.source_tiers import trust_for_agent_source, trust_for_source_name


def test_trust_for_source_name_tiers():
    assert trust_for_source_name("Reuters World News") >= 0.9
    assert trust_for_source_name("GDELT DOC") <= 0.7
    assert trust_for_source_name("telegram channel x") <= 0.4


def test_trust_for_agent_source():
    assert 0.2 <= trust_for_agent_source("news", "reuters.com") <= 1.0
    assert trust_for_agent_source("socmint", "") < trust_for_agent_source("news", "apnews.com")


def test_score_cluster_confirmed():
    t0 = time.time()
    cands = [
        _Cand("iran missile test reported in region", "news", "reuters", t0),
        _Cand("iran missile test coverage continues", "protest", "GDELT", t0 + 100),
    ]
    idx = [0, 1]
    out = _score_cluster(idx, cands)
    conf, sk, _, _, confirmation, _, _, _ = out
    assert len(sk) == 48
    assert 0.0 <= conf <= 1.0
    assert confirmation in ("confirmed", "unconfirmed")


def test_cluster_indices_no_embed():
    cands = [
        _Cand("aaa", "news", "x", 1.0),
        _Cand("aaa", "news", "y", 1.0),
    ]
    emb = [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
    groups = _cluster_indices(cands, emb)
    assert len(groups) == 1


def test_collect_candidates_empty():
    assert _collect_candidates({}) == []


def test_detect_spoofing_velocity_sog():
    ships = [{"mmsi": 123, "name": "T", "lat": 25.0, "lon": 55.0, "sog": MAX_SPEED_KN * 2}]
    an = detect_spoofing(ships, None)
    assert any(a.anomaly_type == "velocity_anomaly" for a in an)


def test_detect_spoofing_position_jump():
    t0 = 1_000_000.0
    prev = {99: {"lat": 10.0, "lon": 20.0, "timestamp": t0}}
    ships = [{"mmsi": 99, "name": "V", "lat": 45.0, "lon": 100.0, "timestamp": t0 + 3600.0}]
    an = detect_spoofing(ships, prev)
    assert any(a.anomaly_type == "position_jump" for a in an)


def test_analyze_ais_anomalies_no_db():
    sig = {"ships": [{"mmsi": 1, "lat": 26.0, "lon": 56.0, "timestamp": time.time()}]}
    out = analyze_ais_anomalies(sig, None, None, conflict="Iran")
    assert isinstance(out, list)


@patch("compliance.ais_anomaly._fetch_track_history_sync")
def test_detect_track_dark_gaps(mock_hist):
    from datetime import datetime, timedelta, timezone

    t1 = datetime.now(timezone.utc)
    t0 = t1 - timedelta(hours=12)
    mock_hist.return_value = [(t1, 26.0, 56.0), (t0, 26.1, 56.1)]
    with patch.dict("os.environ", {"DATABASE_URL": "postgres://x"}, clear=False):
        ships = [{"mmsi": "123", "name": "T", "lat": 26.0, "lon": 56.0}]
        gaps = detect_track_dark_gaps(ships, "Iran")
    assert isinstance(gaps, list)


def test_run_quality_fusion_no_hf_key(monkeypatch):
    monkeypatch.delenv("HUGGINGFACE_API_KEY", raising=False)
    agent_results = {
        "news": {"articles": []},
        "geoint": {},
        "protest": {},
        "socmint": {},
        "diplo": {},
    }
    out = fusion.run_quality_fusion("Iran", agent_results)
    assert "signals" in out
