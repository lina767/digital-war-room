from __future__ import annotations

import logging
import os
from typing import Any

from services.audit_events import emit_audit_event, prune_compliance_audit_events

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


async def run_retention_once() -> dict[str, Any]:
    """
    Run retention cleanup jobs and emit one summary audit event.
    Best-effort by design: partial failures should not crash the process.
    """
    deleted: dict[str, int] = {}
    failed: list[str] = []

    newsletter_pending_days = _env_int("RETENTION_NEWSLETTER_PENDING_DAYS", 30)
    analysis_audit_days = _env_int("RETENTION_ANALYSIS_AUDIT_DAYS", 180)
    compliance_audit_days = _env_int("RETENTION_COMPLIANCE_AUDIT_DAYS", 365)
    document_cache_hours = _env_int("RETENTION_DOCUMENT_CACHE_HOURS", 72)
    embeddings_days = _env_int("RETENTION_EMBEDDINGS_DAYS", 180)

    try:
        from services.newsletter_store import purge_pending_subscribers_older_than

        deleted["newsletter_pending"] = purge_pending_subscribers_older_than(newsletter_pending_days)
    except Exception as e:
        logger.warning("retention newsletter cleanup failed: %s", e)
        failed.append("newsletter_pending")

    try:
        from services.analysis_audit_store import prune_analysis_audit

        deleted["analysis_audit"] = await prune_analysis_audit(analysis_audit_days)
    except Exception as e:
        logger.warning("retention analysis_audit cleanup failed: %s", e)
        failed.append("analysis_audit")

    try:
        from services.pdf_ingest_service import purge_in_memory_documents

        deleted["documents_memory"] = purge_in_memory_documents(document_cache_hours)
    except Exception as e:
        logger.warning("retention document cache cleanup failed: %s", e)
        failed.append("documents_memory")

    try:
        from services.storage_service import prune_old_embeddings

        deleted["embeddings"] = await prune_old_embeddings(embeddings_days)
    except Exception as e:
        logger.warning("retention embeddings cleanup failed: %s", e)
        failed.append("embeddings")

    try:
        deleted["compliance_audit"] = await prune_compliance_audit_events(compliance_audit_days)
    except Exception as e:
        logger.warning("retention compliance audit cleanup failed: %s", e)
        failed.append("compliance_audit")

    outcome = "failure" if failed else "success"
    await emit_audit_event(
        event_type="retention.job.executed",
        actor_type="system",
        object_type="retention_job",
        object_id="daily_retention",
        outcome=outcome,
        reason_code="scheduled_cleanup",
        meta={"deleted": deleted, "failed": failed},
    )
    return {"deleted": deleted, "failed": failed, "outcome": outcome}

