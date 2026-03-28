"""
Resend dashboard templates: variable payloads for transactional sends.

Resend limits (see https://resend.com/docs/dashboard/templates/introduction):
- At most 20 custom variables per template
- Each string variable: max 2000 characters (API reference)
- Reserved names: FIRST_NAME, LAST_NAME, EMAIL, RESEND_UNSUBSCRIBE_URL, contact, this
- Use triple mustache {{{VAR}}} in the template HTML for unescaped HTML snippets (e.g. infographic img).

Daily briefing template uses exactly 20 variables so the dashboard template can list them all.
"""

from __future__ import annotations

import base64
import re
from typing import Any, Dict, List, Optional, Tuple

# Matches Resend inline image docs (content_id < 128 chars)
DAILY_INFOGRAPHIC_CONTENT_ID = "dwr-daily-infographic"

RESEND_STRING_VAR_MAX = 2000
RESEND_DAILY_TEMPLATE_VAR_KEYS: Tuple[str, ...] = (
    "CONFLICT",
    "DATE_STR",
    "THREAT_LEVEL",
    "ESCALATION_SCORE",
    "BLUF_TEXT",
    "FINDING_1",
    "FINDING_2",
    "FINDING_3",
    "FINDING_4",
    "FINDING_5",
    "LINK_BLUF_CTA",
    "LINK_VIEW_FULL",
    "LINK_PUBLIC_FALLBACK",
    "NL_UNSUB_LINK",
    "LINK_FINDING_1",
    "LINK_FINDING_2",
    "LINK_FINDING_3",
    "LINK_FINDING_4",
    "LINK_FINDING_5",
    "INFOGRAPHIC_IMG_HTML",
)

def truncate_resend_string(value: str, max_len: int = RESEND_STRING_VAR_MAX - 10) -> str:
    """Leave margin below API limit; append ellipsis when truncated."""
    s = (value or "").strip()
    if len(s) <= max_len:
        return s
    if max_len <= 1:
        return "…"
    return s[: max_len - 1] + "…"


def _finding_lines(
    key_findings: List[str],
    order_indices: List[int],
    contexts: Optional[List[str]],
    *,
    max_findings: int = 5,
) -> List[str]:
    kf = list(key_findings or [])
    ctx = contexts if isinstance(contexts, list) else []
    out: List[str] = []
    for pos, src_i in enumerate(order_indices[:max_findings]):
        raw = (kf[src_i] if 0 <= src_i < len(kf) else "") or ""
        line = (raw or "").strip()
        if not line:
            out.append("")
            continue
        c = (ctx[src_i] if src_i < len(ctx) and isinstance(ctx[src_i], str) else "") or ""
        c = c.strip()
        if c:
            line = f"{line} — {c[:400]}"
        out.append(line)
    while len(out) < max_findings:
        out.append("")
    return out[:max_findings]


def build_confirmation_template_variables(
    conflict: str,
    confirm_link: str,
    *,
    reminder: bool = False,
) -> Dict[str, str]:
    return {
        "CONFLICT": truncate_resend_string(conflict or "Briefing"),
        "CONFIRM_LINK": truncate_resend_string(confirm_link),
        "IS_REMINDER": "yes" if reminder else "no",
    }


