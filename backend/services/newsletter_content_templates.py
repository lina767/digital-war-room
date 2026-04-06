"""
Content-first newsletter templates fed by live Daily Briefing backend data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Threat accent (left border + score tone) — aligned with Daily Briefing UI bands
THREAT_ACCENT = {
    "CRITICAL": "#b91c1c",
    "HIGH": "#c2410c",
    "ELEVATED": "#ca8a04",
    "LOW": "#15803d",
    "MINIMAL": "#64748b",
}

_PREMIUM_MAX_FINDINGS = 7
_MAX_CTR_FINDINGS = 3


def _escape_html(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _bluf_lead_rest(summary: str) -> Tuple[str, str]:
    """First sentence strong (BLUF), remainder body — matches dashboard BLUF pattern."""
    s = (summary or "").strip()
    if not s:
        return "", ""
    idx = s.find(". ")
    if idx > 0:
        lead, rest = s[: idx + 1].strip(), s[idx + 2 :].strip()
        return lead, rest
    return s, ""


def _confidence_rank(raw: Any) -> int:
    v = (str(raw or "").strip().lower())
    if v == "high":
        return 0
    if v == "medium":
        return 1
    if v == "low":
        return 2
    return 3


def _confidence_label_html(raw: Any) -> str:
    v = (str(raw or "").strip().lower())
    if v == "high":
        color, text = "#0f5132", "HIGH"
    elif v == "medium":
        color, text = "#92400e", "MED"
    elif v == "low":
        color, text = "#475569", "LOW"
    else:
        return ""
    return (
        f'<span style="display:inline-block;margin-right:8px;padding:2px 6px;font-size:10px;'
        f'letter-spacing:0.06em;font-weight:700;color:{color};border:1px solid {color};'
        f'border-radius:2px;">{text}</span>'
    )


def finding_display_order(
    key_findings: List[str],
    confidence: Optional[List[str]],
) -> List[int]:
    """Public alias for newsletter link ordering (same as premium finding order)."""
    return _premium_finding_indices(key_findings, confidence)


def _premium_finding_indices(
    key_findings: List[str],
    confidence: Optional[List[str]],
) -> List[int]:
    """Top N findings; when confidence aligns with findings, rank high→low first (stable)."""
    conf = confidence if isinstance(confidence, list) else []
    indices = [i for i, f in enumerate(key_findings) if (f or "").strip()]
    if not indices:
        return []
    if len(conf) >= len(key_findings):
        indices = sorted(indices, key=lambda i: (_confidence_rank(conf[i] if i < len(conf) else None), i))
    return indices[:_PREMIUM_MAX_FINDINGS]


def _normalize_threat_level(raw: Optional[str]) -> str:
    v = (raw or "").strip().upper()
    if v in ("CRITICAL", "HIGH", "ELEVATED", "LOW", "MINIMAL"):
        return v
    return "ELEVATED"


def _as_int_score(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        v = int(round(float(value)))
        return max(0, min(100, v))
    except (TypeError, ValueError):
        return None


def _derive_topic_tags(briefing_data: Dict[str, Any]) -> str:
    tags: List[str] = []
    candidates = [
        ("sigint", "SIGINT"),
        ("news", "NEWS"),
        ("geoint", "GEOINT"),
        ("protest", "PROTEST"),
        ("diplo", "DIPLO"),
        ("chokepoint", "CHOKEPOINT"),
        ("cyber", "CYBER"),
        ("compliance", "COMPLIANCE"),
    ]
    for key, label in candidates:
        block = briefing_data.get(key)
        if isinstance(block, dict) and block:
            tags.append(label)
    if not tags:
        tags = ["BRIEFING"]
    return ", ".join(tags[:3])


def _scanline(conflict: str, threat_level: str, topic_tags: str, updated_time: str) -> str:
    parts = [p for p in [conflict.upper(), threat_level, topic_tags, updated_time] if p]
    return " | ".join(parts)


def _build_digest_rows(
    key_findings: List[str],
    key_findings_context: Optional[List[str]],
    *,
    max_items: int = 50,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    contexts = key_findings_context if isinstance(key_findings_context, list) else []
    for idx, finding in enumerate((key_findings or [])[:max_items], start=1):
        title = (finding or "").strip()
        if not title:
            continue
        context = contexts[idx - 1] if idx - 1 < len(contexts) and isinstance(contexts[idx - 1], str) else ""
        rows.append(
            {
                "title": title[:180],
                "context": (context or "").strip()[:160],
            }
        )
    return rows


def _newsletter_infographic_enabled(briefing_data: Dict[str, Any]) -> bool:
    return bool(
        briefing_data.get("_newsletter_infographic_enabled")
        or briefing_data.get("_weekly_infographic_enabled")
    )


def _agent_score_rows(briefing_data: Dict[str, Any], *, limit: int = 6) -> List[Tuple[str, int]]:
    rows: List[Tuple[str, int]] = []
    for k, v in (briefing_data or {}).items():
        if not isinstance(k, str) or not k.endswith("_score"):
            continue
        score = _as_int_score(v)
        if score is None:
            continue
        label = k.replace("_score", "").replace("_", " ").upper()
        rows.append((label, score))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows[: max(1, limit)]


def _bluf_short_text(summary: str, *, max_sentences: int = 3) -> str:
    s = (summary or "").strip()
    if not s:
        return ""
    parts = []
    cur = ""
    for ch in s:
        cur += ch
        if ch in ".!?" and len(cur.strip()) > 10:
            parts.append(cur.strip())
            cur = ""
            if len(parts) >= max_sentences:
                break
    if len(parts) < max_sentences and cur.strip():
        parts.append(cur.strip())
    return " ".join(parts[:max_sentences]).strip() or s[:400]


def _ops_preheader(conflict: str, threat_level: str, escalation_score: Optional[int]) -> str:
    esc_txt = f"{escalation_score}/100" if escalation_score is not None else "n/a"
    return f"{conflict}: 3 shifts that changed risk since yesterday. Threat {threat_level}, escalation {esc_txt}."


def _daily_infographic_html(briefing_data: Dict[str, Any], key_findings: List[str], infographic_cta: str) -> str:
    score_rows = _agent_score_rows(briefing_data, limit=6)
    findings = [(f or "").strip() for f in (key_findings or []) if (f or "").strip()][:4]
    image_data_uri = (
        (briefing_data.get("_newsletter_infographic_data_uri") or briefing_data.get("_weekly_infographic_data_uri") or "")
        .strip()
    )
    oversize_note = ""
    if briefing_data.get("_newsletter_infographic_oversize"):
        oversize_note = (
            '<p style="margin:0 0 8px 0;font-size:12px;color:#64748b;">'
            "Infographic omitted in this email for size limits — open the briefing or dashboard for the full picture."
            "</p>"
        )
    image_html = (
        f'<p style="margin:0 0 10px 0;"><img src="{image_data_uri}" alt="Daily intelligence infographic snapshot" '
        'style="display:block;width:100%;max-width:620px;height:auto;border:1px solid #cbd5e1;" /></p>'
        if image_data_uri.startswith("data:image/")
        else ""
    )
    score_html = ""
    for label, score in score_rows:
        score_html += f"""
            <tr>
              <td style="padding:6px 0;font-size:12px;color:#334155;letter-spacing:0.03em;">{_escape_html(label)}</td>
              <td align="right" style="padding:6px 0;font-size:12px;color:#0f172a;font-weight:700;">{score}/100</td>
            </tr>
        """
    finding_html = ""
    for i, item in enumerate(findings, start=1):
        finding_html += (
            f'<p style="margin:0 0 6px 0;font-size:13px;line-height:1.45;color:#0f172a;">{i}. {_escape_html(item[:150])}</p>'
        )
    cta_html = (
        f'<p style="margin:10px 0 0 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;">'
        f'<a href="{infographic_cta}" style="color:#1e3a5f;text-decoration:underline;font-weight:600;">'
        "Explore live context in dashboard</a></p>"
    )
    return f"""
                <table role="presentation" width="100%" style="border-collapse:collapse;margin:0 0 18px 0;">
                  <tr>
                    <td style="padding:12px 14px;background:#f8fafc;border:1px solid #cbd5e1;">
                      <p style="margin:0 0 8px 0;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:#475569;">Daily infographic snapshot</p>
                      {oversize_note}
                      {image_html}
                      <table role="presentation" width="100%" style="border-collapse:collapse;">
                        {score_html}
                      </table>
                      <div style="margin-top:10px;padding-top:10px;border-top:1px solid #e2e8f0;">
                        {finding_html}
                      </div>
                      {cta_html}
                    </td>
                  </tr>
                </table>
    """


def _daily_infographic_text(briefing_data: Dict[str, Any], key_findings: List[str]) -> str:
    score_rows = _agent_score_rows(briefing_data, limit=6)
    findings = [(f or "").strip() for f in (key_findings or []) if (f or "").strip()][:4]
    if not score_rows and not findings:
        return ""
    lines: List[str] = []
    lines.append("Daily infographic snapshot")
    for label, score in score_rows:
        lines.append(f"- {label}: {score}/100")
    if findings:
        lines.append("- Top findings:")
        for idx, item in enumerate(findings, start=1):
            lines.append(f"  {idx}. {item[:150]}")
    return "\n".join(lines)


def daily_briefing_email_html(
    conflict: str,
    date_str: str,
    summary: str,
    key_findings: list[str],
    escalation_score: int | None,
    view_link: str,
    unsubscribe_link: str,
    *,
    briefing_data: Optional[Dict[str, Any]] = None,
    threat_level: Optional[str] = None,
    key_findings_context: Optional[List[str]] = None,
) -> str:
    bd = briefing_data if isinstance(briefing_data, dict) else {}
    tl = _normalize_threat_level(threat_level or bd.get("threat_level"))
    esc = _as_int_score(escalation_score)
    updated = datetime.now(timezone.utc).strftime("%H:%M UTC")
    tags = _derive_topic_tags(bd)
    scanline = _scanline(conflict, tl, tags, updated)
    brief = (summary or "").strip() or "No summary available."
    bluf_short = _bluf_short_text(brief, max_sentences=3)
    bluf_display = bluf_short or brief
    lead, rest = _bluf_lead_rest(bluf_display)
    if rest:
        bluf_html = f'<strong style="color:#0f1720;">{_escape_html(lead)}</strong> {_escape_html(rest)}'
    else:
        bluf_html = f'<strong style="color:#0f1720;">{_escape_html(lead)}</strong>' if lead else _escape_html(bluf_display)

    bluf_cta = (bd.get("_nl_bluf_cta") or view_link or "").strip()
    infographic_cta = (bd.get("_nl_infographic_cta") or bluf_cta).strip()
    public_fb = (bd.get("_nl_public_fallback") or view_link).strip()
    feedback_useful = (bd.get("_nl_feedback_useful") or "").strip()
    feedback_not_useful = (bd.get("_nl_feedback_not_useful") or "").strip()
    finding_urls = bd.get("_nl_finding_urls")
    finding_urls = finding_urls if isinstance(finding_urls, list) else []

    accent = THREAT_ACCENT.get(tl, "#ca8a04")
    esc_pct = esc if esc is not None else 0
    esc_bar = ""
    if esc is not None:
        esc_bar = f"""
                <table role="presentation" width="100%" style="border-collapse:collapse;margin-top:8px;">
                  <tr>
                    <td style="padding:0;height:4px;background:#e2e8f0;font-size:0;line-height:0;">
                      <table role="presentation" width="100%" style="border-collapse:collapse;">
                        <tr>
                          <td width="{esc_pct}%" style="background:{accent};height:4px;font-size:0;line-height:0;">&nbsp;</td>
                          <td style="background:#e2e8f0;height:4px;font-size:0;line-height:0;">&nbsp;</td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>

        """

    threat_panel = f"""
                <table role="presentation" width="100%" style="border-collapse:collapse;margin:0 0 18px 0;">
                  <tr>
                    <td style="padding:11px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-left:4px solid {accent};">
                      <table role="presentation" width="100%" style="border-collapse:collapse;">
                        <tr>
                          <td style="vertical-align:top;">
                            <p style="margin:0 0 2px 0;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#64748b;">Threat level</p>
                            <p style="margin:0;font-size:12px;font-weight:700;color:#0f1720;">{_escape_html(tl)}</p>
                          </td>
                          <td align="right" style="vertical-align:top;">
                            <p style="margin:0 0 2px 0;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#64748b;">Escalation</p>
                            <p style="margin:0;font-size:12px;font-weight:700;color:#0f1720;">{esc}/100</p>
                          </td>
                        </tr>
                      </table>
                      {esc_bar}
                    </td>
                  </tr>
                </table>
    """ if esc is not None else f"""
                <table role="presentation" width="100%" style="border-collapse:collapse;margin:0 0 18px 0;">
                  <tr>
                    <td style="padding:11px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-left:4px solid {accent};">
                      <p style="margin:0 0 2px 0;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#64748b;">Threat level</p>
                      <p style="margin:0;font-size:12px;font-weight:700;color:#0f1720;">{_escape_html(tl)}</p>
                    </td>
                  </tr>
                </table>
    """

    kf = list(key_findings or [])
    conf_list = bd.get("key_findings_confidence")
    conf_list = conf_list if isinstance(conf_list, list) else []
    order = _premium_finding_indices(kf, conf_list if len(conf_list) >= len(kf) else None)
    contexts = key_findings_context if isinstance(key_findings_context, list) else []

    def _one_row_html(disp_i: int, src_i: int, *, deep_url: Optional[str] = None) -> str:
        f = (kf[src_i] or "").strip()
        if not f:
            return ""
        ctx = contexts[src_i] if src_i < len(contexts) and isinstance(contexts[src_i], str) else ""
        badge = ""
        if src_i < len(conf_list):
            badge = _confidence_label_html(conf_list[src_i])
        ctx_html = (
            f'<p style="margin:6px 0 0 0;font-size:12px;line-height:1.45;color:#64748b;letter-spacing:0.02em;text-transform:uppercase;">Why this matters now</p>'
            f'<p style="margin:2px 0 0 0;font-size:13px;line-height:1.45;color:#475569;">{_escape_html(ctx.strip()[:220])}</p>'
            if ctx and ctx.strip()
            else ""
        )
        link_html = ""
        if deep_url:
            link_html = f"""
              <p style="margin:8px 0 0 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;">
                <a href="{deep_url}" style="color:#1e3a5f;text-decoration:underline;font-weight:600;">Explore in dashboard</a>
                <span style="color:#94a3b8;"> · </span>
                <a href="{public_fb}" style="color:#64748b;text-decoration:underline;">Public briefing</a>
              </p>"""
        return f"""
          <tr>
            <td style="padding:12px 0;border-top:1px solid #e2e8f0;">
              <p style="margin:0;font-size:12px;color:#94a3b8;font-family:Georgia,'Times New Roman',serif;">{disp_i}</p>
              <p style="margin:4px 0 0 0;font-size:15px;line-height:1.45;color:#0f1720;">
                {badge}{_escape_html(f)}
              </p>
              {ctx_html}
              {link_html}
            </td>
          </tr>
        """

    rows_html_ctr = ""
    ctr_order = order[:_MAX_CTR_FINDINGS]
    for idx, src_i in enumerate(ctr_order):
        u = finding_urls[idx] if idx < len(finding_urls) else ""
        rows_html_ctr += _one_row_html(idx + 1, src_i, deep_url=u or None)

    rows_html_rest = ""
    for j, src_i in enumerate(order[_MAX_CTR_FINDINGS:], start=len(ctr_order) + 1):
        rows_html_rest += _one_row_html(j, src_i, deep_url=None)

    rows_html = rows_html_ctr + rows_html_rest
    if not rows_html.strip():
        rows_html = """
          <tr>
            <td style="padding:12px 0;border-top:1px solid #e2e8f0;">
              <p style="margin:0;font-size:14px;color:#64748b;">No key developments available for this run.</p>
            </td>
          </tr>
        """

    daily_infographic_html = (
        _daily_infographic_html(bd, kf, infographic_cta)
        if _newsletter_infographic_enabled(bd)
        else ""
    )
    preheader = _ops_preheader(conflict, tl, esc)
    feedback_html = ""
    if feedback_useful or feedback_not_useful:
        useful_link = feedback_useful or view_link
        not_useful_link = feedback_not_useful or view_link
        feedback_html = (
            '<p style="margin:16px 0 0 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.45;color:#64748b;">'
            "Was this useful for today's ops cycle? "
            f'<a href="{useful_link}" style="color:#1e3a5f;text-decoration:underline;font-weight:600;">Useful</a>'
            ' · '
            f'<a href="{not_useful_link}" style="color:#1e3a5f;text-decoration:underline;">Not useful</a>'
            "</p>"
        )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <title>Daily Briefing — {_escape_html(conflict)}</title>
  </head>
  <body style="margin:0;padding:0;background:#eef2f6;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
      {_escape_html(preheader)}
    </div>
    <table role="presentation" width="100%" style="border-collapse:collapse;background:#eef2f6;padding:28px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" style="max-width:680px;border-collapse:collapse;background:#ffffff;border:1px solid #cbd5e1;box-shadow:0 1px 3px rgba(15,23,42,0.06);">
            <tr>
              <td style="padding:22px 24px;font-family:Georgia,'Times New Roman',serif;color:#0f172a;">
                <table role="presentation" width="100%" style="border-collapse:collapse;">
                  <tr>
                    <td style="font-family:Arial,Helvetica,sans-serif;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#64748b;">Digital War Room</td>
                    <td align="right" style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#64748b;">{_escape_html(date_str)} · {_escape_html(updated)}</td>
                  </tr>
                </table>

                <p style="margin:16px 0 4px 0;font-family:Arial,Helvetica,sans-serif;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#64748b;">Daily intelligence briefing</p>
                <h1 style="margin:0 0 10px 0;font-size:26px;line-height:1.2;font-weight:600;letter-spacing:-0.02em;color:#0f172a;">{_escape_html(conflict)}</h1>
                <p style="margin:0 0 16px 0;font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:1.4;letter-spacing:0.06em;text-transform:uppercase;color:#64748b;">{_escape_html(scanline)}</p>

                {threat_panel}

                <p style="margin:0 0 6px 0;font-family:Arial,Helvetica,sans-serif;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:#64748b;">Executive summary (BLUF)</p>
                <p style="margin:0 0 14px 0;font-size:16px;line-height:1.55;color:#1e293b;">{bluf_html}</p>
                <table role="presentation" width="100%" style="margin:0 0 22px 0;border-collapse:collapse;">
                  <tr>
                    <td>
                      <a href="{bluf_cta}" style="display:inline-block;background:#0f172a;color:#ffffff;text-decoration:none;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:600;line-height:13px;padding:14px 20px;border:1px solid #0f172a;">Open live dashboard</a>
                    </td>
                  </tr>
                </table>
                {feedback_html}

                {daily_infographic_html}

                <p style="margin:0 0 10px 0;font-family:Arial,Helvetica,sans-serif;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:#64748b;">Key developments</p>
                <p style="margin:0 0 8px 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.4;color:#94a3b8;">Top {_MAX_CTR_FINDINGS} include direct dashboard links; full list in the briefing.</p>

                <table role="presentation" width="100%" style="border-collapse:collapse;">
                  {rows_html}
                </table>

                <table role="presentation" width="100%" style="margin:20px 0 6px 0;border-collapse:collapse;">
                  <tr>
                    <td>
                      <a href="{view_link}" style="display:inline-block;background:#0f172a;color:#ffffff;text-decoration:none;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:600;line-height:13px;padding:14px 20px;border:1px solid #0f172a;">View full briefing</a>
                    </td>
                  </tr>
                </table>
                <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.5;">
                  <a href="{view_link}" style="color:#1e3a5f;text-decoration:underline;">Open daily briefing in browser</a>
                </p>

                <p style="margin:18px 0 0 0;font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:1.55;color:#94a3b8;border-top:1px solid #e2e8f0;padding-top:14px;">
                  You are receiving this email because you subscribed to Daily Briefing updates.
                  <a href="{unsubscribe_link}" style="color:#1e3a5f;text-decoration:underline;">Unsubscribe</a>
                  <br />
                  <a href="https://github.com/lina767/digital-war-room" style="color:#1e3a5f;text-decoration:underline;">GitHub</a>
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def daily_briefing_email_text(
    conflict: str,
    date_str: str,
    summary: str,
    key_findings: list[str],
    escalation_score: int | None,
    view_link: str,
    unsubscribe_link: str,
    *,
    briefing_data: Optional[Dict[str, Any]] = None,
    threat_level: Optional[str] = None,
    key_findings_context: Optional[List[str]] = None,
) -> str:
    bd = briefing_data if isinstance(briefing_data, dict) else {}
    tl = _normalize_threat_level(threat_level or bd.get("threat_level"))
    esc = _as_int_score(escalation_score)
    updated = datetime.now(timezone.utc).strftime("%H:%M UTC")
    tags = _derive_topic_tags(bd)
    scanline = _scanline(conflict, tl, tags, updated)
    brief = (summary or "").strip() or "No summary available."
    lead, rest = _bluf_lead_rest(brief)
    bluf_txt = f"{lead} {rest}".strip() if rest else lead or brief

    kf = list(key_findings or [])
    conf_list = bd.get("key_findings_confidence")
    conf_list = conf_list if isinstance(conf_list, list) else []
    order = _premium_finding_indices(kf, conf_list if len(conf_list) >= len(kf) else None)
    contexts = key_findings_context if isinstance(key_findings_context, list) else []

    lines: List[str] = []
    for disp_i, src_i in enumerate(order, start=1):
        f = (kf[src_i] or "").strip()
        if not f:
            continue
        ctx = contexts[src_i] if src_i < len(contexts) and isinstance(contexts[src_i], str) else ""
        conf_tag = ""
        if src_i < len(conf_list) and (conf_list[src_i] or "").strip():
            conf_tag = f"[{str(conf_list[src_i]).strip().upper()}] "
        lines.append(f"{disp_i}. {conf_tag}{f}")
        if ctx and ctx.strip():
            lines.append(f"   Why this matters now: {ctx.strip()[:220]}")
    findings_block = "\n".join(lines) if lines else "No key developments available for this run."
    score_line = f"{tl} | Escalation {esc}/100" if esc is not None else tl
    daily_txt = _daily_infographic_text(bd, kf) if _newsletter_infographic_enabled(bd) else ""
    daily_block = f"\n{daily_txt}\n" if daily_txt else ""
    bluf_cta = (bd.get("_nl_bluf_cta") or view_link or "").strip()
    finding_urls = bd.get("_nl_finding_urls")
    finding_urls = finding_urls if isinstance(finding_urls, list) else []
    feedback_useful = (bd.get("_nl_feedback_useful") or "").strip()
    feedback_not_useful = (bd.get("_nl_feedback_not_useful") or "").strip()
    url_lines = ""
    for i, u in enumerate(finding_urls[:_MAX_CTR_FINDINGS], start=1):
        if u:
            url_lines += f"\nFinding {i} (dashboard): {u}"

    return f"""DIGITAL WAR ROOM
