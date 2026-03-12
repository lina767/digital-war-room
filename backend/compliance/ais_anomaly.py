"""
AIS Anomaly Detection – spoofing and dark activity heuristics.

Differentiator vs. commercial tools like Dow Jones Risk & Compliance or World-Check:
uses AIS position data not just for location but for behavioral anomalies.

Anomaly types:
- SPOOFING: vessel reports implausible position jumps (>500 nm between consecutive
  observations with short time gap), or reports position in a sanctions zone while
  other metadata suggests a different location.
- DARK_ACTIVITY: vessel known to operate in a region but missing from AIS data
  in sensitive zones (Hormuz, Persian Gulf). Cross-reference with last known position.

These are heuristic flags, not confirmed detections. They feed into the Compliance
Risk Score and generate alerts.

IMPORTANT: Intelligence signals only – not legal advice.
"""
import logging
import math
from typing import Any, Dict, List, Optional

from .zones import SANCTIONS_ZONES, Zone, all_matching_zones

logger = logging.getLogger(__name__)

# ── Thresholds (configurable) ─────────────────────────────────────────────────
MAX_SPEED_KN = 35.0
NM_PER_DEGREE_LAT = 60.0

DARK_ACTIVITY_WINDOW_SEC = 6 * 3600  # 6 hours


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in nautical miles between two points."""
    R_NM = 3440.065
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R_NM * c


class AISAnomaly:
    """A detected AIS anomaly for a vessel."""
    __slots__ = ("asset_id", "asset_name", "anomaly_type", "severity",
                 "detail", "lat", "lon", "zone_name")

    def __init__(
        self,
        asset_id: str,
        asset_name: str,
        anomaly_type: str,
        severity: str,
        detail: str,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        zone_name: str = "",
    ):
        self.asset_id = asset_id
        self.asset_name = asset_name
        self.anomaly_type = anomaly_type
        self.severity = severity
        self.detail = detail
        self.lat = lat
        self.lon = lon
        self.zone_name = zone_name

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "asset_id": self.asset_id,
            "asset_name": self.asset_name,
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "detail": self.detail,
        }
        if self.lat is not None:
            d["lat"] = self.lat
        if self.lon is not None:
            d["lon"] = self.lon
        if self.zone_name:
            d["zone_name"] = self.zone_name
        return d


def detect_spoofing(
    ships: List[Dict[str, Any]],
    previous_positions: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[AISAnomaly]:
    """
    Detect potential AIS spoofing from current ship positions.

    Heuristics:
    1. If previous_positions is provided, check for implausible jumps
       (distance / time > MAX_SPEED_KN).
    2. If a ship reports a position inside a sanctions zone but has metadata
       (flag, destination) inconsistent with that zone, flag as suspicious.
    """
    anomalies: List[AISAnomaly] = []
    prev = previous_positions or {}

    for ship in ships:
        if not isinstance(ship, dict) or "error" in ship:
            continue
        ship_id = ship.get("mmsi") or ship.get("name") or "unknown"
        ship_name = ship.get("name") or "Vessel"
        lat = ship.get("lat")
        lon = ship.get("lon")
        if lat is None or lon is None:
            continue

        if ship_id in prev:
            prev_pos = prev[ship_id]
            prev_lat = prev_pos.get("lat")
            prev_lon = prev_pos.get("lon")
            prev_ts = prev_pos.get("timestamp", 0)
            curr_ts = ship.get("timestamp", 0)

            if prev_lat is not None and prev_lon is not None:
                dist_nm = _haversine_nm(prev_lat, prev_lon, float(lat), float(lon))
                time_diff_h = max(0.01, abs(curr_ts - prev_ts) / 3600) if curr_ts and prev_ts else 1.0
                speed_kn = dist_nm / time_diff_h

                if speed_kn > MAX_SPEED_KN * 3:
                    zones = all_matching_zones(float(lat), float(lon), SANCTIONS_ZONES)
                    zone_name = zones[0].name if zones else ""
                    anomalies.append(AISAnomaly(
                        asset_id=ship_id,
                        asset_name=ship_name,
                        anomaly_type="spoofing",
                        severity="HIGH" if zone_name else "MEDIUM",
                        detail=(
                            f"Implausible position jump: {dist_nm:.0f} nm in "
                            f"{time_diff_h:.1f}h (implied {speed_kn:.0f} kn, "
                            f"max plausible ~{MAX_SPEED_KN:.0f} kn)"
                        ),
                        lat=float(lat),
                        lon=float(lon),
                        zone_name=zone_name,
                    ))

        zones = all_matching_zones(float(lat), float(lon), SANCTIONS_ZONES)
        if zones:
            flag = (ship.get("flag") or "").upper()
            dest = (ship.get("destination") or "").upper()
            iran_zones = [z for z in zones if "IRAN" in z.name or "HORMUZ" in z.name]
            if iran_zones and flag and flag not in ("IR", "OM", "AE", "QA", "BH", "KW", "SA", "IQ"):
                anomalies.append(AISAnomaly(
                    asset_id=ship_id,
                    asset_name=ship_name,
                    anomaly_type="spoofing",
                    severity="MEDIUM",
                    detail=(
                        f"Non-regional flag ({flag}) vessel in {iran_zones[0].name}. "
                        f"Destination: {dest or 'unknown'}. Review for potential evasion."
                    ),
                    lat=float(lat),
                    lon=float(lon),
                    zone_name=iran_zones[0].name,
                ))

    return anomalies


def detect_dark_activity(
    current_ships: List[Dict[str, Any]],
    previous_ships: Optional[List[Dict[str, Any]]] = None,
    zones: Optional[List[Zone]] = None,
) -> List[AISAnomaly]:
    """
    Detect vessels that were previously seen in/near sensitive zones but are now
    absent from AIS (potential AIS switch-off / "going dark").

    Args:
        current_ships: Ships from current SIGINT scan
        previous_ships: Ships from previous scan (if available)
        zones: Zones to consider for dark activity; defaults to SANCTIONS_ZONES
    """
    if not previous_ships:
        return []

    zone_list = zones or SANCTIONS_ZONES
    anomalies: List[AISAnomaly] = []

    current_ids = set()
    for s in current_ships:
        if isinstance(s, dict):
            sid = s.get("mmsi") or s.get("name") or ""
            if sid:
                current_ids.add(str(sid).lower())

    for prev_ship in previous_ships:
        if not isinstance(prev_ship, dict):
            continue
        ship_id = prev_ship.get("mmsi") or prev_ship.get("name") or ""
        if not ship_id or str(ship_id).lower() in current_ids:
            continue

        prev_lat = prev_ship.get("lat")
        prev_lon = prev_ship.get("lon")
        if prev_lat is None or prev_lon is None:
            continue

        matched = all_matching_zones(float(prev_lat), float(prev_lon), zone_list)
        if matched:
            anomalies.append(AISAnomaly(
                asset_id=str(ship_id),
                asset_name=prev_ship.get("name") or "Vessel",
                anomaly_type="dark_activity",
                severity="HIGH" if any("HORMUZ" in z.name or "IRAN" in z.name for z in matched) else "MEDIUM",
                detail=(
                    f"Previously seen in {matched[0].name} "
                    f"(lat {float(prev_lat):.1f}, lon {float(prev_lon):.1f}), "
                    f"now absent from AIS. Potential AIS switch-off in sensitive zone."
                ),
                lat=float(prev_lat),
                lon=float(prev_lon),
                zone_name=matched[0].name,
            ))

    return anomalies


def analyze_ais_anomalies(
    sigint_result: Dict[str, Any],
    previous_sigint: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Run all AIS anomaly heuristics on SIGINT output.

    Args:
        sigint_result: Current SIGINT agent output with 'ships' list
        previous_sigint: Optional previous SIGINT output for temporal comparison

    Returns:
        List of AISAnomaly dicts
    """
    ships = sigint_result.get("ships") or []
    prev_ships = (previous_sigint or {}).get("ships") or []

    prev_positions: Dict[str, Dict[str, Any]] = {}
    for s in prev_ships:
        if isinstance(s, dict):
            sid = s.get("mmsi") or s.get("name") or ""
            if sid:
                prev_positions[sid] = s

    spoofing = detect_spoofing(ships, prev_positions if prev_positions else None)
    dark = detect_dark_activity(ships, prev_ships if prev_ships else None)

    all_anomalies = spoofing + dark
    return [a.to_dict() for a in all_anomalies]
