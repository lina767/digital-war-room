"""
Tracked URLs for newsletter CTAs (UTM + dashboard deep-link params + public fallback).

All newsletter links use a consistent UTM signature for analytics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

# Dashboard left-panel agent labels (must match AGENTS_WITH_SOURCES .name in frontend).
_AGENT_INFERENCE: List[tuple[str, tuple[str, ...]]] = [
    ("SIGINT", ("sigint", "aircraft", "ads-b", "adsb", "ship", "vessel", "ais", "tanker", "hormuz", "flight")),
    ("NEWS", ("news", "media", "journalist", "headline", "reporting", "press")),
    ("GEOINT", ("geoint", "satellite", "thermal", "firms", "imagery")),
    ("FININT", ("finint", "brent", "wti", "oil", "market", "polymarket", "gold")),
    ("CYBER", ("cyber", "cisa", "kev", "exploit", "malware", "shodan")),
    ("ENERGY", ("energy", "commodit", "storage", "eia")),
    ("PROTEST", ("protest", "riot", "acled", "unrest")),
    ("DIPLO", ("diplo", "sanction", "ofac", "icj", "un ")),
    ("TECHINT", ("techint", "ioda", "ooni", "outage", "internet")),
    ("COMPLIANCE", ("compliance", "geofenc", "sanction", "ofac")),
    ("CHOKEPOINT", ("chokepoint", "strait", "hormuz")),
    ("PROXIMITY", ("proximity", "civilian", "infrastructure")),
    ("SOCMINT", ("socmint", "telegram", "reddit", "social")),
]


def utm_campaign_for_date(date_str: str) -> str:
    return f"daily-briefing-{date_str}"


def _merge_query(url: str, params: Dict[str, str]) -> str:
    parsed = urlparse(url)
    q = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for k, v in params.items():
        if v is not None and v != "":
            q[k] = v
    new_query = urlencode(q, quote_via=quote, safe="")
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def build_tracked_url(
    base_url: str,
    path: str,
    *,
    date_str: str,
    utm_content: str,
    extra_query: Optional[Dict[str, str]] = None,
) -> str:
    """
    Absolute URL on the frontend with UTM params and optional extra query keys.
    """
    root = (base_url or "").rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    url = f"{root}{p}"
    q: Dict[str, str] = {
        "utm_source": "newsletter",
        "utm_medium": "email",
        "utm_campaign": utm_campaign_for_date(date_str),
        "utm_content": utm_content,
    }
    if extra_query:
        for k, v in extra_query.items():
            if v is not None and v != "":
                q[k] = v
    return _merge_query(url, q)


def infer_agent_panel_from_finding(text: str) -> str:
    """Return dashboard agent display name (e.g. SIGINT) or empty string."""
    t = (text or "").lower()
    for name, kws in _AGENT_INFERENCE:
        if any(k in t for k in kws):
            return name
    return ""


def build_newsletter_link_bundle(
    *,
    base_url: str,
    conflict: str,
    date_str: str,
    key_findings: List[str],
    finding_display_indices: List[int],
) -> Dict[str, Any]:
    """
    All tracked links for a single daily send. finding_display_indices maps display order -> source index in key_findings.
    """
    conflict_q = (conflict or "").strip()
    finding_urls: List[str] = []
    for disp_i, src_i in enumerate(finding_display_indices[:5], start=1):
        raw = key_findings[src_i] if 0 <= src_i < len(key_findings) else ""
        agent = infer_agent_panel_from_finding(str(raw))
        extra: Dict[str, str] = {"conflict": conflict_q}
        if agent:
            extra["nl_agent"] = agent
        dashboard = build_tracked_url(
            base_url,
            "/app/dashboard",
            date_str=date_str,
            utm_content=f"finding_{disp_i}",
            extra_query=extra,
        )
        finding_urls.append(dashboard)

    bluf_extra: Dict[str, str] = {"conflict": conflict_q}
    bluf_cta = build_tracked_url(
        base_url,
        "/app/dashboard",
        date_str=date_str,
        utm_content="bluf_primary_cta",
        extra_query=bluf_extra,
    )
    infographic_cta = build_tracked_url(
        base_url,
        "/app/dashboard",
        date_str=date_str,
        utm_content="infographic_cta",
        extra_query=bluf_extra,
    )
    view_full = build_tracked_url(
        base_url,
        "/daily-briefing",
        date_str=date_str,
        utm_content="view_full_briefing",
        extra_query={"nl_section": "briefing-summary"},
    )
    public_fallback = build_tracked_url(
        base_url,
        "/daily-briefing",
        date_str=date_str,
        utm_content="public_briefing_fallback",
        extra_query={"nl_section": "briefing-developments"},
    )
    return {
        "bluf_cta": bluf_cta,
        "infographic_cta": infographic_cta,
        "view_full": view_full,
        "finding_urls": finding_urls,
        "public_briefing_fallback": public_fallback,
    }


def digest_row_url(base_url: str, date_str: str, row_index: int) -> str:
    return build_tracked_url(
        base_url,
        "/daily-briefing",
        date_str=date_str,
        utm_content=f"digest_row_{row_index}",
        extra_query={"nl_section": "briefing-developments"},
    )
