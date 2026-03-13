"""
Supply-Chain Monitoring – route screening against sanctions zones and configurable
intermediary (middlemen) policy.

Trade routes are sequences of waypoints (port/airport/coordinate). Each waypoint is
checked against sanctions zones; additionally, transit hubs are evaluated against a
configurable policy that flags potential evasion patterns.

Middlemen heuristics are NOT hardcoded country lists. They are loaded from a documented
policy configuration so that changes are auditable and politically defensible.

IMPORTANT: Intelligence signals only – not legal advice.
"""
import logging
from typing import Any, Dict, List, Literal, Optional

from .zones import SANCTIONS_ZONES, Zone, all_matching_zones

logger = logging.getLogger(__name__)

# ── Configurable intermediary policy ──────────────────────────────────────────
# Each entry: { hub, condition, rationale, source }
# This is the ONLY place where transit-hub heuristics are defined.
# In production, load from YAML/JSON; here we use a Python structure that
# mirrors the documented policy for transparency.

INTERMEDIARY_POLICY: List[Dict[str, str]] = [
    {
        "hub": "AE",
        "hub_label": "UAE (Dubai, Fujairah)",
        "condition": "Transit between sanctioned origin/destination and UAE free-trade zones",
        "rationale": "OFAC and EU have flagged UAE-based intermediaries in Iranian oil sanctions evasion schemes (ship-to-ship transfers near Fujairah).",
        "source": "OFAC maritime advisory April 2025; EU Council Regulation 267/2012",
    },
    {
        "hub": "TR",
        "hub_label": "Turkey",
        "condition": "Re-export via Turkish ports for goods with dual-use potential",
        "rationale": "Turkey-based re-export channels have been cited in OFAC enforcement actions related to Iran and Russia sanctions evasion.",
        "source": "OFAC enforcement releases 2024–2025",
    },
    {
        "hub": "BY",
        "hub_label": "Belarus",
        "condition": "Transit through Belarus for Russia-destined goods under EU/OFAC sanctions",
        "rationale": "Belarus serves as a documented re-routing hub for sanctioned goods destined for Russia.",
        "source": "EU sanctions guidance; OFAC Russia-related designations",
    },
    {
        "hub": "OM",
        "hub_label": "Oman",
        "condition": "Maritime transit through Omani ports adjacent to Strait of Hormuz",
        "rationale": "Proximity to Hormuz and documented use in ship-to-ship transfer operations.",
        "source": "OFAC maritime advisory April 2025",
    },
    {
        "hub": "MY",
        "hub_label": "Malaysia",
        "condition": "Ship-to-ship transfer operations near Malaysian waters for Iranian crude",
        "rationale": "Malaysian waters have been identified as a location for STS transfers involving sanctioned Iranian oil.",
        "source": "OFAC enforcement; UN Panel of Experts reports",
    },
]


class Waypoint:
    """A point on a trade route (port, airport, or coordinate)."""
    __slots__ = ("label", "country_code", "lat", "lon", "port_type")

    def __init__(
        self,
        label: str,
        lat: float,
        lon: float,
        country_code: str = "",
        port_type: str = "port",
    ):
        self.label = label
        self.lat = lat
        self.lon = lon
        self.country_code = country_code.upper()
        self.port_type = port_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "country_code": self.country_code,
            "lat": self.lat,
            "lon": self.lon,
            "port_type": self.port_type,
        }


class RouteScreeningResult:
    """Result of screening a single trade route."""
    def __init__(
        self,
        route_label: str,
        waypoints: List[Waypoint],
        zone_hits: List[Dict[str, Any]],
        suspicious_hops: List[Dict[str, Any]],
        touches_sanctions_zone: bool,
    ):
        self.route_label = route_label
        self.waypoints = waypoints
        self.zone_hits = zone_hits
        self.suspicious_hops = suspicious_hops
        self.touches_sanctions_zone = touches_sanctions_zone

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route_label": self.route_label,
            "waypoints": [w.to_dict() for w in self.waypoints],
            "zone_hits": self.zone_hits,
            "suspicious_hops": self.suspicious_hops,
            "touches_sanctions_zone": self.touches_sanctions_zone,
        }


def screen_route(
    route_label: str,
    waypoints: List[Dict[str, Any]],
    zones: Optional[List[Zone]] = None,
    policy: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Screen a trade route against sanctions zones and intermediary policy.

    Args:
        route_label: Human-readable route name (e.g. "Bandar Abbas → Fujairah → Rotterdam")
        waypoints: List of dicts with keys: label, lat, lon, country_code (ISO 2), port_type
        zones: Zone list to check against; defaults to SANCTIONS_ZONES
        policy: Intermediary policy; defaults to INTERMEDIARY_POLICY

    Returns:
        RouteScreeningResult as dict with zone_hits, suspicious_hops, touches_sanctions_zone
    """
    zone_list = zones or SANCTIONS_ZONES
    intermediary_rules = policy or INTERMEDIARY_POLICY

    parsed_waypoints: List[Waypoint] = []
    zone_hits: List[Dict[str, Any]] = []
    suspicious_hops: List[Dict[str, Any]] = []
    touches = False

    for wp_data in waypoints:
        try:
            wp_lat = float(wp_data.get("lat"))  # type: ignore[arg-type]
            wp_lon = float(wp_data.get("lon"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            logger.warning("Skipping waypoint %r: invalid lat/lon", wp_data.get("label"))
            continue
        if not (-90 <= wp_lat <= 90 and -180 <= wp_lon <= 180):
            logger.warning("Skipping waypoint %r: lat/lon out of range", wp_data.get("label"))
            continue
        wp = Waypoint(
            label=wp_data.get("label", ""),
            lat=wp_lat,
            lon=wp_lon,
            country_code=wp_data.get("country_code", ""),
            port_type=wp_data.get("port_type", "port"),
        )
        parsed_waypoints.append(wp)

        matched_zones = all_matching_zones(wp.lat, wp.lon, zone_list)
        for z in matched_zones:
            touches = True
            zone_hits.append({
                "waypoint": wp.label,
                "zone_name": z.name,
                "zone_type": z.zone_type,
                "zone_source": z.source,
            })

        for rule in intermediary_rules:
            if wp.country_code == rule["hub"]:
                suspicious_hops.append({
                    "waypoint": wp.label,
                    "country_code": wp.country_code,
                    "hub_label": rule["hub_label"],
                    "condition": rule["condition"],
                    "rationale": rule["rationale"],
                    "policy_source": rule["source"],
                })

    result = RouteScreeningResult(
        route_label=route_label,
        waypoints=parsed_waypoints,
        zone_hits=zone_hits,
        suspicious_hops=suspicious_hops,
        touches_sanctions_zone=touches,
    )
    return result.to_dict()


def get_intermediary_policy() -> List[Dict[str, str]]:
    """Return the active intermediary policy for transparency/audit."""
    return INTERMEDIARY_POLICY
