"""
Evaluate user alert rules against analysis results; persist notifications and optional email.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

from services import alert_rules_store as store

logger = logging.getLogger(__name__)

VALID_KINDS = frozenset({"keyword", "escalation_min", "threat_level"})


def _norm_conflict(rule_sub: str, conflict: str) -> bool:
    if not (rule_sub or "").strip():
        return True
    return rule_sub.lower() in (conflict or "").lower()


def _collect_search_blob(result: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ("summary", "narrative_story"):
        v = result.get(key)
        if isinstance(v, str):
            parts.append(v)
    for kf in result.get("key_findings") or []:
        if isinstance(kf, str):
            parts.append(kf)
    news = result.get("news") or {}
    if isinstance(news, dict):
        for art in news.get("articles") or news.get("headlines") or []:
            if isinstance(art, dict):
                parts.append(str(art.get("title") or ""))
                parts.append(str(art.get("description") or ""))
            elif isinstance(art, str):
                parts.append(art)
    return "\n".join(parts).lower()


def _threat_match(level: str, csv: Optional[str]) -> bool:
    if not csv or not csv.strip():
        return False
    allowed = {x.strip().upper() for x in csv.split(",") if x.strip()}
    return (level or "").upper() in allowed


def _fingerprint(rule_id: str, conflict: str, kind: str, detail: str) -> str:
    raw = f"{rule_id}|{conflict}|{kind}|{detail}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def evaluate_and_notify(
    conflict: str,
    result: Dict[str, Any],
    *,
    tenant_id: Optional[str] = None,
) -> int:
    """
    Run all enabled rules for tenant; insert notifications for matches.
    Returns number of new notifications created.
    """
    rules = store.list_enabled_rules(tenant_id=tenant_id)
    if not rules:
        return 0
    esc = float(result.get("escalation_score") or 0.0)
    threat = str(result.get("threat_level") or "").upper()
    blob = _collect_search_blob(result)
    created = 0
    for rule in rules:
        rid = rule["id"]
        if not _norm_conflict(rule.get("conflict_substring") or "", conflict):
            continue
        kind = rule.get("rule_kind") or ""
        if kind not in VALID_KINDS:
            continue
        matched = False
        detail = ""
        if kind == "keyword":
            kw = (rule.get("keyword") or "").strip().lower()
            if not kw:
                continue
            if kw in blob:
                matched = True
                detail = f"keyword:{kw}"
        elif kind == "escalation_min":
            min_e = rule.get("min_escalation")
            if min_e is None:
                continue
            try:
                thr = float(min_e)
            except (TypeError, ValueError):
                continue
            if esc >= thr:
                matched = True
                detail = f"escalation:{esc:.2f}>={thr:.2f}"
        elif kind == "threat_level":
            if _threat_match(threat, rule.get("threat_levels")):
                matched = True
                detail = f"threat:{threat}"
        if not matched:
            continue
        fp = _fingerprint(rid, conflict, kind, detail)
        if store.notification_exists_fingerprint(
            rule_id=rid, conflict=conflict, fingerprint=fp, tenant_id=tenant_id
        ):
            continue
        title = f"Alert: {rule.get('name') or 'Rule'}"
        body = f"{conflict}: {detail}"
        payload: Dict[str, Any] = {
            "fingerprint": fp,
            "rule_kind": kind,
            "escalation_score": esc,
            "threat_level": threat,
            "detail": detail,
        }
        store.insert_notification(
            rule_id=rid,
            conflict=conflict,
            title=title,
            body=body,
            payload=payload,
            fingerprint=fp,
            tenant_id=tenant_id,
        )
        created += 1
        notify_email = (rule.get("notify_email") or "").strip()
        if notify_email and re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", notify_email):
            try:
                from services.alert_rules_email import send_rule_match_email

                send_rule_match_email(
                    to_email=notify_email,
                    rule_name=rule.get("name") or "Rule",
                    conflict=conflict,
                    body=body,
                    title=title,
                )
            except Exception as e:
                logger.warning("alert email failed: %s", e)
    return created
