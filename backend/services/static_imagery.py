"""Static satellite imagery fetcher (OSM-compatible, free).

Replaces the former Google Static Maps integration. Defaults to Esri's public
``World Imagery`` tile service (free, attribution required). Optionally uses
Mapbox Satellite when ``MAPBOX_TOKEN`` is set.

Both providers expose XYZ tiles. For visual verification (proximity/OSM tag
matching) we compose a 2x2 tile mosaic around the requested lat/lon so the
returned image covers enough context.

Configuration (all optional):
    STATIC_IMAGERY_PROVIDER     esri|mapbox   (default: esri; auto-mapbox if MAPBOX_TOKEN is set)
    STATIC_IMAGERY_ZOOM         int 12-19    (default: 18)
    STATIC_IMAGERY_TILE_GRID    int 1-3      (default: 2 => 2x2)
    MAPBOX_TOKEN                Mapbox public access token (free 50k req/month)
    ESRI_ATTRIBUTION            Override attribution text for compliance logging

Attribution requirements (set in the UI/downstream as appropriate):
    Esri: "Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"
    Mapbox: "(c) Mapbox (c) OpenStreetMap"
"""

from __future__ import annotations

import io
import math
import os
from typing import Optional, Tuple

from services.http_client import get_http_client

ESRI_TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
MAPBOX_TILE_URL = (
    "https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}@2x.png?access_token={token}"
)

DEFAULT_ZOOM = int(os.getenv("STATIC_IMAGERY_ZOOM", "18"))
DEFAULT_GRID = max(1, min(3, int(os.getenv("STATIC_IMAGERY_TILE_GRID", "2"))))


def _deg2num(lat: float, lon: float, zoom: int) -> Tuple[int, int]:
    lat_rad = math.radians(lat)
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def _selected_provider() -> str:
    provider = (os.getenv("STATIC_IMAGERY_PROVIDER") or "").strip().lower()
    if provider in ("esri", "mapbox"):
        return provider
    if (os.getenv("MAPBOX_TOKEN") or "").strip():
        return "mapbox"
    return "esri"


def _tile_url(provider: str, z: int, x: int, y: int) -> str:
    if provider == "mapbox":
        token = (os.getenv("MAPBOX_TOKEN") or "").strip()
        return MAPBOX_TILE_URL.format(z=z, x=x, y=y, token=token)
    return ESRI_TILE_URL.format(z=z, x=x, y=y)


async def _fetch_tile(client, url: str) -> Optional[bytes]:
    try:
        resp = await client.request("GET", url, retries=1)
        if getattr(resp, "status_code", 200) >= 400:
            return None
        data = resp.content
        return data if data else None
    except Exception:
        return None


async def fetch_static_satellite_image(
    lat: float,
    lon: float,
    *,
    zoom: Optional[int] = None,
    size: Optional[str] = None,  # kept for signature compatibility, unused
) -> Tuple[bytes, str]:
    """Return a satellite image covering the requested coordinate.

    Uses free Esri World Imagery tiles by default (no key required). The result
    is a PNG composed of a ``STATIC_IMAGERY_TILE_GRID``x``STATIC_IMAGERY_TILE_GRID``
    mosaic so callers get more context than a single 256px tile.

    Raises no exception on transient errors; returns empty bytes so the vision
    caller can degrade gracefully.
    """
    del size  # legacy parameter, ignored
    z = int(zoom if zoom is not None else DEFAULT_ZOOM)
    z = max(12, min(19, z))
    grid = DEFAULT_GRID
    provider = _selected_provider()

    center_x, center_y = _deg2num(lat, lon, z)
    offset = grid // 2
    client = get_http_client()

    try:
        from PIL import Image
    except Exception:
        # PIL missing — return single centre tile to avoid hard failure.
        url = _tile_url(provider, z, center_x, center_y)
        data = await _fetch_tile(client, url)
        return (data or b"", "image/png" if data else "application/octet-stream")

    tile_size = 256
    canvas = Image.new("RGB", (tile_size * grid, tile_size * grid), (0, 0, 0))
    any_success = False
    for dy in range(grid):
        for dx in range(grid):
            tx = center_x - offset + dx
            ty = center_y - offset + dy
            url = _tile_url(provider, z, tx, ty)
            data = await _fetch_tile(client, url)
            if not data:
                continue
            try:
                tile_img = Image.open(io.BytesIO(data)).convert("RGB")
                if tile_img.size != (tile_size, tile_size):
                    tile_img = tile_img.resize((tile_size, tile_size))
                canvas.paste(tile_img, (dx * tile_size, dy * tile_size))
                any_success = True
            except Exception:
                continue

    if not any_success:
        return b"", "application/octet-stream"

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), "image/png"
