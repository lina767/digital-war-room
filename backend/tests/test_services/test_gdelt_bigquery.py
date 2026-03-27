"""Tests for optional GDELT BigQuery service (no live BQ in CI by default)."""

from services import gdelt_bigquery as gb


def test_terms_from_conflict_extracts_tokens():
    t = gb._terms_from_conflict("Iran nuclear sanctions", max_terms=3)
    assert "iran" in t
    assert "nuclear" in t


def test_fetch_disabled_returns_skipped(monkeypatch):
    monkeypatch.setenv("GDELT_BQ_ENABLED", "0")
    out = gb.fetch_gdelt_event_roots_summary("Iran")
    assert out.get("skipped") is True
    assert out.get("ok") is False


def test_sanitize_term_strips_junk():
    assert gb._sanitize_term("  Foo!! Bar  ") == "foo bar"
    assert gb._sanitize_term("a") is None


def test_match_sql_parameter_names():
    sql, pairs = gb._match_sql(["iran", "iraq"])
    assert "@p0" in sql and "@p1" in sql
    assert pairs == [("p0", "%iran%"), ("p1", "%iraq%")]
