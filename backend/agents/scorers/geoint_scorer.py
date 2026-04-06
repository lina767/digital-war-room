from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ..utils import safe_float

try:
    import h3 as _h3_mod

    def _h3_cell(lat: float, lon: float, res: int = 4) -> str:
        if hasattr(_h3_mod, "latlng_to_cell"):
            return str(_h3_mod.latlng_to_cell(lat, lon, res))
        return str(_h3_mod.geo_to_h3(lat, lon, res))  # type: ignore[attr-defined]

    def _h3_center(cell: str) -> Tuple[float, float]:
        if hasattr(_h3_mod, "cell_to_latlng"):
            latlng = _h3_mod.cell_to_latlng(cell)
            return float(latlng[0]), float(latlng[1])
        latlng = _h3_mod.h3_to_geo(cell)  # type: ignore[attr-defined]
        return float(latlng[0]), float(latlng[1])

except ImportError:

    def _h3_cell(lat: float, lon: float, res: int = 4) -> str:
        # ~45–50 km bins at mid-latitudes when step ≈ 0.45°
        step = 0.45
        return f"grid:{round(lat / step):d}:{round(lon / step):d}"

    def _h3_center(cell: str) -> Tuple[float, float]:
        if not cell.startswith("grid:"):
            return 0.0, 0.0
        _, a, b = cell.split(":", 2)
        step = 0.45
        return int(a) * step, int(b) * step


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


def _region_neighbor_indices(
    points: List[Tuple[float, float]], i: int, eps_deg: float
) -> List[int]:
    lat_i, lon_i = points[i]
    out: List[int] = []
    for j, (lat_j, lon_j) in enumerate(points):
        if abs(lat_i - lat_j) <= eps_deg and abs(lon_i - lon_j) <= eps_deg:
            out.append(j)
    return out


def detect_anomaly_clusters_dbscan(
    anomalies: List[Dict[str, Any]],
    eps_deg: float = 0.5,
    min_samples: int = 3,
) -> List[Dict[str, Any]]:
    """
    Spatial density clusters (DBSCAN-style) on non–gas-flaring FIRMS points.
    Uses Chebyshev (square) neighborhoods to stay comparable to the old 0.5° box check.
    """
    points: List[Tuple[float, float]] = []
    for a in anomalies:
        if a.get("gas_flaring"):
            continue
        lat = _safe_float(a.get("lat"), 0)
        lon = _safe_float(a.get("lon"), 0)
        if lat == 0 and lon == 0:
            continue
        points.append((lat, lon))
    n = len(points)
    if n < min_samples:
        return []

    UNDEF, NOISE = -2, -1
    labels = [UNDEF] * n

    def neighbors(idx: int) -> List[int]:
        return _region_neighbor_indices(points, idx, eps_deg)

    cluster_id = 0
    for i in range(n):
        if labels[i] != UNDEF:
            continue
        nbrs = neighbors(i)
        if len(nbrs) < min_samples:
            labels[i] = NOISE
            continue
        cluster_id += 1
        labels[i] = cluster_id
        seed_queue: List[int] = list(nbrs)
        qi = 0
        while qi < len(seed_queue):
            q = seed_queue[qi]
            qi += 1
            if labels[q] == NOISE:
                labels[q] = cluster_id
            if labels[q] != UNDEF:
                continue
            labels[q] = cluster_id
            nbrs_q_x = neighbors(q)
            if len(nbrs_q_x) >= min_samples:
                for p in nbrs_q_x:
                    if p not in seed_queue:
                        seed_queue.append(p)

    by_cluster: Dict[int, List[Tuple[float, float]]] = defaultdict(list)
    for idx, lab in enumerate(labels):
        if lab > 0:
            by_cluster[lab].append(points[idx])

    clusters: List[Dict[str, Any]] = []
    for _, members in sorted(by_cluster.items(), key=lambda kv: -len(kv[1])):
        if len(members) < min_samples:
            continue
        avg_lat = sum(m[0] for m in members) / len(members)
        avg_lon = sum(m[1] for m in members) / len(members)
        clusters.append(
            {
                "center_lat": round(avg_lat, 4),
                "center_lon": round(avg_lon, 4),
                "count": len(members),
            }
        )
    return clusters


