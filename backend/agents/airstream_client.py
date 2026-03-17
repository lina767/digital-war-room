"""
AISStream (aisstream.io) WebSocket client for real-time AIS vessel data.

Used by the Chokepoint agent to stream ship positions within bounding boxes
(Hormuz, Bab el-Mandeb, Suez). No dependency on chokepoint_agent to avoid
circular imports; the agent passes bounding_boxes, cp_bounds, and tanker_keywords.
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import websockets

logger = logging.getLogger(__name__)

AISTREAM_WS_URL = "wss://stream.aisstream.io/v0/stream"
DEFAULT_COLLECT_SECONDS = 15.0


def _safe_float(v: Any) -> Optional[float]:
    """Return float or None for AIS message fields."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _point_in_bounds(lat: float, lon: float, bounds: Tuple[float, float, float, float]) -> bool:
    """Check if (lat, lon) is inside bounds (lat_min, lat_max, lon_min, lon_max)."""
    lat_min, lat_max, lon_min, lon_max = bounds
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


async def collect_tankers_by_chokepoint(
    bounding_boxes: List[List[List[float]]],
    cp_bounds: Dict[str, Tuple[float, float, float, float]],
    tanker_keywords: List[str],
    api_key: Optional[str] = None,
    collect_seconds: float = DEFAULT_COLLECT_SECONDS,
) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """
    Connect to AISStream WebSocket, subscribe to the given bounding boxes,
    collect PositionReport messages for collect_seconds, then map vessels
    to chokepoints and filter by tanker keywords. Deduplicates by MMSI per cp.

    Args:
        bounding_boxes: List of boxes in AISStream format [[lat, lon], [lat, lon]].
        cp_bounds: Dict cp_name -> (lat_min, lat_max, lon_min, lon_max).
        tanker_keywords: Keywords to match in vessel name (e.g. tanker, vlcc).
        api_key: AISStream API key; if None, reads AISSTREAM_API_KEY or AIRSTREAM_API_KEY or AIRSTREAM_API from env.
        collect_seconds: How long to collect messages.

    Returns:
        Dict[cp_name, List[{name, type, lat, lon, source: "airstream"}]] or None on error.
    """
    key = (
        api_key or os.getenv("AISSTREAM_API_KEY") or os.getenv("AIRSTREAM_API_KEY") or os.getenv("AIRSTREAM_API") or ""
    ).strip()
    if not key:
        return None

    try:
        collect_seconds = float(
            os.getenv("AISSTREAM_COLLECT_SECONDS") or os.getenv("AIRSTREAM_COLLECT_SECONDS") or str(collect_seconds)
        )
    except (TypeError, ValueError):
        collect_seconds = DEFAULT_COLLECT_SECONDS

    # Per chokepoint: MMSI -> latest vessel dict (dedup)
    by_cp: Dict[str, Dict[int, Dict[str, Any]]] = {cp_name: {} for cp_name in cp_bounds}

    async def collect() -> Optional[Dict[str, List[Dict[str, Any]]]]:
        async with websockets.connect(
            AISTREAM_WS_URL,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            subscription = {
                "APIKey": key,
                "BoundingBoxes": bounding_boxes,
                "FilterMessageTypes": ["PositionReport"],
            }
            await ws.send(json.dumps(subscription))

            deadline = time.monotonic() + collect_seconds
            while time.monotonic() < deadline:
                remaining = max(1.0, deadline - time.monotonic())
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict) and data.get("error"):
                    logger.warning("airstream: server error %s", data.get("error"))
                    return None  # do not treat as "0 tankers"
                if data.get("MessageType") != "PositionReport":
                    continue
                meta = data.get("MetaData") or data.get("Metadata") or {}
                msg_body = (data.get("Message") or {}).get("PositionReport") or {}
                lat = _safe_float(meta.get("latitude") or meta.get("Latitude") or msg_body.get("Latitude"))
                lon = _safe_float(meta.get("longitude") or meta.get("Longitude") or msg_body.get("Longitude"))
                if lat is None or lon is None:
                    continue
                name = (meta.get("ShipName") or meta.get("shipname") or "").strip() or "Unknown"
                mmsi_raw = meta.get("MMSI") or msg_body.get("UserID")
                try:
                    mmsi = int(mmsi_raw) if mmsi_raw is not None else hash((lat, lon, name)) % (2**31)
                except (TypeError, ValueError):
                    mmsi = hash((lat, lon, name)) % (2**31)

                is_tanker = any(kw in (name or "").lower() for kw in tanker_keywords)
                if not is_tanker:
                    continue

                vessel = {
                    "name": name,
                    "type": "tanker",
                    "lat": lat,
                    "lon": lon,
                    "source": "airstream",
                }
                for cp_name, bounds in cp_bounds.items():
                    if _point_in_bounds(lat, lon, bounds):
                        by_cp[cp_name][mmsi] = vessel
                        break

        out: Dict[str, List[Dict[str, Any]]] = {}
        for cp_name, mmsi_to_vessel in by_cp.items():
            out[cp_name] = list(mmsi_to_vessel.values())
        return out

    try:
        result = await asyncio.wait_for(collect(), timeout=collect_seconds + 10.0)
        return result
    except asyncio.TimeoutError:
        logger.debug("airstream: collect timeout")
        return None
    except Exception as e:
        logger.debug("airstream: collect failed: %s", e)
        return None
