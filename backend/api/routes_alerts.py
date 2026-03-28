"""
User alert rules CRUD and in-app notification inbox.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

from middleware.tenant_context import get_request_ctx
from services import alert_rules_store as store
from services.alert_rules_engine import VALID_KINDS, evaluate_and_notify
from utils.sanitize import CONFLICT_MAX_LEN, sanitize_conflict

logger = logging.getLogger(__name__)

router = APIRouter()


class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    rule_kind: str
    conflict_substring: str = ""
    keyword: Optional[str] = None
    min_escalation: Optional[float] = None
    threat_levels: Optional[str] = None
    notify_email: Optional[str] = None
    enabled: bool = True

    @field_validator("rule_kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        v = (v or "").strip()
        if v not in VALID_KINDS:
            raise ValueError(f"rule_kind must be one of {sorted(VALID_KINDS)}")
        return v


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    conflict_substring: Optional[str] = None
    rule_kind: Optional[str] = None
    keyword: Optional[str] = None
    min_escalation: Optional[float] = None
    threat_levels: Optional[str] = None
    notify_email: Optional[str] = None

    @field_validator("rule_kind")
    @classmethod
    def _kind(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if v not in VALID_KINDS:
            raise ValueError(f"rule_kind must be one of {sorted(VALID_KINDS)}")
        return v


class EvaluateBody(BaseModel):
    conflict: str = Field(..., min_length=1, max_length=CONFLICT_MAX_LEN)

    @field_validator("conflict", mode="before")
    @classmethod
    def _strip(cls, v: object) -> str:
        if not isinstance(v, str):
            raise TypeError("conflict must be a string")
        return v.strip()

    @field_validator("conflict")
    @classmethod
    def _val(cls, v: str) -> str:
        return sanitize_conflict(v)


def _tid(request: Request) -> str:
    return str(get_request_ctx(request).tenant_id)


@router.get("/alerts/rules")
async def list_alert_rules(request: Request) -> Any:
    return {"rules": store.list_rules(tenant_id=_tid(request))}


@router.post("/alerts/rules")
async def create_alert_rule(request: Request, body: AlertRuleCreate) -> Any:
    r = store.create_rule(
        name=body.name,
        rule_kind=body.rule_kind,
        conflict_substring=body.conflict_substring,
        keyword=body.keyword,
        min_escalation=body.min_escalation,
        threat_levels=body.threat_levels,
        notify_email=body.notify_email,
        enabled=body.enabled,
        tenant_id=_tid(request),
    )
    return {"rule": r}


@router.patch("/alerts/rules/{rule_id}")
async def patch_alert_rule(request: Request, rule_id: str, body: AlertRuleUpdate) -> Any:
    r = store.update_rule(
        rule_id,
        name=body.name,
        enabled=body.enabled,
        conflict_substring=body.conflict_substring,
        rule_kind=body.rule_kind,
        keyword=body.keyword,
        min_escalation=body.min_escalation,
        threat_levels=body.threat_levels,
        notify_email=body.notify_email,
        tenant_id=_tid(request),
    )
    if not r:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"error": "rule_not_found"})
    return {"rule": r}


@router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(request: Request, rule_id: str) -> Any:
    ok = store.delete_rule(rule_id, tenant_id=_tid(request))
    if not ok:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"error": "rule_not_found"})
    return {"ok": True}


@router.get("/alerts/notifications")
async def list_notifications(request: Request, limit: int = 50, unread_only: bool = False) -> Any:
    lim = max(1, min(limit, 200))
    return {
        "notifications": store.list_notifications(limit=lim, unread_only=unread_only, tenant_id=_tid(request)),
        "unread_count": store.unread_count(tenant_id=_tid(request)),
    }


@router.post("/alerts/notifications/read-all")
async def read_all_notifications(request: Request) -> Any:
    n = store.mark_all_read(tenant_id=_tid(request))
    return {"marked": n}


@router.post("/alerts/notifications/{notification_id}/read")
async def read_one_notification(request: Request, notification_id: str) -> Any:
    ok = store.mark_read(notification_id, tenant_id=_tid(request))
    if not ok:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"error": "not_found"})
    return {"ok": True}


@router.post("/alerts/evaluate")
async def evaluate_alerts_manual(request: Request, body: EvaluateBody) -> Any:
    """
    Re-run rules against latest cached analysis for conflict (for testing / catch-up).
    """
    from .state_helpers import get_cache

    entry = get_cache(request, body.conflict)
    if not entry or not isinstance(entry.get("result"), dict):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=404,
            content={"error": "no_cached_analysis", "conflict": body.conflict},
        )
    result = entry["result"]
    n = evaluate_and_notify(body.conflict, result, tenant_id=_tid(request))
    return {"created": n, "conflict": body.conflict}
