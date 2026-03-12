"""
Configurable geographic zones – single source of truth for SIGINT filtering and sanctions geofencing.

Each zone is a named bounding box (lat_min, lat_max, lon_min, lon_max).
Zone sets group zones by purpose: "conflict" zones are used by the SIGINT agent to filter
military aircraft/ships; "sanctions" zones are used by the geofencing wrapper to generate
compliance alerts.

Zones are Iran-focused but the architecture is conflict-agnostic; add regions as needed.
"""
from typing import Dict, List, Literal, Tuple, Optional

ZoneType = Literal["sanctions", "high_risk", "embargo"]

class Zone:
    """A named geographic bounding box with metadata."""
    __slots__ = ("name", "lat_min", "lat_max", "lon_min", "lon_max", "zone_type", "source")

    def __init__(
        self,
        name: str,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        zone_type: ZoneType = "high_risk",
        source: str = "internal",
    ):
        self.name = name
        self.lat_min = lat_min
        self.lat_max = lat_max
        self.lon_min = lon_min
        self.lon_max = lon_max
        self.zone_type = zone_type
        self.source = source

    def contains(self, lat: float, lon: float) -> bool:
        return self.lat_min <= lat <= self.lat_max and self.lon_min <= lon <= self.lon_max

    def to_dict(self):
        return {
            "name": self.name,
            "lat_min": self.lat_min,
            "lat_max": self.lat_max,
            "lon_min": self.lon_min,
            "lon_max": self.lon_max,
            "zone_type": self.zone_type,
            "source": self.source,
        }


# ── Iran-focused zones (Kernfeature) ─────────────────────────────────────────

IRAN_TERRITORIAL_WATERS = Zone("IRAN_TERRITORIAL_WATERS", 24.0, 30.5, 48.0, 62.0, "sanctions", "OFAC/EU")
STRAIT_OF_HORMUZ = Zone("STRAIT_OF_HORMUZ", 25.5, 27.5, 55.0, 57.5, "sanctions", "OFAC maritime guidance 2025")

# ── Broader Middle East / conflict zones ──────────────────────────────────────

PERSIAN_GULF = Zone("PERSIAN_GULF", 22.0, 32.0, 46.0, 62.0, "high_risk", "internal")
RED_SEA = Zone("RED_SEA", 12.0, 28.0, 32.0, 44.0, "high_risk", "internal")
EASTERN_MED = Zone("EASTERN_MED", 30.0, 37.0, 25.0, 38.0, "high_risk", "internal")
GULF_OF_ADEN = Zone("GULF_OF_ADEN", 10.0, 16.0, 42.0, 52.0, "high_risk", "internal")
IRAQ_IRAN = Zone("IRAQ_IRAN", 29.0, 38.0, 40.0, 55.0, "high_risk", "internal")

# ── Other sanctions-relevant regions ──────────────────────────────────────────

BLACK_SEA = Zone("BLACK_SEA", 40.5, 47.0, 27.5, 42.0, "sanctions", "EU/OFAC")
VENEZUELA_WATERS = Zone("VENEZUELA_WATERS", 8.0, 16.0, -72.0, -58.0, "sanctions", "OFAC")
NORTH_KOREA_WATERS = Zone("NORTH_KOREA_WATERS", 35.0, 42.0, 124.0, 132.0, "sanctions", "UN/OFAC")
CRIMEA = Zone("CRIMEA", 44.0, 46.5, 32.0, 37.0, "embargo", "EU/OFAC")
LUHANSK_DONETSK = Zone("LUHANSK_DONETSK", 47.0, 50.0, 37.0, 41.0, "embargo", "EU/OFAC")

# ── Zone sets ─────────────────────────────────────────────────────────────────

CONFLICT_ZONES: List[Zone] = [
    PERSIAN_GULF, RED_SEA, EASTERN_MED, GULF_OF_ADEN, IRAQ_IRAN,
    IRAN_TERRITORIAL_WATERS, STRAIT_OF_HORMUZ,
]

SANCTIONS_ZONES: List[Zone] = [
    IRAN_TERRITORIAL_WATERS, STRAIT_OF_HORMUZ,
    BLACK_SEA, CRIMEA, LUHANSK_DONETSK,
    VENEZUELA_WATERS, NORTH_KOREA_WATERS,
]

ALL_ZONES: List[Zone] = list({z.name: z for z in CONFLICT_ZONES + SANCTIONS_ZONES}.values())


def in_zone_set(lat: float, lon: float, zones: List[Zone]) -> Optional[Zone]:
    """Return the first matching zone, or None."""
    for z in zones:
        if z.contains(lat, lon):
            return z
    return None


def all_matching_zones(lat: float, lon: float, zones: List[Zone]) -> List[Zone]:
    """Return all zones that contain the point."""
    return [z for z in zones if z.contains(lat, lon)]


def in_conflict_zone(lat: float, lon: float) -> bool:
    """Drop-in replacement for the old hardcoded _in_conflict_zone in sigint_agent."""
    return in_zone_set(lat, lon, CONFLICT_ZONES) is not None


def in_sanctions_zone(lat: float, lon: float) -> Optional[Zone]:
    """Check if point is in any sanctions zone; return the zone or None."""
    return in_zone_set(lat, lon, SANCTIONS_ZONES)
