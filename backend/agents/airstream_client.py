"""
AISStream (aisstream.io) WebSocket client for real-time AIS vessel data.

Used by the Chokepoint agent to stream ship positions within bounding boxes
(Hormuz, Bab el-Mandeb, Suez). See https://aisstream.io/documentation

Subscription must be sent within ~3s of connecting (server closes otherwise).
Optional filters per official API: FilterMessageTypes, FiltersShipMMSI.

No dependency on chokepoint_agent to avoid circular imports; the agent passes
bounding_boxes, cp_bounds, and tanker_keywords.
"""

from __future__ import annotations

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

# ITU-R M.1371: ship types 80–89 are tanker / tanker hazardous
def _ais_type_is_tanker(ship_type: Any) -> bool:
    if ship_type is None:
        return False
    try:
        t = int(ship_type)
    except (TypeError, ValueError):
        return False
    return 80 <= t <= 89


def _resolve_api_key(explicit: Optional[str]) -> str:
    """Official env name first (aisstream.io), then legacy aliases."""
    return (
        (explicit or "").strip()
        or (os.getenv("AISSTREAM_API_KEY") or "").strip()
        or (os.getenv("AIRSTREAM_API_KEY") or "").strip()
        or (os.getenv("AIRSTREAM_API") or "").strip()
    )


def _parse_mmsi(mmsi_raw: Any, lat: float, lon: float, name: str) -> int:
    try:
        return int(mmsi_raw) if mmsi_raw is not None else hash((lat, lon, name)) % (2**31)
    except (TypeError, ValueError):
        return hash((lat, lon, name)) % (2**31)


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


def _meta_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    m = data.get("MetaData") or data.get("Metadata") or {}
    return m if isinstance(m, dict) else {}


def _apply_ship_static(data: Dict[str, Any], static_by_mmsi: Dict[int, int]) -> None:
    """Extract MMSI and AIS Type from ShipStaticData (Type not in PositionReport MetaData)."""
    body = (data.get("Message") or {}).get("ShipStaticData") or {}
    if not isinstance(body, dict):
        return
    meta = _meta_dict(data)
    mmsi_raw = meta.get("MMSI") or body.get("UserID")
    ship_type = body.get("Type")
    try:
        mmsi = int(mmsi_raw) if mmsi_raw is not None else None
    except (TypeError, ValueError):
        mmsi = None
    if mmsi is not None and ship_type is not None:
        static_by_mmsi[mmsi] = int(ship_type)


def _ingest_position_report(
    data: Dict[str, Any],
    raw_by_cp: Dict[str, Dict[int, Dict[str, Any]]],
    cp_bounds: Dict[str, Tuple[float, float, float, float]],
) -> None:
    meta = _meta_dict(data)
    msg_body = (data.get("Message") or {}).get("PositionReport") or {}
    if not isinstance(msg_body, dict):
        return
    lat = _safe_float(meta.get("latitude") or meta.get("Latitude") or msg_body.get("Latitude"))
    lon = _safe_float(meta.get("longitude") or meta.get("Longitude") or msg_body.get("Longitude"))
    if lat is None or lon is None:
        return
    name = (meta.get("ShipName") or meta.get("shipname") or "").strip() or "Unknown"
    mmsi = _parse_mmsi(meta.get("MMSI") or msg_body.get("UserID"), lat, lon, name)
    for cp_name, bounds in cp_bounds.items():
        if _point_in_bounds(lat, lon, bounds):
            raw_by_cp[cp_name][mmsi] = {"name": name, "lat": lat, "lon": lon, "mmsi": mmsi}
            break


def _ingest_extended_class_b(
    data: Dict[str, Any],
    raw_by_cp: Dict[str, Dict[int, Dict[str, Any]]],
    static_by_mmsi: Dict[int, int],
    cp_bounds: Dict[str, Tuple[float, float, float, float]],
) -> None:
    """Class B extended report carries Type + Name on the message (useful when no static yet)."""
    body = (data.get("Message") or {}).get("ExtendedClassBPositionReport") or {}
    if not isinstance(body, dict):
        return
    lat = _safe_float(body.get("Latitude"))
    lon = _safe_float(body.get("Longitude"))
    if lat is None or lon is None:
        return
    name = (body.get("Name") or "").strip() or "Unknown"
    mmsi = _parse_mmsi(body.get("UserID"), lat, lon, name)
    st = body.get("Type")
    if st is not None:
        try:
            static_by_mmsi[mmsi] = int(st)
        except (TypeError, ValueError):
            pass
    for cp_name, bounds in cp_bounds.items():
        if _point_in_bounds(lat, lon, bounds):
            raw_by_cp[cp_name][mmsi] = {"name": name, "lat": lat, "lon": lon, "mmsi": mmsi}
            break


