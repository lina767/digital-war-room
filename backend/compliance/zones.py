"""
Configurable geographic zones – single source of truth for SIGINT filtering and sanctions geofencing.

Supports two geometry types:
- Bounding box: Zone(name, lat_min, lat_max, lon_min, lon_max, ...)
- Polygon: PolygonZone(name, vertices=[(lat, lon), ...], ...)

Zone sets group zones by purpose: "conflict" zones are used by the SIGINT agent to filter
military aircraft/ships; "sanctions" zones are used by the geofencing wrapper to generate
compliance alerts.

Zones are Iran-focused but the architecture is conflict-agnostic; add regions as needed.
"""
from typing import Dict, List, Literal, Sequence, Tuple, Optional

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
            "geometry": "bbox",
            "lat_min": self.lat_min,
            "lat_max": self.lat_max,
            "lon_min": self.lon_min,
            "lon_max": self.lon_max,
            "zone_type": self.zone_type,
            "source": self.source,
        }


class PolygonZone:
    """A named geographic polygon zone (list of (lat, lon) vertices)."""
    __slots__ = ("name", "vertices", "zone_type", "source",
                 "_lat_min", "_lat_max", "_lon_min", "_lon_max")

    def __init__(
        self,
        name: str,
        vertices: Sequence[Tuple[float, float]],
        zone_type: ZoneType = "high_risk",
        source: str = "internal",
    ):
        self.name = name
        self.vertices = list(vertices)
        self.zone_type = zone_type
        self.source = source
        lats = [v[0] for v in self.vertices]
        lons = [v[1] for v in self.vertices]
        self._lat_min = min(lats)
        self._lat_max = max(lats)
        self._lon_min = min(lons)
        self._lon_max = max(lons)

    def contains(self, lat: float, lon: float) -> bool:
        if not (self._lat_min <= lat <= self._lat_max and self._lon_min <= lon <= self._lon_max):
            return False
        return _point_in_polygon(lat, lon, self.vertices)

    def to_dict(self):
        return {
            "name": self.name,
            "geometry": "polygon",
            "vertices": self.vertices,
            "zone_type": self.zone_type,
            "source": self.source,
        }


def _point_in_polygon(lat: float, lon: float, vertices: List[Tuple[float, float]]) -> bool:
    """Ray-casting algorithm for point-in-polygon test. Vertices are (lat, lon) pairs."""
    n = len(vertices)
    inside = False
    j = n - 1
    for i in range(n):
        vlat_i, vlon_i = vertices[i]
        vlat_j, vlon_j = vertices[j]
        if ((vlon_i > lon) != (vlon_j > lon)) and (
            lat < (vlat_j - vlat_i) * (lon - vlon_i) / (vlon_j - vlon_i) + vlat_i
        ):
            inside = not inside
        j = i
    return inside


AnyZone = Zone | PolygonZone


# ── Iran-focused zones (Kernfeature) ─────────────────────────────────────────

IRAN_TERRITORIAL_WATERS = Zone("IRAN_TERRITORIAL_WATERS", 24.0, 30.5, 48.0, 62.0, "sanctions", "OFAC/EU")

# Strait of Hormuz: polygon for more precise geometry (narrowest point ~33 km)
STRAIT_OF_HORMUZ = PolygonZone(
    "STRAIT_OF_HORMUZ",
    vertices=[
        (26.0, 55.5), (27.2, 55.0), (27.0, 56.5),
        (26.5, 57.5), (25.8, 57.0), (25.5, 56.0),
    ],
    zone_type="sanctions",
    source="OFAC maritime guidance 2025",
)

# Fujairah anchorage: known STS transfer area
FUJAIRAH_ANCHORAGE = PolygonZone(
    "FUJAIRAH_ANCHORAGE",
    vertices=[
        (25.0, 56.2), (25.4, 56.2), (25.4, 56.6), (25.0, 56.6),
    ],
    zone_type="high_risk",
    source="OFAC maritime advisory 2025 (STS transfer zone)",
)

# Bab el-Mandeb strait: connects Red Sea to Gulf of Aden (~6 mbd oil transit)
BAB_EL_MANDEB = PolygonZone(
    "BAB_EL_MANDEB",
    vertices=[
        (12.4, 43.0), (12.8, 43.0), (12.8, 43.6),
        (12.4, 43.6),
    ],
    zone_type="high_risk",
    source="internal (chokepoint monitoring)",
)

# Suez Canal: ~5 mbd oil transit, ~12% global trade
SUEZ_CANAL = PolygonZone(
    "SUEZ_CANAL",
    vertices=[
        (29.8, 32.2), (31.3, 32.2), (31.3, 32.6),
        (29.8, 32.6),
    ],
    zone_type="high_risk",
    source="internal (chokepoint monitoring)",
)

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

CONFLICT_ZONES: List[AnyZone] = [
    PERSIAN_GULF, RED_SEA, EASTERN_MED, GULF_OF_ADEN, IRAQ_IRAN,
    IRAN_TERRITORIAL_WATERS, STRAIT_OF_HORMUZ, BAB_EL_MANDEB, SUEZ_CANAL,
]

CHOKEPOINT_ZONES: Dict[str, PolygonZone] = {
    "Strait of Hormuz": STRAIT_OF_HORMUZ,
    "Bab el-Mandeb": BAB_EL_MANDEB,
    "Suez Canal": SUEZ_CANAL,
}

SANCTIONS_ZONES: List[AnyZone] = [
    IRAN_TERRITORIAL_WATERS, STRAIT_OF_HORMUZ, FUJAIRAH_ANCHORAGE,
    BLACK_SEA, CRIMEA, LUHANSK_DONETSK,
    VENEZUELA_WATERS, NORTH_KOREA_WATERS,
]

ALL_ZONES: List[AnyZone] = list({z.name: z for z in CONFLICT_ZONES + SANCTIONS_ZONES}.values())


def in_zone_set(lat: float, lon: float, zones: List[AnyZone]) -> Optional[AnyZone]:
    """Return the first matching zone, or None."""
    for z in zones:
        if z.contains(lat, lon):
            return z
    return None


def all_matching_zones(lat: float, lon: float, zones: List[AnyZone]) -> List[AnyZone]:
    """Return all zones that contain the point."""
    return [z for z in zones if z.contains(lat, lon)]


def in_conflict_zone(lat: float, lon: float) -> bool:
    """Drop-in replacement for the old hardcoded _in_conflict_zone in sigint_agent."""
    return in_zone_set(lat, lon, CONFLICT_ZONES) is not None


def in_sanctions_zone(lat: float, lon: float) -> Optional[AnyZone]:
    """Check if point is in any sanctions zone; return the zone or None."""
    return in_zone_set(lat, lon, SANCTIONS_ZONES)
