"""
Layer 5 materialization job.

Builds one daily world snapshot per conflict from Layer 3 snapshots and Layer 4
deterministic diff output.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from services.agent_snapshot_store import (
    list_recent_run_ids,
    load_agent_blocks_for_run,
)
from services.daily_snapshot_store import upsert_daily_snapshot
from services.diff_engine import diff_runs


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _extract_agent_scores(blocks: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for agent, row in blocks.items():
        out = row.get("output") if isinstance(row.get("output"), dict) else {}
        score = None
        for key, val in out.items():
            if key.endswith("_score"):
                score = _safe_float(val)
                if score is not None:
                    break
        if score is not None:
            scores[agent] = round(score, 2)
    return scores


def _extract_top_signals(diff: Dict[str, Any]) -> List[Dict[str, Any]]:
    agents = diff.get("agents") if isinstance(diff.get("agents"), dict) else {}
    out: List[Dict[str, Any]] = []
    for agent, payload in agents.items():
        if not isinstance(payload, dict):
            continue
        generic = payload.get("generic") if isinstance(payload.get("generic"), dict) else {}
        delta = _safe_float(generic.get("score_delta"))
        if delta is None or abs(delta) < 0.01:
            continue
        out.append(
            {
                "agent": agent,
                "score_delta": round(delta, 2),
                "direction": "up" if delta > 0 else "down",
                "summary_changed": bool(generic.get("summary_changed")),
            }
        )
    out.sort(key=lambda x: abs(float(x.get("score_delta") or 0.0)), reverse=True)
    return out[:10]


def _extract_chokepoint_status(curr_blocks: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    cp = ((curr_blocks.get("chokepoint") or {}).get("output") or {})
    points = cp.get("chokepoints")
    if not isinstance(points, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in points:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("chokepoint") or item.get("location")
        if not name:
            continue
        status = item.get("status") or item.get("threat_level") or item.get("risk")
        out.append({"name": str(name), "status": status, "raw": item})
    return out[:20]


def _extract_active_entities(curr_blocks: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    sig = ((curr_blocks.get("sigint") or {}).get("output") or {})
    ships = sig.get("ships")
    if not isinstance(ships, list):
        return []
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for ship in ships:
        if not isinstance(ship, dict):
            continue
        entity_id = str(ship.get("entity_id") or "").strip()
        if not entity_id or entity_id in seen:
            continue
        seen.add(entity_id)
        out.append(
            {
                "entity_id": entity_id,
                "name": ship.get("name"),
                "imo": ship.get("imo") or ship.get("imo_number"),
                "mmsi": ship.get("mmsi"),
                "lat": ship.get("lat"),
                "lon": ship.get("lon"),
            }
        )
    return out[:300]


def materialize_daily_snapshot(
    *,
    conflict: str,
    tenant_id: Any = None,
    snapshot_date: Optional[date] = None,
) -> Dict[str, Any]:
    run_ids = list_recent_run_ids(conflict=conflict, tenant_id=tenant_id, limit=2)
    if not run_ids:
        return {"status": "no_runs", "conflict": conflict}

    run_id_curr = run_ids[0]
    run_id_prev = run_ids[1] if len(run_ids) > 1 else run_ids[0]
    curr_blocks = load_agent_blocks_for_run(run_id=run_id_curr, conflict=conflict, tenant_id=tenant_id)
    if not curr_blocks:
        return {"status": "no_blocks", "conflict": conflict, "run_id_curr": run_id_curr}

    diff = diff_runs(
        conflict=conflict,
        run_id_prev=run_id_prev,
        run_id_curr=run_id_curr,
        tenant_id=tenant_id,
    )
    # If previous run is missing, keep a minimal deterministic structure.
    if diff.get("error"):
        diff = {"summary": {"agents_total": len(curr_blocks), "agents_changed": 0, "agents_unchanged": len(curr_blocks)}}

    payload = {
        "top_signals": _extract_top_signals(diff),
        "chokepoint_status": _extract_chokepoint_status(curr_blocks),
        "agent_scores": _extract_agent_scores(curr_blocks),
        "active_entities": _extract_active_entities(curr_blocks),
        "diff_vs_prior": {
            "run_id_prev": run_id_prev,
            "run_id_curr": run_id_curr,
            **diff,
        },
    }

    snap_date = snapshot_date or datetime.now(timezone.utc).date()
    snapshot_id = upsert_daily_snapshot(
        conflict=conflict,
        snapshot_date=snap_date,
        payload=payload,
        tenant_id=tenant_id,
    )
    if not snapshot_id:
        return {"status": "persist_failed", "conflict": conflict, "snapshot_date": snap_date.isoformat()}

    return {
        "status": "ok",
        "conflict": conflict,
        "snapshot_date": snap_date.isoformat(),
        "snapshot_id": snapshot_id,
        "run_id_prev": run_id_prev,
        "run_id_curr": run_id_curr,
        "top_signals_count": len(payload["top_signals"]),
        "active_entities_count": len(payload["active_entities"]),
    }
