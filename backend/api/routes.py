"""
API routes – aggregate router. All route groups are split into dedicated modules;
this module only mounts them and re-exports push_* for main.py.
"""

from fastapi import APIRouter

from .routes_analyze import router as analyze_router
from .routes_compliance import router as compliance_router
from .routes_documents import router as documents_router
from .routes_geoint import router as geoint_router
from .routes_iaea import router as iaea_router
from .routes_newsletter import router as newsletter_router
from .routes_proximity import router as proximity_router
from .routes_resend_webhooks import router as resend_webhooks_router
from .routes_demo import router as demo_router
from .routes_tenant import router as tenant_router
from .routes_alerts import router as alerts_router
from .state_helpers import (
    push_agent_status,
    push_escalation_timeline,
    push_run_history,
)

router = APIRouter()

router.include_router(analyze_router, tags=["analyze"])
router.include_router(compliance_router, tags=["compliance"])
router.include_router(documents_router, tags=["documents"])
router.include_router(geoint_router, tags=["geoint"])
router.include_router(iaea_router, tags=["iaea"])
router.include_router(newsletter_router, tags=["newsletter"])
router.include_router(proximity_router, tags=["proximity"])
router.include_router(resend_webhooks_router, tags=["webhooks"])
router.include_router(demo_router, tags=["demo"])
router.include_router(tenant_router, tags=["auth", "tenant"])
router.include_router(alerts_router, tags=["alerts"])

# Re-export for main.py (periodic analysis and WebSocket broadcast)
__all__ = ["router", "push_escalation_timeline", "push_agent_status", "push_run_history"]
