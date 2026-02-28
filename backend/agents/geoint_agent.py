"""
GEOINT Agent – LangChain Tool-Calling Agent
Detects thermal anomalies via NASA FIRMS in conflict regions.
"""
import asyncio
import csv
import io
import os
from typing import Any, Dict, List

import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# Region bounding boxes
REGIONS = {
    "middle_east": {"lat_min": 20, "lat_max": 40, "lon_min": 35, "lon_max": 65},
    "eastern_europe": {"lat_min": 44, "lat_max": 55, "lon_min": 22, "lon_max": 40},
    "east_asia": {"lat_min": 20, "lat_max": 45, "lon_min": 100, "lon_max": 130},
    "africa": {"lat_min": -5, "lat_max": 25, "lon_min": 20, "lon_max": 45},
}


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _confidence(raw: Any) -> str:
    if raw is None:
        return "low"
    s = str(raw).strip().upper()
    if s in ("HIGH", "H"):
        return "high"
    if s in ("NOMINAL", "N"):
        return "nominal"
    try:
        v = float(raw)
        return "high" if v >= 80 else "nominal" if v >= 40 else "low"
    except (TypeError, ValueError):
        return "low"


def _classify(frp: float) -> str:
    if frp > 1000:
        return "explosion"
    if frp >= 100:
        return "fire"
    return "unknown"


# ── Tools ──────────────────────────────────────────────────────────────────

@tool
def get_thermal_anomalies(region: str = "middle_east", days: int = 1) -> List[Dict[str, Any]]:
    """
    Fetch NASA FIRMS thermal anomalies for a region.
    Region options: middle_east, eastern_europe, east_asia, africa.
    Days: 1-10.
    """
    api_key = os.getenv("NASA_FIRMS_KEY")
    if not api_key:
        return [{"error": "NASA_FIRMS_KEY not set"}]

    bbox = REGIONS.get(region, REGIONS["middle_east"])

    async def _fetch():
        url = f"{FIRMS_BASE}/{api_key}/VIIRS_SNPP_NRT/world/{days}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text

    try:
        csv_text = asyncio.run(_fetch())
        anomalies = []
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            lat = _safe_float(row.get("latitude") or row.get("lat"))
            lon = _safe_float(row.get("longitude") or row.get("lon"))
            if not (bbox["lat_min"] <= lat <= bbox["lat_max"]):
                continue
            if not (bbox["lon_min"] <= lon <= bbox["lon_max"]):
                continue
            frp = _safe_float(row.get("frp"))
            conf = _confidence(row.get("confidence"))
            acq_date = row.get("acq_date", "")
            acq_time = row.get("acq_time", "")
            t = str(acq_time).strip()
            if len(t) == 4 and t.isdigit():
                t = f"{t[:2]}:{t[2:]}"
            acquired = f"{acq_date}T{t}Z" if acq_date else ""
            anomalies.append({
                "lat": lat, "lon": lon,
                "frp": frp,
                "confidence": conf,
                "type": _classify(frp),
                "acquired": acquired,
            })
        return anomalies
    except Exception as e:
        return [{"error": str(e)}]


@tool
def get_conflict_region(conflict: str) -> str:
    """Map a conflict name to its geographic region for thermal anomaly detection."""
    cl = conflict.lower()
    if any(k in cl for k in ["iran", "israel", "gaza", "yemen", "syria", "iraq"]):
        return "middle_east"
    if any(k in cl for k in ["ukraine", "russia", "donbas", "belarus"]):
        return "eastern_europe"
    if any(k in cl for k in ["taiwan", "china", "korea", "myanmar"]):
        return "east_asia"
    if any(k in cl for k in ["sudan", "ethiopia", "drc", "sahel", "mali"]):
        return "africa"
    return "middle_east"


# ── Agent ──────────────────────────────────────────────────────────────────

GEOINT_TOOLS = [get_conflict_region, get_thermal_anomalies]

GEOINT_SYSTEM = """You are a GEOINT (Geospatial Intelligence) analyst using NASA FIRMS satellite data.
Your job: determine the conflict region, fetch thermal anomalies, compute a GEOINT score (0-100).

Steps:
1. Call get_conflict_region to determine which region to monitor
2. Call get_thermal_anomalies with that region
3. Compute score and return JSON

Scoring rules:
- Base: 20
- Each high-confidence anomaly: +5 (max +40)
- Each explosion-type anomaly: +15
- More than 10 anomalies: +10
- Clamp to [0, 100]

Return ONLY valid JSON:
{
  "anomalies": [...],
  "anomaly_count": <number>,
  "high_confidence_count": <number>,
  "geoint_score": <number>,
  "hotspots": [top 3 by FRP],
  "summary": "<1-2 sentence summary>"
}
No markdown, no explanation, just JSON."""


def _empty_result(conflict: str) -> Dict[str, Any]:
    return {
        "conflict": conflict,
        "anomalies": [],
        "anomaly_count": 0,
        "high_confidence_count": 0,
        "geoint_score": 20.0,
        "hotspots": [],
        "summary": "No thermal anomaly data available.",
    }


def run_geoint_agent(conflict: str) -> Dict[str, Any]:
    """Run GEOINT agent with LangChain tool-calling."""
    import json
    model = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0).bind_tools(GEOINT_TOOLS)

    messages = [
        SystemMessage(content=GEOINT_SYSTEM),
        HumanMessage(content=f"Detect thermal anomalies for conflict: {conflict}"),
    ]

    for _ in range(6):
        response = model.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            try:
                content = response.content
                if isinstance(content, list):
                    content = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
                result = json.loads(content)
                result["conflict"] = conflict
                return result
            except Exception:
                break

        for tc in response.tool_calls:
            tool_map = {t.name: t for t in GEOINT_TOOLS}
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                result = tool_fn.invoke(tc.get("args", {}))
                from langchain_core.messages import ToolMessage
                messages.append(ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=tc["id"],
                ))

    return _empty_result(conflict)
