"""Resend → SQLite newsletter mirror (sync-from-resend) and store helpers."""

import httpx
import pytest
from fastapi.testclient import TestClient

import services.newsletter_store as newsletter_store


def test_apply_resend_contact_sync(monkeypatch, tmp_path):
    monkeypatch.setattr(newsletter_store, "DB_PATH", tmp_path / "n.sqlite")
    assert newsletter_store.apply_resend_contact_sync("x@y.com", "Iran", unsubscribed=False) == "inserted"
    assert newsletter_store.apply_resend_contact_sync("x@y.com", "Iran", unsubscribed=False) == "noop"
    assert newsletter_store.get_subscriber_stats()["confirmed"] == 1
    assert newsletter_store.apply_resend_contact_sync("x@y.com", "Iran", unsubscribed=True) == "removed"
    assert newsletter_store.get_subscriber_stats()["confirmed"] == 0


@pytest.mark.asyncio
async def test_fetch_contacts_from_resend(monkeypatch, respx_mock):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    respx_mock.get("https://api.resend.com/contacts").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "has_more": False,
                "data": [{"id": "1", "email": "a@example.com", "first_name": "Iran", "unsubscribed": False}],
            },
        )
    )
    from services.resend_contacts import fetch_contacts_from_resend

    rows = await fetch_contacts_from_resend(segment_id="seg-uuid")
    assert len(rows) == 1
    assert rows[0]["email"] == "a@example.com"


def test_sync_from_resend_endpoint(monkeypatch, tmp_path, respx_mock):
    monkeypatch.setattr(newsletter_store, "DB_PATH", tmp_path / "n.sqlite")
    monkeypatch.setenv("NEWSLETTER_CRON_SECRET", "test-secret")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_NEWSLETTER_SEGMENT_ID", "seg-uuid-1")
    respx_mock.get("https://api.resend.com/contacts").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "has_more": False,
                "data": [
                    {"id": "1", "email": "a@example.com", "first_name": "Iran", "unsubscribed": False},
                ],
            },
        )
    )
    from main import app

    client = TestClient(app)
    r = client.post(
        "/api/newsletter/sync-from-resend",
        json={},
        headers={"X-Newsletter-Secret": "test-secret"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["fetched"] == 1
    assert body["inserted"] == 1
    assert body["removed"] == 0
    assert newsletter_store.get_subscriber_stats()["confirmed"] == 1


def test_sync_from_resend_removes_unsubscribed(monkeypatch, tmp_path, respx_mock):
    monkeypatch.setattr(newsletter_store, "DB_PATH", tmp_path / "n.sqlite")
    monkeypatch.setenv("NEWSLETTER_CRON_SECRET", "test-secret")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_NEWSLETTER_SEGMENT_ID", "seg-uuid-1")
    assert newsletter_store.apply_resend_contact_sync("x@y.com", "Iran", unsubscribed=False) == "inserted"
    respx_mock.get("https://api.resend.com/contacts").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "has_more": False,
                "data": [
                    {"id": "1", "email": "x@y.com", "first_name": "Iran", "unsubscribed": True},
                ],
            },
        )
    )
    from main import app

    client = TestClient(app)
    r = client.post(
        "/api/newsletter/sync-from-resend",
        json={},
        headers={"X-Newsletter-Secret": "test-secret"},
    )
    assert r.status_code == 200
    assert r.json()["removed"] == 1
    assert newsletter_store.get_subscriber_stats()["confirmed"] == 0
