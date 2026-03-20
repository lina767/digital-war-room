"""
Reusable newsletter email templates (HTML + plain text).
"""

from __future__ import annotations

from typing import Any


def _escape_html(value: Any) -> str:
    s = str(value)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def confirmation_email_html(conflict: str, link: str) -> str:
    safe_conflict = _escape_html(conflict)
    safe_link = _escape_html(link)
    return f"""
    <p>You requested the Daily Briefing for <strong>{safe_conflict}</strong>.</p>
    <p>Click the link below to confirm your subscription:</p>
    <p><a href="{safe_link}">Confirm subscription</a></p>
    <p>If you did not request this, you can ignore this email.</p>
    <p style="color:#666;font-size:12px;">Digital War Room - Geopolitical intelligence briefings</p>
    """


def confirmation_email_text(conflict: str, link: str) -> str:
    return (
        f"You requested the Daily Briefing for {conflict}.\n\n"
        f"Confirm your subscription: {link}\n\n"
        "If you did not request this, you can ignore this email."
    )


def daily_briefing_email_html(
    *,
    conflict: str,
    date_str: str,
    summary: str,
    key_findings: list[Any],
    escalation_score: Any,
    view_link: str,
    unsubscribe_link: str,
) -> str:
    findings_list = "\n".join(f"<li>{_escape_html(item)}</li>" for item in key_findings[:10])
    score_line = ""
    if escalation_score is not None:
        score_line = f"<p><strong>Escalation score:</strong> {_escape_html(escalation_score)}</p>"

    return f"""
    <h2>Daily Briefing - {_escape_html(conflict)} - {_escape_html(date_str)}</h2>
    {score_line}
    <p><strong>Executive Summary</strong></p>
    <p>{_escape_html(summary)}</p>
    <p><strong>Key developments</strong></p>
    <ul>{findings_list}</ul>
    <p><a href="{_escape_html(view_link)}">View full briefing online</a></p>
    <hr style="margin-top:24px;border:none;border-top:1px solid #eee;">
    <p style="color:#666;font-size:12px;">
      You received this because you subscribed to the Daily Briefing.
      <a href="{_escape_html(unsubscribe_link)}">Unsubscribe</a>.
    </p>
    """


def daily_briefing_email_text(
    *,
    conflict: str,
    date_str: str,
    summary: str,
    key_findings: list[Any],
    escalation_score: Any,
    view_link: str,
    unsubscribe_link: str,
) -> str:
    text_findings = "\n".join(f"- {item}" for item in key_findings[:10]) or "- No key developments available."
    score_line = f"Escalation score: {escalation_score}\n\n" if escalation_score is not None else ""
    return (
        f"Daily Briefing - {conflict} - {date_str}\n\n"
        f"{score_line}"
        f"Executive Summary:\n{summary}\n\n"
        f"Key developments:\n{text_findings}\n\n"
        f"View full briefing online: {view_link}\n"
        f"Unsubscribe: {unsubscribe_link}"
    )
