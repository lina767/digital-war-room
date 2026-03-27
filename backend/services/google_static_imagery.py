import os
from typing import Optional, Tuple

from services.http_client import get_http_client

GOOGLE_STATIC_MAPS_URL = "https://maps.googleapis.com/maps/api/staticmap"


async def fetch_static_satellite_image(
    lat: float,
    lon: float,
    *,
    zoom: Optional[int] = None,
    size: Optional[str] = None,
) -> Tuple[bytes, str]:
    """Fetch Google Static satellite image for given lat/lon."""
    api_key = (os.getenv("GOOGLE_MAPS_STATIC_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("missing_google_static_api_key")

    z = int(zoom if zoom is not None else int(os.getenv("PROXIMITY_GOOGLE_STATIC_ZOOM", "18")))
    img_size = size or os.getenv("PROXIMITY_GOOGLE_STATIC_SIZE", "640x640")
    maptype = (os.getenv("PROXIMITY_GOOGLE_STATIC_MAPTYPE", "satellite") or "satellite").strip()
    params = {
        "center": f"{lat:.6f},{lon:.6f}",
        "zoom": max(12, min(21, z)),
        "size": img_size,
        "maptype": maptype,
        "key": api_key,
        "scale": 2,
    }
    client = get_http_client()
    resp = await client.request("GET", GOOGLE_STATIC_MAPS_URL, params=params, retries=1)
    content_type = (resp.headers.get("content-type") or "image/png").split(";")[0].strip()
    return resp.content, content_type
