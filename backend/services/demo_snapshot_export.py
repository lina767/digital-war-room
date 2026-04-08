"""
Build and persist sanitized demo snapshots from cached analysis endpoints.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import urlopen

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "demo" / "demo_snapshot.json"

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "token",
    "secret",
    "authorization",
    "auth",
    "email",
    "phone",
    "wallet",
    "wallets",
    "tracked_wallets",
    "tracked_chain_wallets",
}

AGENT_KEYS = [
    "finint",
    "sigint",
    "news",
    "geoint",
    "satintel",
    "socmint",
    "techint",
    "cyber",
    "energy",
    "diplo",
    "proximity",
    "narrative",
    "chokepoint",
    "pentagon",
]


def _http_json(url: str, timeout: int) -> dict[str, Any]:
    with urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            lk = k.lower()
            if lk in SENSITIVE_KEYS:
                out[k] = "[redacted]"
            elif lk in {"url", "reference_url"}:
                out[k] = "https://example.invalid/redacted"
            else:
                out[k] = _scrub(v)
        return out
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _build_precomputed_agent_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in AGENT_KEYS:
        block = payload.get(key)
        if not isinstance(block, dict):
            continue
        score = None
        for candidate in ("escalation_score", f"{key}_score"):
            if isinstance(block.get(candidate), (int, float)):
                score = float(block[candidate])
                break
        if score is None:
            continue
        meta = block.get("_meta") if isinstance(block.get("_meta"), dict) else {}
        conf = meta.get("confidence", {}) if isinstance(meta.get("confidence"), dict) else {}
        rows.append(
            {
                "agent": key.upper(),
                "score": round(score),
                "confidence": str(conf.get("level", "medium")).lower(),
                "data_freshness": str(meta.get("data_freshness", "unavailable")).lower(),
                "contribution": f"Derived from real run export ({key}).",
            }
        )
    return rows


def build_demo_snapshot(
    *,
    conflict: str = "Yemen",
    timeout: int = 45,
    base_url: str = "http://127.0.0.1:8000",
) -> dict[str, Any]:
    conflict_enc = quote(conflict)
    analyze_url = f"{base_url}/api/analyze/latest?conflict={conflict_enc}"
    timeline_url = f"{base_url}/api/analyze/timeline?conflict={conflict_enc}"
    analysis = _http_json(analyze_url, timeout=timeout)
    timeline = _http_json(timeline_url, timeout=timeout)

    clean = _scrub(deepcopy(analysis))
    clean["_demo"] = True
    clean["snapshot_source"] = "historical_run"
    clean["scenario_id"] = f"demo-{conflict.lower().replace(' ', '-')}-{datetime.now(timezone.utc).date().isoformat()}"
    clean["scenario_title"] = f"{conflict} - Sanitized Historical Snapshot"
    clean["scenario_note"] = "Generated from a real cached analysis run and sanitized for demo traffic."
    clean["score_timeline"] = [
        {"label": p.get("label") or p.get("label_with_date") or "t", "escalation_score": p.get("escalation_score")}
        for p in (timeline.get("points") or [])[-10:]
        if isinstance(p, dict)
    ]
    clean["precomputed_agent_results"] = _build_precomputed_agent_results(clean)
    return clean


def export_demo_snapshot(
    *,
    conflict: str = "Yemen",
    timeout: int = 45,
    output_path: Path | None = None,
    base_url: str = "http://127.0.0.1:8000",
) -> dict[str, Any]:
    snapshot = build_demo_snapshot(conflict=conflict, timeout=timeout, base_url=base_url)
    out_path = (output_path or OUTPUT_PATH).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"output_path": str(out_path), "agent_rows": len(snapshot.get("precomputed_agent_results", []))}
