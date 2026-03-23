"""
Cross-source signal fusion: embed, cluster, score, persist to Postgres.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from agents.utils import run_async
from quality.source_tiers import trust_for_agent_source, trust_for_source_name
from services.hf_service import _cosine_similarity, embed

logger = logging.getLogger(__name__)

SIM_THRESHOLD = float(os.getenv("QUALITY_FUSION_SIM_THRESHOLD", "0.82"))
TIME_WINDOW_H = float(os.getenv("QUALITY_FUSION_TIME_WINDOW_H", "24"))
GEO_MAX_KM = float(os.getenv("QUALITY_FUSION_GEO_MAX_KM", "120"))
MAX_CANDIDATES = int(os.getenv("QUALITY_FUSION_MAX_CANDIDATES", "72"))
CONFIRM_MIN_AGENTS = 2
CONFIRM_MIN_SCORE = float(os.getenv("QUALITY_FUSION_CONFIRM_MIN_SCORE", "0.42"))


@dataclass
class _Cand:
    text: str
    agent: str
    source_hint: str
    ts: float  # unix
    lat: Optional[float] = None
    lon: Optional[float] = None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _parse_ts(val: Any) -> float:
    if val is None:
        return datetime.now(timezone.utc).timestamp()
    if isinstance(val, (int, float)):
        return float(val) if val > 1e12 else float(val)  # assume seconds
    s = str(val).strip()
    if not s:
        return datetime.now(timezone.utc).timestamp()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return datetime.now(timezone.utc).timestamp()


def _normalize_text(s: str) -> str:
    t = re.sub(r"\s+", " ", (s or "").strip().lower())
    return t[:2000]


def _extract_news(news: Dict[str, Any]) -> List[_Cand]:
    out: List[_Cand] = []
    for a in (news.get("articles") or [])[:25]:
        if not isinstance(a, dict) or a.get("error"):
            continue
        title = (a.get("title") or "")[:400]
        body = (a.get("description") or a.get("summary") or a.get("body_excerpt") or "")[:400]
        text = _normalize_text(f"{title} {body}")
        if len(text) < 20:
            continue
        src = ""
        so = a.get("source")
        if isinstance(so, dict):
            src = str(so.get("name") or "")
        elif isinstance(so, str):
            src = so
        ts = _parse_ts(a.get("publishedAt") or a.get("published_at") or a.get("date"))
        out.append(_Cand(text=text, agent="news", source_hint=src or "news", ts=ts))
    return out


def _extract_socmint(soc: Dict[str, Any]) -> List[_Cand]:
    out: List[_Cand] = []
    for key in ("telegram_posts", "twitter_posts", "reddit_posts", "rss_articles", "reliefweb_reports"):
        for p in (soc.get(key) or [])[:12]:
            if not isinstance(p, dict) or p.get("error"):
                continue
            t = (p.get("text") or p.get("title") or p.get("body_excerpt") or "")[:500]
            text = _normalize_text(t)
            if len(text) < 15:
                continue
            hint = str(p.get("source") or p.get("account") or key)
            ts = _parse_ts(p.get("date") or p.get("published"))
            out.append(_Cand(text=text, agent="socmint", source_hint=hint, ts=ts))
    return out


def _extract_geoint(g: Dict[str, Any]) -> List[_Cand]:
    out: List[_Cand] = []
    for item in (g.get("reliefweb_reports") or [])[:15]:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or item.get("name") or "")[:300]
        body = (item.get("body") or item.get("summary") or "")[:300]
        text = _normalize_text(f"{title} {body}")
        if len(text) < 15:
            continue
        lat = item.get("lat") or item.get("latitude")
        lon = item.get("lon") or item.get("longitude")
        try:
            lat_f = float(lat) if lat is not None else None
            lon_f = float(lon) if lon is not None else None
        except (TypeError, ValueError):
            lat_f, lon_f = None, None
        ts = _parse_ts(item.get("date") or item.get("created"))
        out.append(
            _Cand(
                text=text,
                agent="geoint",
                source_hint="reliefweb",
                ts=ts,
                lat=lat_f,
                lon=lon_f,
            )
        )
    for an in (g.get("anomalies") or [])[:10]:
        if not isinstance(an, dict):
            continue
        text = _normalize_text(str(an.get("summary") or an.get("label") or "thermal signal"))
        if len(text) < 8:
            continue
        lat = an.get("lat") or an.get("latitude")
        lon = an.get("lon") or an.get("longitude")
        try:
            lat_f = float(lat) if lat is not None else None
            lon_f = float(lon) if lon is not None else None
        except (TypeError, ValueError):
            lat_f, lon_f = None, None
        out.append(_Cand(text=text, agent="geoint", source_hint="FIRMS", ts=_parse_ts(None), lat=lat_f, lon=lon_f))
    return out


def _extract_protest(pr: Dict[str, Any]) -> List[_Cand]:
    out: List[_Cand] = []
    for e in (pr.get("protest_events") or [])[:25]:
        if not isinstance(e, dict) or e.get("error"):
            continue
        notes = (e.get("notes") or e.get("location") or "")[:400]
        et = (e.get("event_type") or "")[:120]
        text = _normalize_text(f"{et} {notes}")
        if len(text) < 12:
            continue
        lat = e.get("latitude") or e.get("lat")
        lon = e.get("longitude") or e.get("lon")
        try:
            lat_f = float(lat) if lat is not None else None
            lon_f = float(lon) if lon is not None else None
        except (TypeError, ValueError):
            lat_f, lon_f = None, None
        ts = _parse_ts(e.get("event_date") or e.get("timestamp"))
        out.append(_Cand(text=text, agent="protest", source_hint="ACLED", ts=ts, lat=lat_f, lon=lon_f))
    for a in (pr.get("protest_articles") or [])[:12]:
        if not isinstance(a, dict) or a.get("error"):
            continue
        title = (a.get("title") or "")[:400]
        text = _normalize_text(title)
        if len(text) < 15:
            continue
        ts = _parse_ts(a.get("seendate") or a.get("date"))
        out.append(_Cand(text=text, agent="protest", source_hint="GDELT", ts=ts))
    return out


def _extract_diplo(d: Dict[str, Any]) -> List[_Cand]:
    out: List[_Cand] = []
    for key in ("un_press", "icj_items", "headlines"):
        block = d.get(key)
        if isinstance(block, list):
            for item in block[:8]:
                if isinstance(item, dict):
                    t = (item.get("title") or item.get("headline") or "")[:400]
                elif isinstance(item, str):
                    t = item[:400]
                else:
                    continue
                text = _normalize_text(t)
                if len(text) < 12:
                    continue
                out.append(_Cand(text=text, agent="diplo", source_hint=key, ts=_parse_ts(None)))
    return out


def _collect_candidates(agent_results: Dict[str, Dict[str, Any]]) -> List[_Cand]:
    cands: List[_Cand] = []
    cands.extend(_extract_news(agent_results.get("news") or {}))
    cands.extend(_extract_socmint(agent_results.get("socmint") or {}))
    cands.extend(_extract_geoint(agent_results.get("geoint") or {}))
    cands.extend(_extract_protest(agent_results.get("protest") or {}))
    cands.extend(_extract_diplo(agent_results.get("diplo") or {}))
    return cands[:MAX_CANDIDATES]


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.p = list(range(n))

    def find(self, x: int) -> int:
        if self.p[x] != x:
            self.p[x] = self.find(self.p[x])
        return self.p[x]

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _geo_compatible(a: _Cand, b: _Cand) -> bool:
    if a.lat is None or a.lon is None or b.lat is None or b.lon is None:
        return True
    d = _haversine_km(a.lat, a.lon, b.lat, b.lon)
    return d <= GEO_MAX_KM


def _time_compatible(a: _Cand, b: _Cand) -> bool:
    return abs(a.ts - b.ts) <= TIME_WINDOW_H * 3600


def _cluster_indices(cands: List[_Cand], embeddings: List[List[float]]) -> List[Set[int]]:
    n = len(cands)
    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            if not _time_compatible(cands[i], cands[j]):
                continue
            if not _geo_compatible(cands[i], cands[j]):
                continue
            if _cosine_similarity(embeddings[i], embeddings[j]) >= SIM_THRESHOLD:
                uf.union(i, j)
    groups: Dict[int, Set[int]] = {}
    for i in range(n):
        r = uf.find(i)
        groups.setdefault(r, set()).add(i)
    return list(groups.values())


def _score_cluster(
    indices: Sequence[int], cands: List[_Cand]
) -> Tuple[float, str, str, List[Dict[str, Any]], str, str, float, float]:
    members = [cands[i] for i in indices]
    agents = sorted({m.agent for m in members})
    n_agents = len(agents)
    trusts = [trust_for_agent_source(m.agent, m.source_hint) for m in members]
    avg_trust = sum(trusts) / len(trusts) if trusts else 0.5

    ts_list = [m.ts for m in members]
    t0 = min(ts_list)
    span_h = (max(ts_list) - t0) / 3600.0 if ts_list else 0.0
    if len(ts_list) > 1:
        hrs_from_t0 = [(t - t0) / 3600.0 for t in ts_list]
        try:
            std_h = statistics.pstdev(hrs_from_t0)
        except statistics.StatisticsError:
            std_h = 0.0
    else:
        std_h = 0.0
    temporal = max(0.0, 1.0 - min(std_h / 48.0, 1.0)) * 0.5 + max(0.0, 1.0 - min(span_h / 72.0, 1.0)) * 0.5

    coords = [(m.lat, m.lon) for m in members if m.lat is not None and m.lon is not None]
    if len(coords) >= 2:
        lat_m = sum(c[0] for c in coords) / len(coords)
        lon_m = sum(c[1] for c in coords) / len(coords)
        dists = [_haversine_km(lat_m, lon_m, la, lo) for la, lo in coords]
        mean_d = sum(dists) / len(dists)
        geo_score = max(0.0, 1.0 - min(mean_d / 400.0, 1.0))
    elif len(coords) == 1:
        geo_score = 0.65
    else:
        geo_score = 0.35

    src_part = min(1.0, n_agents / 4.0) * 0.3
    qual_part = avg_trust * 0.3
    temp_part = temporal * 0.2
    geo_part = geo_score * 0.2
    total = min(1.0, max(0.0, src_part + qual_part + temp_part + geo_part))

    canonical = max((m.text for m in members), key=len)[:500]
    sk = hashlib.sha256(_normalize_text(canonical).encode("utf-8")).hexdigest()[:48]

    detail_agents = [{"agent": m.agent, "source": m.source_hint} for m in members]
    confirmation = "confirmed" if n_agents >= CONFIRM_MIN_AGENTS and total >= CONFIRM_MIN_SCORE else "unconfirmed"
    decay_state = "active"
    if confirmation == "unconfirmed":
        decay_state = "active"

    first_ts = min(ts_list)
    last_ts = max(ts_list)
    return total, sk, canonical, detail_agents, confirmation, decay_state, first_ts, last_ts


def run_quality_fusion(conflict: str, agent_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build cross-validated signals. Persists to Postgres when DATABASE_URL is set.
    Returns a dict for the API: signals, summary, fusion_meta.
    """
    cands = _collect_candidates(agent_results)
    if not cands:
        return {
            "signals": [],
            "summary": "No cross-source candidates extracted.",
            "fusion_meta": {"candidates": 0, "clusters": 0},
        }

    texts = [c.text for c in cands]
    emb = run_async(embed(texts))
    if not emb or len(emb) != len(cands):
        return {
            "signals": [],
            "summary": "Cross-validation skipped (embeddings unavailable).",
            "fusion_meta": {"candidates": len(cands), "clusters": 0, "embed_error": True},
        }

    clusters = _cluster_indices(cands, emb)
    rows: List[Dict[str, Any]] = []
    out_signals: List[Dict[str, Any]] = []

    for group in clusters:
        idxs = sorted(group)
        (
            conf,
            sk,
            canonical,
            detail_agents,
            confirmation,
            decay_state,
            first_ts,
            last_ts,
        ) = _score_cluster(idxs, cands)
        lat_vals = [cands[i].lat for i in idxs if cands[i].lat is not None]
        lon_vals = [cands[i].lon for i in idxs if cands[i].lon is not None]
        lat_m = sum(lat_vals) / len(lat_vals) if lat_vals else None
        lon_m = sum(lon_vals) / len(lon_vals) if lon_vals else None

        first_dt = datetime.fromtimestamp(first_ts, tz=timezone.utc)
        last_dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)

        row = {
            "signal_key": sk,
            "canonical_text": canonical,
            "first_seen_utc": first_dt,
            "last_seen_utc": last_dt,
            "source_agents": detail_agents,
            "lat": lat_m,
            "lon": lon_m,
            "confidence": round(conf, 4),
            "confirmation": confirmation,
            "decay_state": decay_state,
        }
        rows.append(row)
        out_signals.append(
            {
                **row,
                "first_seen_utc": first_dt.isoformat(),
                "last_seen_utc": last_dt.isoformat(),
                "source_agents": detail_agents,
            }
        )

    async def _persist() -> List[Dict[str, Any]]:
        from services.quality_store import apply_signal_decay, fetch_quality_signals_for_conflict, upsert_quality_signals

        await upsert_quality_signals(conflict, rows)
        await apply_signal_decay(conflict)
        return await fetch_quality_signals_for_conflict(conflict)

    merged_db: List[Dict[str, Any]] = []
    if os.getenv("DATABASE_URL", "").strip():
        try:
            merged_db = run_async(_persist())
        except Exception as e:
            logger.warning("quality fusion persist failed: %s", e)

    summary = f"{len(out_signals)} fused signal(s), {sum(1 for s in out_signals if s.get('confirmation') == 'confirmed')} confirmed."
    return {
        "signals": merged_db if merged_db else out_signals,
        "summary": summary,
        "fusion_meta": {
            "candidates": len(cands),
            "clusters": len(clusters),
            "confirmed_count": sum(1 for s in out_signals if s.get("confirmation") == "confirmed"),
        },
    }
