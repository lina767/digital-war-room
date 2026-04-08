"""
Layer 4 deterministic diff engine.

Compares two analysis runs based on Layer 3 agent snapshots and returns a
structured delta for API/UI/newsletter use.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.agent_snapshot_store import (
    list_recent_run_ids,
    load_agent_blocks_for_run,
)


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _list_of_dicts(v: Any) -> List[Dict[str, Any]]:
    if not isinstance(v, list):
        return []
    return [x for x in v if isinstance(x, dict)]


def _list_of_str(v: Any) -> List[str]:
    if not isinstance(v, list):
        return []
    out: List[str] = []
    for item in v:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _dict_item_key(d: Dict[str, Any], fallback_fields: List[str]) -> str:
    for key in fallback_fields:
        val = d.get(key)
        if isinstance(val, str) and val.strip():
            return f"{key}:{val.strip().lower()}"
        if val is not None:
            return f"{key}:{str(val)}"
    return str(hash(str(sorted(d.items()))))


def _extract_agent_score(block: Dict[str, Any]) -> Optional[float]:
    preferred = (
        "escalation_score",
        "sigint_score",
        "geoint_score",
        "satintel_score",
        "proximity_score",
        "chokepoint_score",
        "energy_score",
        "news_score",
        "socmint_score",
        "narrative_score",
        "diplo_score",
        "techint_score",
        "cyber_score",
        "pentagon_score",
    )
    for key in preferred:
        if key in block:
            score = _safe_float(block.get(key))
            if score is not None:
                return score
    for key, val in block.items():
        if key.endswith("_score"):
            score = _safe_float(val)
            if score is not None:
                return score
    return None


def _diff_generic(prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
    prev_summary = str(prev.get("summary") or "").strip()
    curr_summary = str(curr.get("summary") or "").strip()
    prev_score = _extract_agent_score(prev)
    curr_score = _extract_agent_score(curr)
    score_delta = round(curr_score - prev_score, 2) if prev_score is not None and curr_score is not None else None
    return {
        "summary_changed": prev_summary != curr_summary,
        "score_prev": prev_score,
        "score_curr": curr_score,
        "score_delta": score_delta,
    }


def _diff_finint(prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
    prev_sdn = _list_of_dicts((prev.get("ofac_sanctions") or {}).get("sample"))
    curr_sdn = _list_of_dicts((curr.get("ofac_sanctions") or {}).get("sample"))
    prev_sdn_keys = {_dict_item_key(x, ["name", "program"]) for x in prev_sdn}
    curr_sdn_keys = {_dict_item_key(x, ["name", "program"]) for x in curr_sdn}

    prev_poly = _list_of_dicts(prev.get("polymarket"))
    curr_poly = _list_of_dicts(curr.get("polymarket"))
    prev_poly_map = {
        str(x.get("question") or x.get("title") or "").strip().lower(): _safe_float(x.get("probability"))
        for x in prev_poly
        if str(x.get("question") or x.get("title") or "").strip()
    }
    curr_poly_map = {
        str(x.get("question") or x.get("title") or "").strip().lower(): _safe_float(x.get("probability"))
        for x in curr_poly
        if str(x.get("question") or x.get("title") or "").strip()
    }
    prob_shifts: List[Dict[str, Any]] = []
    for q, curr_prob in curr_poly_map.items():
        prev_prob = prev_poly_map.get(q)
        if prev_prob is None or curr_prob is None:
            continue
        delta = curr_prob - prev_prob
        if abs(delta) >= 0.05:
            prob_shifts.append({"question": q, "prev": round(prev_prob, 3), "curr": round(curr_prob, 3), "delta": round(delta, 3)})

    return {
        "new_sanctions_count": len(curr_sdn_keys - prev_sdn_keys),
        "removed_sanctions_count": len(prev_sdn_keys - curr_sdn_keys),
        "probability_shifts_over_5pct": prob_shifts[:20],
    }


def _diff_chokepoint(prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
    prev_cp = _list_of_dicts(prev.get("chokepoints"))
    curr_cp = _list_of_dicts(curr.get("chokepoints"))
    prev_keys = {_dict_item_key(x, ["name", "chokepoint", "location"]) for x in prev_cp}
    curr_keys = {_dict_item_key(x, ["name", "chokepoint", "location"]) for x in curr_cp}
    return {
        "new_chokepoint_items": len(curr_keys - prev_keys),
        "resolved_chokepoint_items": len(prev_keys - curr_keys),
    }


def _diff_proximity(prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
    prev_evidence = _list_of_dicts(prev.get("evidence"))
    curr_evidence = _list_of_dicts(curr.get("evidence"))
    prev_keys = {_dict_item_key(x, ["mmsi", "imo", "name", "vessel"]) for x in prev_evidence}
    curr_keys = {_dict_item_key(x, ["mmsi", "imo", "name", "vessel"]) for x in curr_evidence}
    return {
        "entered_or_new_vessels": len(curr_keys - prev_keys),
        "exited_or_resolved_vessels": len(prev_keys - curr_keys),
    }


def _diff_cyber(prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
    prev_kev = _list_of_dicts(prev.get("cisa_kev"))
    curr_kev = _list_of_dicts(curr.get("cisa_kev"))
    prev_kev_keys = {_dict_item_key(x, ["cve", "vulnerabilityName"]) for x in prev_kev}
    curr_kev_keys = {_dict_item_key(x, ["cve", "vulnerabilityName"]) for x in curr_kev}
    prev_otx = _list_of_dicts(prev.get("otx_pulses"))
    curr_otx = _list_of_dicts(curr.get("otx_pulses"))
    prev_otx_keys = {_dict_item_key(x, ["id", "name", "title"]) for x in prev_otx}
    curr_otx_keys = {_dict_item_key(x, ["id", "name", "title"]) for x in curr_otx}
    return {
        "new_kev_items": len(curr_kev_keys - prev_kev_keys),
        "new_otx_pulses": len(curr_otx_keys - prev_otx_keys),
    }


def _agent_specific_diff(agent_name: str, prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
    if agent_name == "finint":
        return _diff_finint(prev, curr)
    if agent_name == "chokepoint":
        return _diff_chokepoint(prev, curr)
    if agent_name == "proximity":
        return _diff_proximity(prev, curr)
    if agent_name == "cyber":
        return _diff_cyber(prev, curr)
    return {}


def _global_diff(prev_blocks: Dict[str, Dict[str, Any]], curr_blocks: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    prev_fin = ((prev_blocks.get("finint") or {}).get("output") or {})
    curr_fin = ((curr_blocks.get("finint") or {}).get("output") or {})
    prev_escalation = _safe_float(prev_fin.get("escalation_score"))
    curr_escalation = _safe_float(curr_fin.get("escalation_score"))
    escalation_delta = (
        round(curr_escalation - prev_escalation, 2)
        if prev_escalation is not None and curr_escalation is not None
        else None
    )
    prev_threat = str((prev_fin.get("threat_level") or "")).strip() or None
    curr_threat = str((curr_fin.get("threat_level") or "")).strip() or None
    prev_findings = set(_list_of_str((prev_fin.get("key_findings") or [])))
    curr_findings = set(_list_of_str((curr_fin.get("key_findings") or [])))
    return {
        "escalation_score_prev": prev_escalation,
        "escalation_score_curr": curr_escalation,
        "escalation_score_delta": escalation_delta,
        "threat_level_prev": prev_threat,
        "threat_level_curr": curr_threat,
        "key_findings_added": sorted(list(curr_findings - prev_findings))[:50],
        "key_findings_resolved": sorted(list(prev_findings - curr_findings))[:50],
    }


def diff_runs(
    *,
    conflict: str,
    run_id_prev: str,
    run_id_curr: str,
    tenant_id: Any = None,
) -> Dict[str, Any]:
    prev_blocks = load_agent_blocks_for_run(run_id=run_id_prev, conflict=conflict, tenant_id=tenant_id)
    curr_blocks = load_agent_blocks_for_run(run_id=run_id_curr, conflict=conflict, tenant_id=tenant_id)
    if not prev_blocks:
        return {"error": "previous_run_not_found", "run_id_prev": run_id_prev}
    if not curr_blocks:
        return {"error": "current_run_not_found", "run_id_curr": run_id_curr}

    agents = sorted(set(prev_blocks.keys()) | set(curr_blocks.keys()))
    agent_diffs: Dict[str, Any] = {}
    changed_agents = 0
    for agent in agents:
        prev_row = prev_blocks.get(agent) or {}
        curr_row = curr_blocks.get(agent) or {}
        prev_output = prev_row.get("output") if isinstance(prev_row.get("output"), dict) else {}
        curr_output = curr_row.get("output") if isinstance(curr_row.get("output"), dict) else {}
        hash_changed = (prev_row.get("content_hash") or "") != (curr_row.get("content_hash") or "")
        if hash_changed:
            changed_agents += 1
        agent_diffs[agent] = {
            "present_prev": bool(prev_row),
            "present_curr": bool(curr_row),
            "content_hash_changed": hash_changed,
            "generic": _diff_generic(prev_output, curr_output),
            "specific": _agent_specific_diff(agent, prev_output, curr_output),
        }

    return {
        "conflict": conflict,
        "run_id_prev": run_id_prev,
        "run_id_curr": run_id_curr,
        "summary": {
            "agents_total": len(agents),
            "agents_changed": changed_agents,
            "agents_unchanged": max(0, len(agents) - changed_agents),
        },
        "global": _global_diff(prev_blocks, curr_blocks),
        "agents": agent_diffs,
    }


def auto_pick_runs_for_diff(
    *,
    conflict: str,
    tenant_id: Any = None,
) -> Optional[Dict[str, str]]:
    run_ids = list_recent_run_ids(conflict=conflict, tenant_id=tenant_id, limit=2)
    if len(run_ids) < 2:
        return None
    # list_recent_run_ids returns newest first
    return {"run_id_curr": run_ids[0], "run_id_prev": run_ids[1]}
