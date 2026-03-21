"""Smoke tests for HTTP mock fixtures (respx)."""

import asyncio

import services.proximity_correlation as proximity_correlation
import services.http_client as http_client


def test_mock_resend_api_shared_client(mock_resend_api):
    async def run():
        await http_client.close_http_client()
        client = http_client.get_http_client()
        r = await client.request(
            "POST",
            "https://api.resend.com/emails",
            json={"from": "noreply@example.com", "to": ["u@example.com"], "subject": "t"},
        )
        assert r.status_code == 200
        assert r.json().get("id") == "re_mock_email"
        await http_client.close_http_client()

    asyncio.run(run())


def test_mock_overpass_interpreter(mock_overpass_interpreter):
    proximity_correlation._overpass_cache.clear()

    async def run():
        facs = await proximity_correlation.fetch_overpass_context(48.8566, 2.3522)
        assert facs == []

    asyncio.run(run())
    proximity_correlation._overpass_cache.clear()
