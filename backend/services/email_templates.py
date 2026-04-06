"""
Digital War Room - Branded Email Templates
Dark military-tech design matching the website and Daily Briefing page layout (BLUF, Key Findings, etc.).

Usage: Replace the html strings in newsletter_sender.py with these function calls.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Brand colors (extracted from screenshot)
COLORS = {
    "bg_dark": "#0d1117",  # Main background
    "bg_card": "#161b22",  # Card/panel background
    "bg_header": "#0d1117",  # Header area
    "text_primary": "#e6edf3",  # Main text
    "text_secondary": "#7d8590",  # Muted text
    "accent_green": "#22c55e",  # Primary green (buttons, highlights)
    "accent_red": "#f85149",  # Alert red (for HIGH status)
    "border": "#30363d",  # Borders
    "link": "#22c55e",  # Links
}

# Aligned with Daily Briefing `--threat-*` (approximate hex for email clients)
THREAT_LEVEL_HEX = {
    "CRITICAL": "#f87171",
    "HIGH": "#fb923c",
    "ELEVATED": "#facc15",
    "LOW": "#22c55e",
    "MINIMAL": "#9ca3af",
}


def _normalize_threat_level(raw: Optional[str]) -> str:
    v = (raw or "").strip().upper()
    if v in ("CRITICAL", "HIGH", "ELEVATED", "LOW", "MINIMAL"):
        return v
    return "ELEVATED"


def _bluf_html(summary: str) -> str:
    """BLUF block: lead sentence strong (matches BLUFSection)."""
    s = (summary or "").strip()
    if not s:
        return ""
    idx = s.find(". ")
    if idx > 0:
        lead, rest = s[: idx + 1], s[idx + 2 :].strip()
        return f'<strong style="color: {COLORS["text_primary"]};">{_escape_html(lead)}</strong> {_escape_html(rest)}'
    return _escape_html(s)


def _finding_title_body(text: str, context: Optional[str]) -> tuple[str, str]:
    t = (text or "").strip()
    title = t.split(".", 1)[0].strip() if t else ""
    body = (context or "").strip() or t
    return title, body


def _trajectory_from_predictive(predictive: Optional[Dict[str, Any]], escalation_score: int) -> str:
    """Match useBriefingData.buildPredictiveOutlook trajectory logic."""
    if not predictive:
        if escalation_score >= 65:
            return "ESCALATING"
        if escalation_score <= 35:
            return "DE_ESCALATING"
        return "STABLE"
    baseline = predictive.get("baseline_escalation") or {}
    vs_b = baseline.get("vs_baseline")
    if vs_b == "higher":
        return "ESCALATING"
    if vs_b == "lower":
        return "DE_ESCALATING"
    if vs_b == "similar":
        if escalation_score >= 65:
            return "ESCALATING"
        if escalation_score <= 35:
            return "DE_ESCALATING"
        return "STABLE"
    if escalation_score >= 65:
        return "ESCALATING"
    if escalation_score <= 35:
        return "DE_ESCALATING"
    return "STABLE"


def _predictive_signals(
    briefing_data: Dict[str, Any], predictive: Optional[Dict[str, Any]], escalation_score: int
) -> List[tuple[str, int]]:
    """Top signals aligned with useBriefingData.buildPredictiveOutlook (subset)."""
    esc = max(0, min(100, int(round(float(escalation_score)))))
    signals: List[tuple[str, int]] = [("Composite escalation score", esc)]

    pred = predictive or {}
    baseline = pred.get("baseline_escalation") or {}
    for i, d in enumerate((baseline.get("drivers") or [])[:2]):
        if isinstance(d, str) and d.strip():
            w = int(esc * (0.88 - i * 0.08))
            signals.append((d.strip()[:120], max(0, min(100, w))))

    esc_list = pred.get("escalation") or []
    if esc_list and isinstance(esc_list[0], dict):
        e0 = esc_list[0]
        h, lev = e0.get("horizon"), e0.get("level")
        if h and lev:
            weight = {"CRITICAL": 92, "HIGH": 78, "MEDIUM": 55, "LOW": 38}.get(str(lev), 50)
            signals.append((f"Predicted stress ({h})", weight))

    choke = briefing_data.get("chokepoint") or {}
    cps = choke.get("chokepoints") if isinstance(choke, dict) else None
    if isinstance(cps, list) and cps:
        risks = [float(c.get("disruption_risk") or 0) for c in cps if isinstance(c, dict)]
        max_risk = max(risks) if risks else 0
        if max_risk > 35:
            signals.append(("Chokepoint disruption risk", int(round(max(0, min(100, max_risk))))))

    news = briefing_data.get("news")
    if isinstance(news, dict):
        ns = news.get("news_score")
        if isinstance(ns, (int, float)) and not isinstance(ns, bool):
            try:
                f = float(ns)
                if f == f:  # not NaN
                    signals.append(("News stream intensity", min(100, int(round(f)))))
            except (TypeError, ValueError):
                pass

    return signals[:5]


def _default_things_to_watch_scenarios(conflict: str, escalation_score: int) -> List[Dict[str, Any]]:
    """When API sends no scenarios, mirror frontend effectiveWatchScenarios."""
    label = (conflict or "this theater").strip() or "this theater"
    esc = max(0, min(100, int(round(float(escalation_score)))))
    bias = (esc - 50) / 100.0
    p_esc = min(0.42, max(0.18, 0.28 + bias * 0.2))
    p_stable = min(0.4, max(0.2, 0.32 - bias * 0.12))
    return [
        {
            "description": (
                f"Pattern hold for {label}: treat material change when SIGINT posture, "
                "NEWS throughput, and FININT (e.g. Brent) move together rather than in isolation."
            ),
            "probability": p_stable,
        },
        {
            "description": (
                f"Escalation corridor: watch for correlated spikes in military/transport indicators, "
                f"headline density, and commodity stress before updating your prior on {label}."
            ),
            "probability": p_esc,
        },
        {
            "description": (
                "Maritime and chokepoints: cross-check tanker/AIS context, disruption language in coverage, "
                "and ENERGY readings when reassessing spillover risk."
            ),
            "probability": 0.22,
        },
        {
            "description": (
                "Tail risks: diplomatic shocks or single-point failures may lag in OSINT; "
                "keep a slot for late-breaking sources and primary corroboration."
            ),
            "probability": 0.14,
        },
    ]


def _things_to_watch_scenario_dicts(bd: Dict[str, Any], conflict: str, esc_for_pred: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    scenarios = bd.get("scenarios") or []
    if isinstance(scenarios, list):
        for s in scenarios[:4]:
            if not isinstance(s, dict):
                continue
            desc = (s.get("description") or "").strip()
            if not desc:
                continue
            out.append({"description": desc, "probability": s.get("probability")})
    if not out:
        out = _default_things_to_watch_scenarios(conflict, esc_for_pred)
    return out


def confirmation_email_html(conflict: str, confirm_link: str) -> str:
    """
    Double opt-in confirmation email - matches DWR dark theme.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: {COLORS['bg_dark']}; font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: {COLORS['bg_dark']};">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 520px;">

                    <!-- Header -->
                    <tr>
                        <td style="padding-bottom: 24px; border-bottom: 1px solid {COLORS['border']};">
                            <span style="color: {COLORS['accent_green']}; font-size: 14px; font-weight: 600; letter-spacing: 2px; text-transform: uppercase;">DIGITAL WAR ROOM</span>
                        </td>
                    </tr>

                    <!-- Content -->
                    <tr>
                        <td style="padding: 32px 0;">
                            <p style="color: {COLORS['text_secondary']}; font-size: 12px; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 1px;">Subscription Request</p>
                            <h1 style="color: {COLORS['text_primary']}; font-size: 20px; font-weight: 600; margin: 0 0 24px 0;">Daily Briefing: {conflict}</h1>

                            <p style="color: {COLORS['text_secondary']}; font-size: 14px; line-height: 1.6; margin: 0 0 24px 0;">
                                You requested the Daily Briefing for <span style="color: {COLORS['text_primary']}; font-weight: 500;">{conflict}</span>.
                                Confirm your subscription to receive daily intelligence updates.
                            </p>

                            <!-- CTA Button -->
                            <table role="presentation" cellspacing="0" cellpadding="0" style="margin: 32px 0;">
                                <tr>
                                    <td style="background-color: {COLORS['accent_green']}; border-radius: 6px;">
                                        <a href="{confirm_link}" style="display: inline-block; padding: 14px 28px; color: #000000; font-size: 14px; font-weight: 600; text-decoration: none; letter-spacing: 0.5px;">
                                            CONFIRM SUBSCRIPTION
                                        </a>
                                    </td>
                                </tr>
                            </table>

                            <p style="color: {COLORS['text_secondary']}; font-size: 12px; line-height: 1.5; margin: 0;">
                                If you did not request this, ignore this email.
                            </p>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding-top: 24px; border-top: 1px solid {COLORS['border']};">
                            <p style="color: {COLORS['text_secondary']}; font-size: 11px; margin: 0; letter-spacing: 0.5px;">
                                Digital War Room - AI-Powered OSINT Intelligence
                            </p>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


