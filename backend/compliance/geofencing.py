"""
Geofencing wrapper – checks SIGINT outputs (ships, aircraft positions) against
configured sanctions zones and generates alerts.

This is a thin layer on top of the existing SIGINT agent outputs; it does NOT
implement its own tracking pipeline.

IMPORTANT: Geofencing alerts are intelligence signals, not legal advice.
They support due diligence but do not replace legal review.
"""
import time
from typing import Any, Dict, List, Optional

from .zones import SANCTIONS_ZONES, Zone, all_matching_zones


class GeofencingAlert:
    """An alert generated when a tracked asset enters a sanctions zone."""
    __slots__ = ("asset_type", "asset_id", "asset_name", "lat", "lon",
                 "zone", "timestamp", "source")

    def __init__(
        self,
        asset_type: str,
        asset_id: str,
        asset_name: str,
        lat: float,
        lon: float,
        zone: Zone,
        timestamp: Optional[float] = None,
        source: str = "",
    ):
        self.asset_type = asset_type
        self.asset_id = asset_id
        self.asset_name = asset_name
        self.lat = lat
        self.lon = lon
        self.zone = zone
        self.timestamp = timestamp or time.time()
        self.source = source

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_type": self.asset_type,
            "asset_id": self.asset_id,
            "asset_name": self.asset_name,
            "lat": self.lat,
            "lon": self.lon,
            "zone_name": self.zone.name,
            "zone_type": self.zone.zone_type,
            "zone_source": self.zone.source,
            "timestamp": self.timestamp,
            "source": self.source,
        }


def check_sigint_for_sanctions(
    sigint_result: Dict[str, Any],
    zones: Optional[List[Zone]] = None,
) -> List[Dict[str, Any]]:
    """
    Check SIGINT agent output (aircraft, ships) against sanctions zones.

    Args:
        sigint_result: The dict returned by run_sigint_agent, containing
                       'aircraft' and 'ships' lists.
        zones: Optional zone list; defaults to SANCTIONS_ZONES.

    Returns:
        List of GeofencingAlert dicts for assets inside sanctions zones.
    """
    zone_list = zones or SANCTIONS_ZONES
    alerts: List[GeofencingAlert] = []

    for ac in sigint_result.get("aircraft") or []:
        if not isinstance(ac, dict) or "error" in ac:
            continue
        try:
            lat = float(ac.get("lat"))  # type: ignore[arg-type]
            lon = float(ac.get("lon"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        matched = all_matching_zones(lat, lon, zone_list)
        for zone in matched:
            alerts.append(GeofencingAlert(
                asset_type="aircraft",
                asset_id=ac.get("flight") or ac.get("hex") or "unknown",
                asset_name=ac.get("flight") or ac.get("type") or "Aircraft",
                lat=lat,
                lon=lon,
                zone=zone,
                source=ac.get("source") or "ADSB",
            ))

    for ship in sigint_result.get("ships") or []:
        if not isinstance(ship, dict) or "error" in ship:
            continue
        try:
            lat = float(ship.get("lat"))  # type: ignore[arg-type]
            lon = float(ship.get("lon"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        matched = all_matching_zones(lat, lon, zone_list)
        for zone in matched:
            alerts.append(GeofencingAlert(
                asset_type="ship",
                asset_id=ship.get("mmsi") or ship.get("name") or "unknown",
                asset_name=ship.get("name") or "Vessel",
                lat=lat,
                lon=lon,
                zone=zone,
                source=ship.get("source") or "AIS",
            ))

    return [a.to_dict() for a in alerts]