def _thermal_subscore(anomalies: List[Dict[str, Any]]) -> Tuple[float, int, List[Dict[str, Any]], int]:
    non_flaring = [a for a in anomalies if not a.get("gas_flaring")]
    high = sum(1 for a in non_flaring if a.get("confidence") == "high")
    explosion_count = sum(
        1 for a in non_flaring if a.get("type") == "explosion" or _safe_float(a.get("frp"), 0) > 500
    )
    clusters = detect_anomaly_clusters_dbscan(non_flaring, eps_deg=0.5, min_samples=3)
    recent = sum(1 for a in anomalies if _recent_within_hours(a.get("acquired", ""), 6.0))
    base = 20.0
    base += min(40, high * 5)
    base += min(45, explosion_count * 15)
    if clusters:
        base += 20
    base += recent * 5
    if len(anomalies) > 10:
        base += 10
    thermal = max(0.0, min(100.0, base))
    return thermal, explosion_count, clusters, recent


def _apply_baseline_to_thermal(
    thermal: float, anomaly_count: int, baseline_avg: Optional[float]
) -> Tuple[float, Optional[float]]:
    if baseline_avg is None or baseline_avg < 0.5:
        return thermal, None
    ratio = anomaly_count / baseline_avg
    adjusted = thermal
    if ratio >= 2.0:
        adjusted = min(100.0, thermal + min(15.0, (ratio - 1.0) * 7.0))
    elif ratio <= 0.5 and anomaly_count > 0:
        adjusted = max(0.0, thermal - 4.0)
    return adjusted, ratio


def _conflict_event_score(acled_points: Sequence[Dict[str, Any]], acled_report_count: int) -> float:
    n = len(acled_points) if acled_points else 0
    if n > 0:
        return min(100.0, n * 0.5)
    return min(100.0, acled_report_count * 20.0)


def _disaster_alert_score(gdacs_count: int) -> float:
    return min(100.0, gdacs_count * 28.0)


def _crisis_trend_score(reliefweb_reports: Sequence[Dict[str, Any]]) -> float:
    texts: List[str] = []
    for r in reliefweb_reports:
        if not isinstance(r, dict):
            continue
        src = (r.get("source") or "").strip()
        if src.startswith("CrisisWatch"):
            texts.append(f"{r.get('title', '')} {r.get('body_excerpt', '')}".lower())
    if not texts:
        return 0.0
    bad_hits = 0
    good_hits = 0
    bad_kw = (
        "deteriorat",
        "escalat",
        "worsen",
        "intensif",
        "breakdown",
        "flare-up",
        "flare up",
        "violence surge",
    )
    good_kw = ("improv", "ceasefire", "truce", "ease tension", "de-escalat", "progress", "stabil")
    for t in texts:
        if any(k in t for k in bad_kw):
            bad_hits += 1
        if any(k in t for k in good_kw):
            good_hits += 1
    s = 50.0 + min(35.0, bad_hits * 12.0) - min(35.0, good_hits * 14.0)
    return max(0.0, min(100.0, s))