def _finalize_tankers(
    raw_by_cp: Dict[str, Dict[int, Dict[str, Any]]],
    static_by_mmsi: Dict[int, int],
    tanker_keywords: List[str],
) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    kw = [k.lower() for k in tanker_keywords]
    for cp_name, mmsi_map in raw_by_cp.items():
        vessels: List[Dict[str, Any]] = []
        for _mmsi, v in mmsi_map.items():
            mmsi = int(v.get("mmsi") or _mmsi)
            name = str(v.get("name") or "Unknown")
            st = static_by_mmsi.get(mmsi)
            by_type = _ais_type_is_tanker(st)
            by_name = any(k in name.lower() for k in kw)
            if not (by_type or by_name):
                continue
            type_label = "tanker" if by_type or by_name else "unknown"
            vessels.append(
                {
                    "name": name,
                    "type": type_label,
                    "lat": v["lat"],
                    "lon": v["lon"],
                    "source": "airstream",
                    **({"ais_ship_type": st} if st is not None else {}),
                }
            )
        out[cp_name] = vessels
    return out


def _default_message_types() -> List[str]:
    raw = (os.getenv("AISSTREAM_FILTER_MESSAGE_TYPES") or "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return ["PositionReport", "ShipStaticData", "ExtendedClassBPositionReport"]


async def collect_tankers_by_chokepoint(
    bounding_boxes: List[List[List[float]]],
    cp_bounds: Dict[str, Tuple[float, float, float, float]],
    tanker_keywords: List[str],
    api_key: Optional[str] = None,
    collect_seconds: float = DEFAULT_COLLECT_SECONDS,
) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """
    Connect to AISStream WebSocket, subscribe to the given bounding boxes,
    collect AIS messages for collect_seconds, then map vessels to chokepoints
    and classify tankers via AIS ship type (80–89) and/or name keywords.

    Uses the same subscription shape as the official Python example:
    APIKey, BoundingBoxes, FilterMessageTypes (optional), FiltersShipMMSI (optional).

    Args:
        bounding_boxes: List of boxes in AISStream format [[lat, lon], [lat, lon]].
        cp_bounds: Dict cp_name -> (lat_min, lat_max, lon_min, lon_max).
        tanker_keywords: Keywords to match in vessel name when AIS type unknown.
        api_key: If None, reads AISSTREAM_API_KEY, then AIRSTREAM_API_KEY, then AIRSTREAM_API.
        collect_seconds: How long to collect messages (env AISSTREAM_COLLECT_SECONDS / AIRSTREAM_COLLECT_SECONDS).

    Returns:
        Dict[cp_name, List[{name, type, lat, lon, source: "airstream"}]] or None on error / no key.
    """
    key = _resolve_api_key(api_key)
    if not key:
        return None

    try:
        collect_seconds = float(
            os.getenv("AISSTREAM_COLLECT_SECONDS") or os.getenv("AIRSTREAM_COLLECT_SECONDS") or str(collect_seconds)
        )
    except (TypeError, ValueError):
        collect_seconds = DEFAULT_COLLECT_SECONDS

    raw_by_cp: Dict[str, Dict[int, Dict[str, Any]]] = {cp_name: {} for cp_name in cp_bounds}
    static_by_mmsi: Dict[int, int] = {}

    mmsi_filter_raw = (os.getenv("AISSTREAM_FILTERS_SHIP_MMSI") or os.getenv("AIRSTREAM_FILTERS_SHIP_MMSI") or "").strip()
    filters_ship_mmsi: Optional[List[str]] = None
    if mmsi_filter_raw:
        filters_ship_mmsi = [x.strip() for x in mmsi_filter_raw.split(",") if x.strip()]

    async def collect() -> Optional[Dict[str, List[Dict[str, Any]]]]:
        async with websockets.connect(
            AISTREAM_WS_URL,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            # Server closes if no subscription within ~3s (see aisstream.io/documentation).
            subscription: Dict[str, Any] = {
                "APIKey": key,
                "BoundingBoxes": bounding_boxes,
                "FilterMessageTypes": _default_message_types(),
            }
            if filters_ship_mmsi:
                subscription["FiltersShipMMSI"] = filters_ship_mmsi
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
                if not isinstance(data, dict):
                    continue
                if data.get("error"):
                    err = str(data.get("error", ""))
                    log_fn = logger.error if "valid" in err.lower() or "api" in err.lower() else logger.warning
                    log_fn("airstream: server error — %s (check AISSTREAM_API_KEY)", err)
                    return None
                mt = data.get("MessageType")
                if mt == "ShipStaticData":
                    _apply_ship_static(data, static_by_mmsi)
                elif mt == "PositionReport":
                    _ingest_position_report(data, raw_by_cp, cp_bounds)
                elif mt == "ExtendedClassBPositionReport":
                    _ingest_extended_class_b(data, raw_by_cp, static_by_mmsi, cp_bounds)

            return _finalize_tankers(raw_by_cp, static_by_mmsi, tanker_keywords)

    try:
        return await asyncio.wait_for(collect(), timeout=collect_seconds + 10.0)
    except asyncio.TimeoutError:
        logger.debug("airstream: collect timeout")
        return None
    except Exception as e:
        logger.debug("airstream: collect failed: %s", e)
        return None
