"""Unit tests for agents.domain_runner (partial results, timeouts, manager failure)."""

from agents.domain_runner import run_domain_with_analysts


def _analyst_ok(conflict: str):
    return {"source": "ok", "data": [conflict]}


def _analyst_error(conflict: str):
    raise ValueError("analyst failed")


def _manager(conflict: str, analyst_results: dict):
    """Manager fuses analyst results; tolerates error entries."""
    out = {"conflict": conflict, "combined": []}
    for name, data in analyst_results.items():
        if data.get("error"):
            continue
        out["combined"].append({"name": name, **data})
    return out


def test_domain_runner_partial_results():
    """One analyst ok, one error: manager receives both; result contains only ok (no crash)."""
    result = run_domain_with_analysts(
        "Iran",
        analysts=[
            ("a_ok", _analyst_ok),
            ("a_fail", _analyst_error),
        ],
        manager=_manager,
        analyst_timeout_s=5.0,
    )
    assert result["conflict"] == "Iran"
    assert len(result["combined"]) == 1
    assert result["combined"][0]["name"] == "a_ok"


def test_domain_runner_all_ok():
    """All analysts ok: manager gets full results."""
    result = run_domain_with_analysts(
        "Ukraine",
        analysts=[("x", _analyst_ok), ("y", _analyst_ok)],
        manager=_manager,
        analyst_timeout_s=5.0,
    )
    assert result["conflict"] == "Ukraine"
    assert len(result["combined"]) == 2


def test_domain_runner_manager_receives_error_entries():
    """Manager is called with analyst_results that include error entries."""
    collected = {}

    def _manager_snap(conflict: str, analyst_results: dict):
        collected["results"] = analyst_results
        return _manager(conflict, analyst_results)

    run_domain_with_analysts(
        "Test",
        analysts=[("ok", _analyst_ok), ("err", _analyst_error)],
        manager=_manager_snap,
        analyst_timeout_s=5.0,
    )
    assert "ok" in collected["results"]
    assert collected["results"]["ok"].get("source") == "ok"
    assert "err" in collected["results"]
    assert "error" in collected["results"]["err"]
