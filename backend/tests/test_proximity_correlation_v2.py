import services.proximity_correlation as pc


def test_parse_daypart_hhmm():
    assert pc._parse_daypart("1345") == "day"
    assert pc._parse_daypart("2315") == "night"


def test_vision_needed_threshold_and_semantics(monkeypatch):
    monkeypatch.setattr(pc, "PROXIMITY_VISION_ENABLED", True)
    monkeypatch.setattr(pc, "PROXIMITY_VISION_MIN_RISK", "HIGH_RISK")
    assert pc._vision_needed("HIGH_RISK", {"intensity": 0.1}) is True
    assert pc._vision_needed("ELEVATED", {"intensity": 0.9}) is True
    assert pc._vision_needed("ELEVATED", {"intensity": 0.1}) is False


def test_dynamic_risk_synthesis_outputs_confidence():
    out = pc._dynamic_risk_synthesis(
        base_risk="HIGH_RISK",
        distance_m=95.0,
        facility_type="school",
        semantic={"intensity": 0.8},
        vision={"supports_tag": True, "confidence": 0.8},
        acquired="2026-03-27T12:10:00Z",
    )
    assert 0.0 <= out["risk_confidence"] <= 1.0
    assert out["risk_label_dynamic"] in {"CRITICAL_PROXIMITY", "HIGH_RISK", "ELEVATED", "LOW_CONFIDENCE"}
    assert out["daypart"] == "day"


def test_distance_to_geometry_fallback_when_no_geometry():
    fac = {"lat": 33.0, "lon": 35.0, "geometry": []}
    d, method = pc._distance_to_geometry_m(33.0001, 35.0001, fac)
    assert d > 0
    assert method == "haversine_center"
