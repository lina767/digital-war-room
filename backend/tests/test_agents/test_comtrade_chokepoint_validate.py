from agents.enrichments.comtrade_chokepoint_validate import run_comtrade_chokepoint_validation


def test_comtrade_validation_not_triggered_returns_structured_fallback():
    out = run_comtrade_chokepoint_validation(
        conflict="Iran",
        finint_result={"escalation_score": 10.0, "summary": "ok"},
        chokepoint_result={"chokepoints": [{"name": "Strait of Hormuz", "status": "OPEN", "disruption_risk": 10.0}]},
    )
    assert isinstance(out, dict)
    assert out.get("triggered") is False
    assert "summary" in out
    assert "validation_score" in out
    assert "_meta" in out


def test_comtrade_validation_triggered_does_not_crash_without_comtrade_lib(monkeypatch):
    # Force preview_energy_trade_flows to behave as if dependency/network failed.
    from agents import enrichments as enrichments_pkg

    # Import module under test
    mod = __import__("agents.enrichments.comtrade_chokepoint_validate", fromlist=["preview_energy_trade_flows"])
    monkeypatch.setattr(mod, "preview_energy_trade_flows", lambda **kwargs: {"ok": False, "records": [], "error": "boom"})

    out = run_comtrade_chokepoint_validation(
        conflict="Iran",
        finint_result={"escalation_score": 10.0, "summary": "ok"},
        chokepoint_result={
            "chokepoints": [{"name": "Strait of Hormuz", "status": "DISRUPTED", "disruption_risk": 80.0}]
        },
    )
    assert isinstance(out, dict)
    assert out.get("triggered") is True
    assert out.get("period")
    assert out.get("hs_codes") == ["2709", "2710"]
    assert "validation_score" in out
    assert "_meta" in out

