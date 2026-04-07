import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


async def persist_analysis_side_effects(
    conflict: str, result: dict[str, Any], tenant_id: uuid.UUID | None = None
) -> None:
    """Postgres audit, SIGINT state for compliance deltas, AIS track samples."""
    try:
        from services.analysis_audit_store import persist_analysis_audit
        from services.audit_events import emit_audit_event

        await persist_analysis_audit(conflict, result)
        await emit_audit_event(
            event_type="analysis.audit.persisted",
            actor_type="system",
            tenant_id=str(tenant_id) if tenant_id else None,
            object_type="analysis_run",
            object_id=str(result.get("analysis_run_id") or ""),
            outcome="success",
            reason_code="provenance_snapshot",
            meta={"conflict": conflict},
        )
    except Exception as e:
        logger.warning("persist_analysis_audit failed for %s: %s", conflict, e)
        try:
            from services.monitoring_store import record_error
            from services.audit_events import emit_audit_event

            record_error(
                message=f"analysis_audit persist failed: {e!s}"[:2000],
                severity="warning",
                conflict=conflict,
            )
            await emit_audit_event(
                event_type="analysis.audit.persisted",
                actor_type="system",
                tenant_id=str(tenant_id) if tenant_id else None,
                object_type="analysis_run",
                object_id=str(result.get("analysis_run_id") or ""),
                outcome="failure",
                reason_code="persist_error",
                meta={"conflict": conflict},
            )
        except Exception:
            pass
    try:
        from agents.agent_state_store import get_agent_state_store

        sig = result.get("sigint")
        if isinstance(sig, dict):
            get_agent_state_store().set_result(conflict, "sigint", sig, time.time())
    except Exception as e:
        logger.warning("agent_state_store sigint write failed for %s: %s", conflict, e)
    try:
        from services.quality_store import insert_ais_track_samples
        from services.entity_resolver import resolve_vessel_entity

        sig = result.get("sigint") or {}
        ships = sig.get("ships") or []
        samples: list[dict[str, Any]] = []
        resolved_entities = 0
        now_ts = time.time()
        for s in ships:
            if not isinstance(s, dict) or "error" in s:
                continue
            try:
                entity_id = resolve_vessel_entity(s, tenant_id=tenant_id)
                if entity_id:
                    s["entity_id"] = entity_id
                    resolved_entities += 1
            except Exception:
                pass
            mmsi = s.get("mmsi") or s.get("name")
            if mmsi is None:
                continue
            lat, lon = s.get("lat"), s.get("lon")
            if lat is None or lon is None:
                continue
            ts = s.get("timestamp") or s.get("seen") or now_ts
            samples.append({"mmsi": str(mmsi), "observed_at": ts, "lat": lat, "lon": lon})
        if samples:
            await insert_ais_track_samples(conflict, samples, tenant_id=tenant_id)
        if resolved_entities:
            logger.info("entity_resolver resolved %d vessels for %s", resolved_entities, conflict)
    except Exception as e:
        logger.warning("insert_ais_track_samples failed for %s: %s", conflict, e)
    try:
        from services.alert_rules_engine import evaluate_and_notify

        tid_str = str(tenant_id) if tenant_id else None
        evaluate_and_notify(conflict, result, tenant_id=tid_str)
    except Exception as e:
        logger.warning("evaluate_and_notify alerts failed for %s: %s", conflict, e)
    try:
        from services.agent_snapshot_store import persist_agent_snapshots_for_result

        snapshot_count = persist_agent_snapshots_for_result(conflict=conflict, result=result, tenant_id=tenant_id)
        if snapshot_count:
            logger.info("agent_snapshot_store persisted %d snapshots for %s", snapshot_count, conflict)
    except Exception as e:
        logger.warning("agent_snapshot_store persist failed for %s: %s", conflict, e)
