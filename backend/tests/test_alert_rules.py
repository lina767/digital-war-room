"""Alert rules store + engine smoke tests."""

import os
import tempfile
import uuid

import pytest


@pytest.fixture()
def alert_db(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "alerts.sqlite")
        monkeypatch.setenv("ALERT_RULES_DB_PATH", path)
        yield path


def test_create_list_rule(alert_db):
    from services import alert_rules_store as store

    tid = str(uuid.uuid4())
    r = store.create_rule(
        name="Test",
        rule_kind="escalation_min",
        min_escalation=50.0,
        tenant_id=tid,
    )
    assert r["id"]
    rules = store.list_rules(tenant_id=tid)
    assert len(rules) == 1
    assert rules[0]["name"] == "Test"


def test_evaluate_keyword(alert_db):
    from services import alert_rules_store as store
    from services.alert_rules_engine import evaluate_and_notify

    tid = str(uuid.uuid4())
    store.create_rule(
        name="kw",
        rule_kind="keyword",
        keyword="missile",
        tenant_id=tid,
    )
    result = {
        "escalation_score": 10.0,
        "threat_level": "LOW",
        "summary": "Test missile launch reported",
        "key_findings": [],
        "news": {},
    }
    n = evaluate_and_notify("Iran", result, tenant_id=tid)
    assert n >= 1
    notifs = store.list_notifications(tenant_id=tid)
    assert len(notifs) >= 1


def test_delete_rule(alert_db):
    from services import alert_rules_store as store

    tid = str(uuid.uuid4())
    r = store.create_rule(name="x", rule_kind="keyword", keyword="a", tenant_id=tid)
    assert store.delete_rule(r["id"], tenant_id=tid)
    assert store.list_rules(tenant_id=tid) == []