def confirmation_email_text(conflict: str, confirm_link: str) -> str:
    """Plain text version of confirmation email."""
    return f"""DIGITAL WAR ROOM
================

Subscription Request: Daily Briefing - {conflict}

You requested the Daily Briefing for {conflict}.
Confirm your subscription to receive daily intelligence updates.

Confirm subscription: {confirm_link}

If you did not request this, ignore this email.

-
Digital War Room - AI-Powered OSINT Intelligence
"""


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
    """
    Daily briefing email — section labels and structure aligned with the Daily Briefing page.
    """
    bd: Dict[str, Any] = briefing_data if isinstance(briefing_data, dict) else {}
    esc_raw = escalation_score
    try:
        esc_int = int(round(float(esc_raw))) if esc_raw is not None else None
    except (TypeError, ValueError):
        esc_int = None
    if esc_int is not None:
        esc_int = max(0, min(100, esc_int))
    esc_for_pred = esc_int if esc_int is not None else 50

    tl = _normalize_threat_level(threat_level or bd.get("threat_level"))
    threat_color = THREAT_LEVEL_HEX.get(tl, COLORS["accent_green"])
    if esc_int is not None:
        escalation_html = f"""
            <p style="margin: 0 0 4px 0;">
                <span style="color: {threat_color}; font-size: 14px; font-weight: 600; letter-spacing: 0.06em; font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;">
                    {tl}
                </span>
            </p>
            <p style="margin: 0; color: {COLORS['text_secondary']}; font-size: 12px; font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;">
                {esc_int}/100
            </p>
        """
    else:
        escalation_html = f"""
            <p style="margin: 0; color: {threat_color}; font-size: 14px; font-weight: 600; letter-spacing: 0.06em; font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;">{tl}</p>
        """

    # Inbox preheader (hidden snippet line; many clients show this next to subject)
    snippet = (summary or "").strip().replace("\n", " ")
    if len(snippet) > 130:
        snippet = snippet[:127] + "..."
    preheader = f"{conflict} — {snippet}" if snippet else f"Daily intelligence briefing for {conflict}"

    ctx_list = key_findings_context if key_findings_context is not None else bd.get("key_findings_context") or []
    if not isinstance(ctx_list, list):
        ctx_list = []

    findings_html = ""
    for i, finding in enumerate(key_findings[:8], 1):
        text = (finding or "").strip()
        if not text:
            continue
        ctx = ctx_list[i - 1] if i - 1 < len(ctx_list) else None
        ctx_s = ctx if isinstance(ctx, str) else None
        _, body = _finding_title_body(text, ctx_s)
        extra = ""
        if ctx_s and ctx_s.strip() and ctx_s.strip() != text.strip():
            extra = f"""
                <p style="color: {COLORS['text_secondary']}; font-size: 12px; line-height: 1.5; margin: 8px 0 0 0;">
                    {_escape_html(ctx_s.strip())}
                </p>
            """
        findings_html += f"""
            <tr>
                <td style="padding: 10px 0; border-bottom: 1px solid {COLORS['border']};">
                    <p style="color: {COLORS['text_primary']}; font-size: 13px; line-height: 1.5; margin: 0;">
                        <span style="color: {COLORS['accent_green']}; font-size: 12px; margin-right: 8px;">{i}.</span>
                        {_escape_html(body)}
                    </p>
                    {extra}
                </td>
            </tr>
        """

    watch_items = _things_to_watch_scenario_dicts(bd, conflict, esc_for_pred)
    sc_rows = ""
    for s in watch_items:
        desc = (s.get("description") or "").strip()
        if not desc:
            continue
        prob = s.get("probability")
        prob_line = ""
        if isinstance(prob, (int, float)) and not isinstance(prob, bool):
            pf = float(prob)
            if 0 <= pf <= 1:
                prob_line = f'<p style="margin: 4px 0 0 0; font-size: 11px; color: {COLORS["text_secondary"]}; font-family: \'SF Mono\', monospace;">~{int(round(pf * 100))}%</p>'
        sc_rows += f"""
                <tr>
                    <td style="padding: 8px 0; border-bottom: 1px solid {COLORS['border']};">
                        <p style="margin: 0; font-size: 13px; line-height: 1.5; color: {COLORS['text_primary']};">{_escape_html(desc)}</p>
                        {prob_line}
                    </td>
                </tr>
            """
    scenarios_html = ""
    if sc_rows:
        scenarios_html = f"""
                    <tr>
                        <td style="padding: 24px 0; border-top: 1px solid {COLORS['border']};">
                            <p style="color: {COLORS['accent_green']}; font-size: 11px; margin: 0 0 6px 0; text-transform: uppercase; letter-spacing: 1.5px;">Things to Watch</p>
                            <p style="color: {COLORS['text_secondary']}; font-size: 12px; line-height: 1.5; margin: 0 0 14px 0;">
                                Supervisor scenarios when present; otherwise default cross-stream watch items. Probabilities are rough emphasis only.
                            </p>
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                {sc_rows}
                            </table>
                        </td>
                    </tr>
            """

    predictive = bd.get("predictive") if isinstance(bd.get("predictive"), dict) else {}
    pred_block = ""
    traj = _trajectory_from_predictive(predictive if predictive else None, esc_for_pred)
    sigs = _predictive_signals(bd, predictive if predictive else None, esc_for_pred)
    if sigs:
        sig_rows = ""
        for label, weight in sigs:
            sig_rows += f"""
                <tr>
                    <td style="padding: 8px 10px; border: 1px solid {COLORS['border']}; border-radius: 4px;">
                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                            <tr>
                                <td style="font-size: 12px; color: {COLORS['text_primary']};">{_escape_html(label)}</td>
                                <td align="right" style="font-size: 11px; font-family: monospace; color: {COLORS['text_secondary']};">{weight}/100</td>
                            </tr>
                        </table>
                    </td>
                </tr>
                <tr><td style="height: 6px;"></td></tr>
            """
        pred_block = f"""
                    <tr>
                        <td style="padding: 24px 0; border-top: 1px solid {COLORS['border']};">
                            <p style="color: {COLORS['accent_green']}; font-size: 11px; margin: 0 0 10px 0; text-transform: uppercase; letter-spacing: 1.5px;">Predictive Outlook</p>
                            <p style="color: {COLORS['text_primary']}; font-size: 13px; margin: 0 0 12px 0;">
                                Trajectory: <span style="font-family: monospace;">{traj}</span>
                            </p>
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                {sig_rows}
                            </table>
                        </td>
                    </tr>
        """

    energy = bd.get("energy") if isinstance(bd.get("energy"), dict) else {}
    global_note = energy.get("global_impact_note") if isinstance(energy, dict) else None
    global_note_s = (global_note or "").strip() if isinstance(global_note, str) else ""
    global_html = ""
    if global_note_s:
        global_html = f"""
                    <tr>
                        <td style="padding: 24px 0; border-top: 1px solid {COLORS['border']};">
                            <p style="color: {COLORS['accent_green']}; font-size: 11px; margin: 0 0 10px 0; text-transform: uppercase; letter-spacing: 1.5px;">Global Impact</p>
                            <p style="color: {COLORS['text_primary']}; font-size: 13px; line-height: 1.6; margin: 0;">
                                {_escape_html(global_note_s)}
                            </p>
                        </td>
                    </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: {COLORS['bg_dark']}; font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: {COLORS['bg_dark']};">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 600px;">

                    <!-- Preheader: hidden preview text for email clients -->
                    <tr>
                        <td style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;">
                            {_escape_html(preheader)}
                        </td>
                    </tr>

                    <!-- Header -->
                    <tr>
                        <td style="padding-bottom: 20px; border-bottom: 1px solid {COLORS['border']};">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td>
                                        <span style="color: {COLORS['accent_green']}; font-size: 13px; font-weight: 600; letter-spacing: 2px;">DIGITAL WAR ROOM</span>
                                    </td>
                                    <td align="right">
                                        <span style="color: {COLORS['text_secondary']}; font-size: 12px;">{date_str}</span>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <tr>
                        <td align="right" style="padding: 0 0 16px 0;">
                            <span style="color: {COLORS['text_secondary']}; font-size: 10px; letter-spacing: 0.12em;">UNCLASSIFIED // OPEN SOURCE</span>
                        </td>
                    </tr>

                    <!-- Title & threat (BriefingHeader-style) -->
                    <tr>
                        <td style="padding: 24px 0 16px 0;">
                            <p style="color: {COLORS['text_secondary']}; font-size: 11px; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 1.5px;">Daily Briefing</p>
                            <h1 style="color: {COLORS['text_primary']}; font-size: 22px; font-weight: 600; margin: 0 0 16px 0;">{_escape_html(conflict)}</h1>
                            {escalation_html}
                        </td>
                    </tr>

                    <!-- BLUF -->
                    <tr>
                        <td style="padding: 24px 0; border-top: 1px solid {COLORS['border']}; border-left: 4px solid {threat_color}; padding-left: 16px;">
                            <p style="color: {COLORS['text_secondary']}; font-size: 11px; margin: 0 0 12px 0; text-transform: uppercase; letter-spacing: 1.5px;">BLUF</p>
                            <p style="color: {COLORS['text_primary']}; font-size: 14px; line-height: 1.7; margin: 0;">
                                {_bluf_html(summary)}
                            </p>
                        </td>
                    </tr>

                    <!-- Key Findings -->
                    <tr>
                        <td style="padding: 24px 0; border-top: 1px solid {COLORS['border']};">
                            <p style="color: {COLORS['accent_green']}; font-size: 18px; margin: 0 0 16px 0; font-family: 'Segoe UI', system-ui, sans-serif; font-weight: 600; letter-spacing: -0.02em;">Key Findings</p>
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                {findings_html}
                            </table>
                        </td>
                    </tr>
                    {scenarios_html}
                    {pred_block}
                    {global_html}

                    <!-- CTA -->
                    <tr>
                        <td style="padding: 24px 0; border-top: 1px solid {COLORS['border']};">
                            <table role="presentation" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="background-color: {COLORS['accent_green']}; border-radius: 6px;">
                                        <a href="{view_link}" style="display: inline-block; padding: 12px 24px; color: #000000; font-size: 13px; font-weight: 600; text-decoration: none; letter-spacing: 0.5px;">
                                            VIEW FULL BRIEFING ->
                                        </a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding-top: 32px; border-top: 1px solid {COLORS['border']};">
                            <p style="color: {COLORS['text_secondary']}; font-size: 11px; margin: 0 0 8px 0;">
                                Digital War Room - AI-Powered OSINT Intelligence
                            </p>
                            <p style="color: {COLORS['text_secondary']}; font-size: 11px; margin: 0;">
                                <a href="{unsubscribe_link}" style="color: {COLORS['text_secondary']}; text-decoration: underline;">Unsubscribe</a>
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
    """Plain text version — section titles aligned with Daily Briefing page."""
    bd: Dict[str, Any] = briefing_data if isinstance(briefing_data, dict) else {}
    tl = _normalize_threat_level(threat_level or bd.get("threat_level"))
    try:
        esc_int = int(round(float(escalation_score))) if escalation_score is not None else None
    except (TypeError, ValueError):
        esc_int = None
    if esc_int is not None:
        esc_int = max(0, min(100, esc_int))
    score_line = f"{tl} | {esc_int}/100" if esc_int is not None else tl

    ctx_list = key_findings_context if key_findings_context is not None else bd.get("key_findings_context") or []
    if not isinstance(ctx_list, list):
        ctx_list = []

    lines: list[str] = []
    for i, finding in enumerate(key_findings[:8], 1):
        text = (finding or "").strip()
        if not text:
            continue
        ctx = ctx_list[i - 1] if i - 1 < len(ctx_list) else None
        ctx_s = ctx if isinstance(ctx, str) else None
        _, body = _finding_title_body(text, ctx_s)
        lines.append(f"  {i}. {body}")
        if ctx_s and ctx_s.strip() and ctx_s.strip() != text.strip():
            lines.append(f"      ({ctx_s.strip()})")

    findings_text = "\n".join(lines) if lines else "  (none)"

    esc_for_pred = esc_int if esc_int is not None else 50
    predictive = bd.get("predictive") if isinstance(bd.get("predictive"), dict) else {}
    traj = _trajectory_from_predictive(predictive if predictive else None, esc_for_pred)

    watch_items_txt = _things_to_watch_scenario_dicts(bd, conflict, esc_for_pred)
    scen_lines: list[str] = []
    for s in watch_items_txt:
        desc = (s.get("description") or "").strip()
        if not desc:
            continue
        prob = s.get("probability")
        if isinstance(prob, (int, float)) and not isinstance(prob, bool) and 0 <= float(prob) <= 1:
            scen_lines.append(f"  - {desc} (~{int(round(float(prob) * 100))}%)")
        else:
            scen_lines.append(f"  - {desc}")
    scenarios_block = "THINGS TO WATCH\n" + "\n".join(scen_lines) + "\n\n" if scen_lines else ""

    sig_lines = []
    for label, weight in _predictive_signals(bd, predictive if predictive else None, esc_for_pred):
        sig_lines.append(f"  - {label}: {weight}/100")
    predictive_block = (
        (f"PREDICTIVE OUTLOOK\nTrajectory: {traj}\n" + "\n".join(sig_lines) + "\n\n") if sig_lines else ""
    )

    energy = bd.get("energy") if isinstance(bd.get("energy"), dict) else {}
    gn = energy.get("global_impact_note") if isinstance(energy, dict) else None
    global_block = ""
    if isinstance(gn, str) and gn.strip():
        global_block = f"GLOBAL IMPACT\n{gn.strip()}\n\n"

    return f"""DIGITAL WAR ROOM
UNCLASSIFIED // OPEN SOURCE
Daily Briefing — {conflict} — {date_str}
Threat: {score_line}
{'=' * 50}

BLUF
{summary}

KEY FINDINGS
{findings_text}

{scenarios_block}{predictive_block}{global_block}View full briefing: {view_link}

-
Digital War Room - AI-Powered OSINT Intelligence
Unsubscribe: {unsubscribe_link}
"""


def _escape_html(s: str) -> str:
    """Escape HTML special characters."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
