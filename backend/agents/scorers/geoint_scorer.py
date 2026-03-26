from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from ..utils import safe_float


def _safe_float(v: Any, default: float = 0.0) -> float:
    result = safe_float(v)
    return result if result is not None else default


def _recent_within_hours(acquired_str: str, hours: float = 6.0) -> bool:
    if not acquired_str or not isinstance(acquired_str, str):
        return False
    try:
        s = acquired_str.strip().replace("Z", "+00:00")
        if "T" in s:
            date_part, time_part = s.split("T", 1)
            time_part = time_part.replace("+00:00", "").replace("-", "").replace(":", "").strip()[:6]
            if len(time_part) >= 4 and ":" not in time_part:
                time_part = f"{time_part[:2]}:{time_part[2:4]}:00"
            s = f"{date_part}T{time_part}+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() <= hours * 3600
    except Exception:
        return False


def detect_explosion_clusters(
    anomalies: List[Dict[str, Any]],
    radius_deg: float = 0.5,
    max_hours: float | None = 2.0,
) -> List[Dict[str, Any]]:
    clusters: List[Dict[str, Any]] = []
    used = set()
    for a in anomalies:
        if a.get("gas_flaring"):
            continue
        lat = _safe_float(a.get("lat"), 0)
        lon = _safe_float(a.get("lon"), 0)
        key = (round(lat, 2), round(lon, 2))
        if key in used:
            continue
        nearby: List[Dict[str, Any]] = []
        t0 = None
        if max_hours is not None:
            def _parse_t(acq: str) -> Any:
                if not acq:
                    return None
                s = str(acq).strip().replace("Z", "+00:00")
                try:
                    return datetime.fromisoformat(s)
                except Exception:
                    return None

            t0 = _parse_t(a.get("acquired", ""))
            for b in anomalies:
                if b.get("gas_flaring"):
                    continue
                if abs(_safe_float(b.get("lat"), 0) - lat) > radius_deg:
                    continue
                if abs(_safe_float(b.get("lon"), 0) - lon) > radius_deg:
                    continue
                if t0 is not None and max_hours is not None:
                    tb = _parse_t(b.get("acquired", ""))
                    if tb is None:
                        continue
                    if abs((tb - t0).total_seconds()) > max_hours * 3600:
                        continue
                nearby.append(b)
        else:
            nearby = [
                b
                for b in anomalies
                if not b.get("gas_flaring")
                and abs(_safe_float(b.get("lat"), 0) - lat) <= radius_deg
                and abs(_safe_float(b.get("lon"), 0) - lon) <= radius_deg
            ]
        if len(nearby) >= 3:
            used.add(key)
            clusters.append(
                {
                    "center_lat": round(lat, 4),
                    "center_lon": round(lon, 4),
                    "count": len(nearby),
                }
            )
    return clusters


def compute_geoint_score(anomalies: List[Dict[str, Any]]) -> Tuple[float, int, List[Dict[str, Any]], int]:
    non_flaring = [a for a in anomalies if not a.get("gas_flaring")]
    high = sum(1 for a in non_flaring if a.get("confidence") == "high")
    explosion_count = sum(1 for a in non_flaring if a.get("type") == "explosion" or _safe_float(a.get("frp"), 0) > 500)
    clusters = detect_explosion_clusters(non_flaring, radius_deg=0.5, max_hours=2.0)
    recent = sum(1 for a in anomalies if _recent_within_hours(a.get("acquired", ""), 6.0))
    base = 20.0
    base += min(40, high * 5)
    base += min(45, explosion_count * 15)
    if clusters:
        base += 20
    base += recent * 5
    if len(anomalies) > 10:
        base += 10
    return (max(0.0, min(100.0, base)), explosion_count, clusters, recent)


def enrich_geoint_with_ner_entities(geoint_result: Dict[str, Any], entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not entities:
        return geoint_result

    location_ents = [ent for ent in entities if ent.get("type") == "LOCATION" and ent.get("entity")]
    if not location_ents:
        return geoint_result

    location_names = list(dict.fromkeys(ent.get("entity", "").strip() for ent in location_ents if ent.get("entity")))
    hotspots = geoint_result.get("hotspots", [])
    anomalies = geoint_result.get("anomalies", [])

    geoint_result["ner_locations"] = location_names[:30]

    matched_locations: List[str] = []
    hotspot_texts = " ".join(
        str(h.get("region", "")) + " " + str(h.get("city", "")) + " " + str(h.get("location_name", ""))
        for h in (hotspots + anomalies[:20])
    ).lower()
    for loc in location_names:
        if loc.lower() in hotspot_texts:
            matched_locations.append(loc)

    if matched_locations:
        geoint_result["ner_hotspot_matches"] = matched_locations
        existing_summary = geoint_result.get("summary", "")
        geoint_result["summary"] = f"{existing_summary} NER locations near hotspots: {', '.join(matched_locations[:5])}."
    else:
        geoint_result["ner_hotspot_matches"] = []

    return geoint_result