Daily Intelligence Briefing — {conflict} — {date_str}
{scanline}
Threat: {score_line}

Executive summary (BLUF)
{bluf_txt}

Open live dashboard: {bluf_cta}
{daily_block}

Key developments (top rows include dashboard deep links)
{findings_block}
{url_lines}

View full briefing: {view_link}
Feedback (useful): {feedback_useful or view_link}
Feedback (not useful): {feedback_not_useful or view_link}
Unsubscribe: {unsubscribe_link}
GitHub: https://github.com/lina767/digital-war-room
"""


def daily_briefing_digest_html(
    conflict: str,
    date_str: str,
    summary: str,
    key_findings: list[str],
    view_link: str,
    unsubscribe_link: str,
    *,
    briefing_data: Optional[Dict[str, Any]] = None,
    threat_level: Optional[str] = None,
    key_findings_context: Optional[List[str]] = None,
    row_links: Optional[List[str]] = None,
) -> str:
    bd = briefing_data if isinstance(briefing_data, dict) else {}
    tl = _normalize_threat_level(threat_level or bd.get("threat_level"))
    updated = datetime.now(timezone.utc).strftime("%H:%M UTC")
    tags = _derive_topic_tags(bd)
    rows = _build_digest_rows(key_findings, key_findings_context, max_items=50)
    digest_intro = (summary or "").strip() or "Daily list of key report developments."
    feedback_useful = (bd.get("_nl_feedback_useful") or "").strip()
    feedback_not_useful = (bd.get("_nl_feedback_not_useful") or "").strip()
    infographic_cta = (bd.get("_nl_infographic_cta") or view_link).strip()
    daily_infographic_html = (
        _daily_infographic_html(bd, key_findings, infographic_cta)
        if _newsletter_infographic_enabled(bd)
        else ""
    )

    links = row_links if isinstance(row_links, list) and row_links else []
    row_html = ""
    for idx, item in enumerate(rows):
        row_scanline = _scanline(conflict, tl, tags, updated)
        context_html = (
            f'<p style="margin:5px 0 0 0;color:#2f3e4d;font-size:13px;line-height:1.35;">{_escape_html(item["context"])}</p>'
            if item["context"]
            else ""
        )
        row_href = links[idx] if idx < len(links) else view_link
        row_html += f"""
                <table role="presentation" width="100%" style="border-collapse:collapse;border-top:1px solid #e2e8f0;">
                  <tr>
                    <td style="padding:11px 0 10px 0;">
                      <p style="margin:0;">
                        <a href="{row_href}" style="color:#0f3f73;text-decoration:none;font-size:16px;line-height:1.35;font-weight:bold;">{_escape_html(item["title"])}</a>
                      </p>
                      <p style="margin:5px 0 0 0;color:#4a5562;font-size:11px;line-height:1.35;text-transform:uppercase;letter-spacing:0.03em;">{_escape_html(row_scanline)}</p>
                      {context_html}
                      <p style="margin:6px 0 0 0;font-size:13px;line-height:1.35;"><a href="{row_href}" style="color:#0f3f73;text-decoration:underline;">Read report</a></p>
                    </td>
                  </tr>
                </table>
        """

    if not row_html:
        row_html = """
                <table role="presentation" width="100%" style="border-collapse:collapse;border-top:1px solid #e2e8f0;">
                  <tr>
                    <td style="padding:11px 0 10px 0;">
                      <p style="margin:0;color:#4a5562;font-size:14px;">No digest items available for this run.</p>
                    </td>
                  </tr>
                </table>
        """
    feedback_html = ""
    if feedback_useful or feedback_not_useful:
        feedback_html = (
            '<p style="margin-top:10px;font-size:12px;line-height:1.45;color:#596677;">'
            'Was this digest useful? '
            f'<a href="{feedback_useful or view_link}" style="color:#0f3f73;text-decoration:underline;font-weight:600;">Useful</a>'
            ' · '
            f'<a href="{feedback_not_useful or view_link}" style="color:#0f3f73;text-decoration:underline;">Not useful</a>'
            "</p>"
        )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <title>Daily Briefing Digest - {_escape_html(conflict)}</title>
  </head>
  <body style="margin:0;padding:0;background:#f5f7fa;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
      {_escape_html(conflict)} digest - {_escape_html(digest_intro[:120])}
    </div>
    <table role="presentation" width="100%" style="border-collapse:collapse;background:#f5f7fa;padding:24px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" style="max-width:680px;border-collapse:collapse;background:#ffffff;border:1px solid #dde3ea;">
            <tr>
              <td style="padding:20px;font-family:Arial,Helvetica,sans-serif;color:#17212b;">
                <table role="presentation" width="100%" style="border-collapse:collapse;">
                  <tr>
                    <td style="font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:#5b6774;">DIGITAL WAR ROOM</td>
                    <td align="right" style="font-size:12px;color:#5b6774;">{_escape_html(date_str)}</td>
                  </tr>
                </table>
                <h1 style="margin:14px 0 8px 0;font-size:23px;line-height:1.25;color:#0f1720;">Daily Intelligence Digest</h1>
                <p style="margin:0 0 14px 0;font-size:14px;line-height:1.45;color:#22303e;">{_escape_html(digest_intro)}</p>
                {daily_infographic_html}
                {feedback_html}
                {row_html}
                <p style="margin-top:14px;border-top:1px solid #e2e8f0;padding-top:12px;font-size:12px;line-height:1.5;color:#596677;">
                  You are receiving this email because you subscribed to Daily Briefing updates.
                  <a href="{unsubscribe_link}" style="color:#0f3f73;text-decoration:underline;">Unsubscribe</a>
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def daily_briefing_digest_text(
    conflict: str,
    date_str: str,
    summary: str,
    key_findings: list[str],
    view_link: str,
    unsubscribe_link: str,
    *,
    briefing_data: Optional[Dict[str, Any]] = None,
    threat_level: Optional[str] = None,
    key_findings_context: Optional[List[str]] = None,
    row_links: Optional[List[str]] = None,
) -> str:
    bd = briefing_data if isinstance(briefing_data, dict) else {}
    tl = _normalize_threat_level(threat_level or bd.get("threat_level"))
    updated = datetime.now(timezone.utc).strftime("%H:%M UTC")
    tags = _derive_topic_tags(bd)
    rows = _build_digest_rows(key_findings, key_findings_context, max_items=50)
    header_scanline = _scanline(conflict, tl, tags, updated)
    digest_intro = (summary or "").strip() or "Daily list of key report developments."
    feedback_useful = (bd.get("_nl_feedback_useful") or "").strip()
    feedback_not_useful = (bd.get("_nl_feedback_not_useful") or "").strip()
    daily_txt = _daily_infographic_text(bd, key_findings) if _newsletter_infographic_enabled(bd) else ""
    daily_block = f"\n{daily_txt}\n" if daily_txt else ""
    links = row_links if isinstance(row_links, list) and row_links else []
    lines: List[str] = []
    for idx, item in enumerate(rows, start=1):
        href = links[idx - 1] if idx - 1 < len(links) else view_link
        lines.append(f"{idx}. {item['title']}")
        lines.append(f"   {header_scanline}")
        if item["context"]:
            lines.append(f"   {item['context']}")
        lines.append(f"   Read report: {href}")
    body = "\n".join(lines) if lines else "No digest items available for this run."
    return f"""DIGITAL WAR ROOM
Daily Intelligence Digest - {conflict} - {date_str}
{header_scanline}

{digest_intro}
{daily_block}

{body}

Feedback (useful): {feedback_useful or view_link}
Feedback (not useful): {feedback_not_useful or view_link}
Unsubscribe: {unsubscribe_link}
"""