def build_hex_corroboration(
    anomalies: List[Dict[str, Any]],
    acled_events: Sequence[Dict[str, Any]],
    h3_res: int = 4,
    max_cells: int = 20,
) -> Dict[str, Any]:
    """
    Bucket FIRMS + ACLED into H3 (or grid fallback) cells and count distinct source layers per cell.
    Cells with both FIRMS and ACLED are corroborated hotspots (reduces agricultural-burn-only FIRMS noise).
    """
    layers: Dict[str, Set[str]] = defaultdict(set)
    for a in anomalies:
        if not isinstance(a, dict) or a.get("gas_flaring"):
            continue
        lat = _safe_float(a.get("lat"), None)
        lon = _safe_float(a.get("lon"), None)
        if lat is None or lon is None:
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        cell = _h3_cell(lat, lon, h3_res)
        layers[cell].add("firms")

    for e in acled_events:
        if not isinstance(e, dict):
            continue
        lat = _safe_float(e.get("lat"), None)
        lon = _safe_float(e.get("lon"), None)
        if lat is None or lon is None:
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        cell = _h3_cell(lat, lon, h3_res)
        layers[cell].add("acled")

    corroborated = [c for c, s in layers.items() if len(s) >= 2]

    top = sorted(layers.keys(), key=lambda cid: (-len(layers[cid]), cid))[:max_cells]
    top_cells: List[Dict[str, Any]] = []
    for cid in top:
        s = layers[cid]
        try:
            clat, clon = _h3_center(cid)
        except Exception:
            clat, clon = 0.0, 0.0
        top_cells.append(
            {
                "cell": cid,
                "layers": sorted(s),
                "layer_count": len(s),
                "approx_lat": round(clat, 4),
                "approx_lon": round(clon, 4),
            }
        )

    bonus = min(15.0, 6.0 * len(corroborated))
    return {
        "h3_resolution": h3_res,
        "cells_with_firms": sum(1 for s in layers.values() if "firms" in s),
        "cells_with_acled": sum(1 for s in layers.values() if "acled" in s),
        "corroborated_cell_count": len(corroborated),
        "corroboration_bonus": bonus,
        "top_cells": top_cells,
    }


def compute_geoint_score(
    anomalies: List[Dict[str, Any]],
    *,
    reliefweb_reports: Optional[List[Dict[str, Any]]] = None,
    acled_events: Optional[List[Dict[str, Any]]] = None,
    gdacs_count: int = 0,
    baseline_avg_anomalies: Optional[float] = None,
) -> Tuple[float, int, List[Dict[str, Any]], int, Dict[str, Any]]:
    """
    Multi-factor GEOINT score:
      0.4 * thermal + 0.3 * conflict density + 0.15 * disaster + 0.15 * CrisisWatch trend,
    plus a small corroboration bonus when FIRMS and ACLED co-locate in the same hex/grid cell.
    """
    reports = reliefweb_reports or []
    acled = list(acled_events or [])
    acled_report_count = sum(1 for r in reports if isinstance(r, dict) and r.get("source") == "ACLED")

    thermal, explosion_count, clusters, recent = _thermal_subscore(anomalies)
    thermal, baseline_ratio = _apply_baseline_to_thermal(thermal, len(anomalies), baseline_avg_anomalies)

    conflict_sc = _conflict_event_score(acled, acled_report_count)
    disaster_sc = _disaster_alert_score(gdacs_count)
    crisis_sc = _crisis_trend_score(reports)

    corroboration = build_hex_corroboration(anomalies, acled, h3_res=4, max_cells=20)

    # Intercept 12 + 0.4*thermal with thermal floor 20 ⇒ ~20 when only FIRMS baseline fires (no conflict/disaster/CrisisWatch).
    intercept = 12.0
    weighted = (
        intercept
        + 0.4 * thermal
        + 0.3 * conflict_sc
        + 0.15 * disaster_sc
        + 0.15 * crisis_sc
        + float(corroboration.get("corroboration_bonus") or 0.0)
    )
    final = max(0.0, min(100.0, weighted))

    breakdown: Dict[str, Any] = {
        "thermal_score": round(thermal, 2),
        "conflict_event_score": round(conflict_sc, 2),
        "disaster_alert_score": round(disaster_sc, 2),
        "crisis_trend_score": round(crisis_sc, 2),
        "corroboration_bonus": round(float(corroboration.get("corroboration_bonus") or 0.0), 2),
        "baseline_ratio": baseline_ratio,
        "intercept": intercept,
        "weights": {"thermal": 0.4, "conflict": 0.3, "disaster": 0.15, "crisis_trend": 0.15},
    }

    breakdown["corroboration"] = corroboration

    return final, explosion_count, clusters, recent, breakdown


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