def build_daily_briefing_template_variables(
    *,
    conflict: str,
    date_str: str,
    summary: str,
    key_findings: List[str],
    briefing_payload: Dict[str, Any],
    threat_level: Optional[str],
    escalation_score: Any,
    unsubscribe_link: str,
    view_link: str,
    order_indices: List[int],
    key_findings_context: Optional[List[str]],
    include_infographic_cid: bool,
) -> Dict[str, str]:
    """
    Build the 20-variable map for the Resend daily briefing template (single layout only).

    When include_infographic_cid is True, INFOGRAPHIC_IMG_HTML references cid:dwr-daily-infographic;
    the caller must attach the image with that content_id on the same API request.
    """
    bd = briefing_payload if isinstance(briefing_payload, dict) else {}
    tl = (str(threat_level or bd.get("threat_level") or "ELEVATED")).strip().upper()
    if tl not in ("CRITICAL", "HIGH", "ELEVATED", "LOW", "MINIMAL"):
        tl = "ELEVATED"
    try:
        if escalation_score is None:
            esc_str = ""
        else:
            esc_int = int(round(float(escalation_score)))
            esc_str = str(max(0, min(100, esc_int)))
    except (TypeError, ValueError):
        esc_str = ""

    brief = (summary or "").strip() or "No summary available."
    bluf = truncate_resend_string(brief)

    lines = _finding_lines(list(key_findings or []), list(order_indices), key_findings_context)

    bluf_cta = (bd.get("_nl_bluf_cta") or view_link or "").strip()
    view_full = (bd.get("_nl_view_full") or view_link or "").strip()
    public_fb = (bd.get("_nl_public_fallback") or view_link or "").strip()
    finding_urls = bd.get("_nl_finding_urls")
    finding_urls = finding_urls if isinstance(finding_urls, list) else []

    def _fu(idx: int) -> str:
        u = finding_urls[idx] if idx < len(finding_urls) else ""
        return truncate_resend_string(str(u).strip()) if u else ""

    info_html = ""
    if include_infographic_cid:
        info_html = (
            f'<img src="cid:{DAILY_INFOGRAPHIC_CONTENT_ID}" alt="Daily intelligence infographic snapshot" '
            'style="display:block;width:100%;max-width:620px;height:auto;border:1px solid #cbd5e1;" />'
        )

    variables: Dict[str, str] = {
        "CONFLICT": truncate_resend_string(conflict),
        "DATE_STR": truncate_resend_string(date_str),
        "THREAT_LEVEL": truncate_resend_string(tl),
        "ESCALATION_SCORE": truncate_resend_string(esc_str),
        "BLUF_TEXT": bluf,
        "FINDING_1": truncate_resend_string(lines[0]),
        "FINDING_2": truncate_resend_string(lines[1]),
        "FINDING_3": truncate_resend_string(lines[2]),
        "FINDING_4": truncate_resend_string(lines[3]),
        "FINDING_5": truncate_resend_string(lines[4]),
        "LINK_BLUF_CTA": truncate_resend_string(bluf_cta),
        "LINK_VIEW_FULL": truncate_resend_string(view_full),
        "LINK_PUBLIC_FALLBACK": truncate_resend_string(public_fb),
        "NL_UNSUB_LINK": truncate_resend_string(unsubscribe_link),
        "LINK_FINDING_1": _fu(0),
        "LINK_FINDING_2": _fu(1),
        "LINK_FINDING_3": _fu(2),
        "LINK_FINDING_4": _fu(3),
        "LINK_FINDING_5": _fu(4),
        "INFOGRAPHIC_IMG_HTML": info_html,
    }
    for k, v in variables.items():
        if len(v) > RESEND_STRING_VAR_MAX:
            variables[k] = truncate_resend_string(v, max_len=RESEND_STRING_VAR_MAX - 10)
    return variables


def data_uri_to_inline_attachment(data_uri: str, *, content_id: str = DAILY_INFOGRAPHIC_CONTENT_ID) -> Optional[Dict[str, Any]]:
    """
    Convert a data:image/...;base64,... URI into a Resend attachment dict with content_id for CID inline images.
    Returns None if parsing fails.
    """
    raw = (data_uri or "").strip()
    if not raw.startswith("data:") or "," not in raw:
        return None
    try:
        meta, b64 = raw.split(",", 1)
    except ValueError:
        return None
    if ";base64" not in meta and "base64" not in meta:
        return None
    mime_m = re.search(r"data:([^;]+)", meta)
    mime = (mime_m.group(1).strip() if mime_m else "image/png") or "image/png"
    try:
        binary = base64.b64decode(b64.strip(), validate=True)
    except Exception:
        try:
            binary = base64.b64decode(b64.strip())
        except Exception:
            return None
    if not binary:
        return None
    ext = "png"
    if "jpeg" in mime or "jpg" in mime:
        ext = "jpg"
    elif "webp" in mime:
        ext = "webp"
    elif "gif" in mime:
        ext = "gif"
    return {
        "filename": f"infographic.{ext}",
        "content": base64.b64encode(binary).decode("ascii"),
        "content_id": content_id[:127],
        "content_type": mime,
    }
