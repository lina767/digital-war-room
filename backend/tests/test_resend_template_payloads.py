"""Resend template variable builders (20-variable daily cap, truncation)."""

from services.resend_template_payloads import (
    RESEND_DAILY_TEMPLATE_VAR_KEYS,
    RESEND_STRING_VAR_MAX,
    build_confirmation_template_variables,
    build_daily_briefing_template_variables,
    data_uri_to_inline_attachment,
    truncate_resend_string,
)


def test_truncate_resend_string():
    long = "x" * 5000
    out = truncate_resend_string(long, max_len=100)
    assert len(out) <= 100
    assert out.endswith("…")


def test_confirmation_variables():
    v = build_confirmation_template_variables("Iran", "https://example.com/newsletter/confirm?token=abc", reminder=False)
    assert v["CONFLICT"] == "Iran"
    assert "confirm" in v["CONFIRM_LINK"]
    assert v["IS_REMINDER"] == "no"
    v2 = build_confirmation_template_variables("Iran", "https://x", reminder=True)
    assert v2["IS_REMINDER"] == "yes"


def test_daily_template_twenty_keys():
    bd = {
        "_nl_bluf_cta": "https://x/bluf",
        "_nl_view_full": "https://x/view",
        "_nl_public_fallback": "https://x/pub",
        "_nl_finding_urls": ["https://x/f1", "https://x/f2", "", "", ""],
    }
    v = build_daily_briefing_template_variables(
        conflict="Iran",
        date_str="2026-03-28",
        summary="First sentence. Second sentence.",
        key_findings=["A", "B", "C", "D", "E"],
        briefing_payload=bd,
        threat_level="HIGH",
        escalation_score=72,
        unsubscribe_link="https://x/unsub",
        view_link="https://x/view",
        order_indices=[0, 1, 2, 3, 4],
        key_findings_context=None,
        include_infographic_cid=False,
    )
    assert set(v.keys()) == set(RESEND_DAILY_TEMPLATE_VAR_KEYS)
    assert len(v) == 20
    assert v["THREAT_LEVEL"] == "HIGH"
    assert v["ESCALATION_SCORE"] == "72"
    assert v["INFOGRAPHIC_IMG_HTML"] == ""
    for val in v.values():
        assert len(val) <= RESEND_STRING_VAR_MAX


def test_data_uri_attachment():
    # 1x1 png minimal
    b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    uri = f"data:image/png;base64,{b64}"
    att = data_uri_to_inline_attachment(uri)
    assert att is not None
    assert att["content_id"] == "dwr-daily-infographic"
    assert att["filename"] == "infographic.png"
    assert "content" in att
