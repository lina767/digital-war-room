"""
Reusable HTTP mocks for external APIs used by the backend.

Uses **respx** (see dev dependencies) to stub httpx traffic without network calls.
Typical usage:

    def test_something(mock_resend_api):
        ...

    @pytest.mark.asyncio
    async def test_overpass(mock_overpass_interpreter):
        ...
"""

from __future__ import annotations

import httpx
import pytest
from respx import MockRouter

from services.proximity_correlation import OVERPASS_URLS

# --- Resend (api.resend.com) -------------------------------------------------

_RESEND_EMAILS = "https://api.resend.com/emails"
_RESEND_AUDIENCE_CONTACTS = r"https://api\.resend\.com/audiences/[^/]+/contacts"
_RESEND_CONTACT_SEGMENTS = r"https://api\.resend\.com/contacts/[^/]+/segments/[^/]+"


@pytest.fixture
def mock_resend_api(respx_mock: MockRouter) -> MockRouter:
    """Stub Resend: transactional email, audience contacts, segment membership."""
    respx_mock.post(_RESEND_EMAILS).mock(return_value=httpx.Response(200, json={"id": "re_mock_email"}))
    respx_mock.route(method="POST", url__regex=_RESEND_AUDIENCE_CONTACTS).mock(
        return_value=httpx.Response(200, json={"id": "re_mock_contact"})
    )
    respx_mock.route(method="POST", url__regex=_RESEND_CONTACT_SEGMENTS).mock(
        return_value=httpx.Response(200, json={"id": "re_mock_segment"})
    )
    return respx_mock


# --- OpenStreetMap Overpass mirrors -----------------------------------------


@pytest.fixture
def mock_overpass_interpreter(respx_mock: MockRouter) -> MockRouter:
    """Stub Overpass interpreter POSTs (empty OSM elements)."""
    body = {"elements": []}
    for url in OVERPASS_URLS:
        respx_mock.post(url).mock(return_value=httpx.Response(200, json=body))
    return respx_mock


@pytest.fixture
def mock_common_external_apis(
    respx_mock: MockRouter,
) -> MockRouter:
    """Resend + Overpass — use for tests that touch newsletter and proximity-style HTTP."""
    respx_mock.post(_RESEND_EMAILS).mock(return_value=httpx.Response(200, json={"id": "re_mock_email"}))
    respx_mock.route(method="POST", url__regex=_RESEND_AUDIENCE_CONTACTS).mock(
        return_value=httpx.Response(200, json={"id": "re_mock_contact"})
    )
    respx_mock.route(method="POST", url__regex=_RESEND_CONTACT_SEGMENTS).mock(
        return_value=httpx.Response(200, json={"id": "re_mock_segment"})
    )
    body = {"elements": []}
    for url in OVERPASS_URLS:
        respx_mock.post(url).mock(return_value=httpx.Response(200, json=body))
    return respx_mock


@pytest.fixture
def httpx_json_response():
    """Factory for ``httpx.Response`` with JSON body (use in custom respx routes)."""

    def _make(data: dict, status_code: int = 200) -> httpx.Response:
        return httpx.Response(status_code, json=data)

    return _make
