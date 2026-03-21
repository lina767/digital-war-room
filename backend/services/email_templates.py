"""
Digital War Room - Branded Email Templates
Dark military-tech design matching the website.

Usage: Replace the html strings in newsletter_sender.py with these function calls.
"""

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
) -> str:
    """
    Daily briefing email - matches DWR intelligence feed style.
    """
    # Escalation badge color
    if escalation_score is not None:
        if escalation_score >= 70:
            badge_color = "#f85149"  # Red - HIGH
            badge_text = "HIGH"
        elif escalation_score >= 40:
            badge_color = "#d29922"  # Yellow/Orange - MEDIUM
            badge_text = "MEDIUM"
        else:
            badge_color = COLORS["accent_green"]  # Green - LOW
            badge_text = "LOW"
        escalation_html = f"""
            <span style="display: inline-block; background-color: {badge_color}; color: #000; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 4px; letter-spacing: 1px;">
                {badge_text}
            </span>
            <span style="color: {COLORS['text_secondary']}; font-size: 12px; margin-left: 8px;">
                Score: {escalation_score}/100
            </span>
        """
    else:
        escalation_html = ""

    # Inbox preheader (hidden snippet line; many clients show this next to subject)
    snippet = (summary or "").strip().replace("\n", " ")
    if len(snippet) > 130:
        snippet = snippet[:127] + "..."
    preheader = f"{conflict} — {snippet}" if snippet else f"Daily intelligence briefing for {conflict}"

    # Key findings list
    findings_html = ""
    for i, finding in enumerate(key_findings[:8], 1):
        findings_html += f"""
            <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid {COLORS['border']};">
                    <span style="color: {COLORS['accent_green']}; font-size: 12px; margin-right: 8px;">{i}.</span>
                    <span style="color: {COLORS['text_primary']}; font-size: 13px; line-height: 1.5;">{_escape_html(finding)}</span>
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

                    <!-- Title & Escalation -->
                    <tr>
                        <td style="padding: 24px 0 16px 0;">
                            <p style="color: {COLORS['text_secondary']}; font-size: 11px; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 1.5px;">Daily Briefing</p>
                            <h1 style="color: {COLORS['text_primary']}; font-size: 22px; font-weight: 600; margin: 0 0 16px 0;">{_escape_html(conflict)}</h1>
                            {escalation_html}
                        </td>
                    </tr>

                    <!-- Executive Summary -->
                    <tr>
                        <td style="padding: 24px 0; border-top: 1px solid {COLORS['border']};">
                            <p style="color: {COLORS['accent_green']}; font-size: 11px; margin: 0 0 12px 0; text-transform: uppercase; letter-spacing: 1.5px;">Executive Summary</p>
                            <p style="color: {COLORS['text_primary']}; font-size: 14px; line-height: 1.7; margin: 0;">
                                {_escape_html(summary)}
                            </p>
                        </td>
                    </tr>

                    <!-- Key Findings -->
                    <tr>
                        <td style="padding: 24px 0; border-top: 1px solid {COLORS['border']};">
                            <p style="color: {COLORS['accent_green']}; font-size: 11px; margin: 0 0 16px 0; text-transform: uppercase; letter-spacing: 1.5px;">Key Developments</p>
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                {findings_html}
                            </table>
                        </td>
                    </tr>

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
) -> str:
    """Plain text version of daily briefing."""
    findings_text = "\n".join(f"  {i}. {f}" for i, f in enumerate(key_findings[:8], 1))
    score_text = f" (Score: {escalation_score}/100)" if escalation_score else ""

    return f"""DIGITAL WAR ROOM
Daily Briefing - {conflict} - {date_str}{score_text}
{'=' * 50}

EXECUTIVE SUMMARY
{summary}

KEY DEVELOPMENTS
{findings_text}

View full briefing: {view_link}

-
Digital War Room - AI-Powered OSINT Intelligence
Unsubscribe: {unsubscribe_link}
"""


def _escape_html(s: str) -> str:
    """Escape HTML special characters."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
