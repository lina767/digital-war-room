"""
Heuristic detection of unusual data patterns vs the previous analysis run (same conflict).

Examples: spike in military/security-related text across NEWS + SIGINT + SOCMINT, volume spikes,
or a sharp escalation score jump. Stateless; callers pass the prior full result from cache.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Terms that indicate military / security / conflict chatter (lowercased matching).
_MILITARY_TERMS: Tuple[str, ...] = (
    "military",
    "missile",
    "drone",
    "troop",
    "strike",
    "strikes",
    "naval",
    "navy",
    "defense",
    "pentagon",
    "nato",
    "deployment",
    "border",
    "artillery",
    "fighter",
    "carrier",
    "rocket",
    "combat",
    "ballistic",
    "cruise",
    "warship",
    "submarine",
    "brigade",
    "battalion",
    "offensive",
    "retaliation",
    "mobilization",
    "air defense",
    "invasion",
    "raid",
    "shelling",
    "sanctions",
    "blockade",
    "fleet",
    "war zone",
    "armed forces",
    "defence",
    "ministry of defense",
    "idf",
    "irgc",
    "hezbollah",
    "houthi",
)


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    return str(x)


def _gather_text_blobs(result: Dict[str, Any]) -> List[str]:
    """Extract searchable text from news, SIGINT, SOCMINT, protest headlines."""
    news = result.get("news") or {}
    articles = news.get("articles") if isinstance(news, dict) else None
    blobs: List[str] = []
    if isinstance(articles, list):
        for a in articles[:80]:
            if not isinstance(a, dict):
                continue
            blobs.append(_safe_str(a.get("title")))
            blobs.append(_safe_str(a.get("description") or a.get("summary")))

    sig = result.get("sigint") or {}
    if isinstance(sig, dict):
        for r in (sig.get("conflict_reports") or [])[:40]:
            if isinstance(r, dict):
                blobs.append(_safe_str(r.get("title")))
                blobs.append(_safe_str(r.get("summary") or r.get("text")))
        for a in (sig.get("aircraft") or [])[:30]:
            if isinstance(a, dict):
                blobs.append(_safe_str(a.get("callsign") or a.get("type")))
        for s in (sig.get("ships") or [])[:20]:
            if isinstance(s, dict):
                blobs.append(_safe_str(s.get("name")))

    sm = result.get("socmint") or {}
    if isinstance(sm, dict):
        for t in (sm.get("top_signals") or [])[:40]:
            blobs.append(_safe_str(t))

    pr = result.get("protest") or {}
    if isinstance(pr, dict):
        for pa in (pr.get("protest_articles") or [])[:20]:
            if isinstance(pa, dict):
                blobs.append(_safe_str(pa.get("title")))

    return [b for b in blobs if b.strip()]


def _military_chatter_score(texts: List[str]) -> int:
    if not texts:
        return 0
    blob = " ".join(texts).lower()
    score = 0
    for term in _MILITARY_TERMS:
        if term in blob:
            score += blob.count(term)
    return score


def _snapshot_metrics(result: Dict[str, Any]) -> Dict[str, float]:
    news = result.get("news") or {}
    articles = news.get("articles") if isinstance(news, dict) else None
    n_art = float(len(articles)) if isinstance(articles, list) else 0.0

    sig = result.get("sigint") or {}
    reports = []
    ac = 0.0
    sh = 0.0
    if isinstance(sig, dict):
        cr = sig.get("conflict_reports")
        if isinstance(cr, list):
            reports = cr
        ac = float(len([x for x in (sig.get("aircraft") or []) if isinstance(x, dict)]))
        sh = float(len([x for x in (sig.get("ships") or []) if isinstance(x, dict)]))

    sm = result.get("socmint") or {}
    soc_n = float(len(sm.get("top_signals") or [])) if isinstance(sm, dict) else 0.0

    texts = _gather_text_blobs(result)
    mil = float(_military_chatter_score(texts))

    esc = result.get("escalation_score")
    try:
        esc_f = float(esc) if esc is not None else 0.0
    except (TypeError, ValueError):
        esc_f = 0.0

    return {
        "news_articles": n_art,
        "sigint_reports": float(len(reports)),
        "sigint_tracks": ac + sh,
        "socmint_signals": soc_n,
        "military_chatter_score": mil,
        "escalation_score": esc_f,
    }


def _ratio(curr: float, prev: float) -> Optional[float]:
    if prev <= 0:
        return None
    return curr / prev


def compute_pattern_flags(
    current: Dict[str, Any],
    previous: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Return 0–5 high-signal pattern flags (dicts with id, severity, title, detail, category).

    previous: full previous analysis payload from cache, or None on first run.
    """
    cur = _snapshot_metrics(current)
    flags: List[Dict[str, Any]] = []

    prev_m: Optional[Dict[str, float]] = None
    if previous and isinstance(previous, dict):
        try:
            prev_m = _snapshot_metrics(previous)
        except Exception:
            prev_m = None

    # --- Military / security chatter spike (NEWS + SIGINT + SOCMINT text) ---
    mc = cur["military_chatter_score"]
    mc_prev = prev_m["military_chatter_score"] if prev_m else 0.0
    rr = _ratio(mc, mc_prev) if prev_m is not None else None
    if prev_m is None:
        if mc >= 40:
            flags.append(
                {
                    "id": "military_chatter_elevated",
                    "category": "military_chatter",
                    "severity": "medium",
                    "title": "Elevated military & security chatter",
                    "detail": f"High keyword density across news and intel feeds (index {mc:.0f}) — no prior run to compare.",
                    "metrics": {"military_chatter_index": round(mc, 1)},
                }
            )
    else:
        # Ratio undefined when previous index was ~0 — use absolute emergence instead.
        emergence = mc_prev < 8 and mc >= 28
        ratio_spike = (
            mc >= 25
            and rr is not None
            and rr >= 1.55
            and (mc - mc_prev) >= 8
        )
        if emergence or ratio_spike:
            sev = "high" if (ratio_spike and rr is not None and rr >= 2.0) or (mc - mc_prev) >= 25 or mc >= 55 else "medium"
            if ratio_spike and rr is not None:
                detail = f"Cross-feed keyword index increased ~{rr:.1f}× vs last run ({mc:.0f} vs {mc_prev:.0f})."
                metrics: Dict[str, Any] = {
                    "current": round(mc, 1),
                    "previous": round(mc_prev, 1),
                    "ratio": round(rr, 2),
                }
            else:
                detail = f"Military & security chatter index surged from a quiet baseline ({mc:.0f} vs {mc_prev:.0f})."
                metrics = {"current": round(mc, 1), "previous": round(mc_prev, 1)}
            flags.append(
                {
                    "id": "military_chatter_spike",
                    "category": "military_chatter",
                    "severity": sev,
                    "title": "Spike in military & security chatter",
                    "detail": detail,
                    "metrics": metrics,
                }
            )

    # --- News volume spike ---
    na = cur["news_articles"]
    na_prev = prev_m["news_articles"] if prev_m else 0.0
    n_ratio = _ratio(na, na_prev) if prev_m is not None else None
    if prev_m is not None and na >= 12 and n_ratio is not None and n_ratio >= 1.45 and (na - na_prev) >= 6:
        flags.append(
            {
                "id": "news_volume_spike",
                "category": "news_volume",
                "severity": "medium",
                "title": "News volume spike",
                "detail": f"Article count up ~{n_ratio:.1f}× vs last run ({int(na)} vs {int(na_prev)}).",
                "metrics": {"current": int(na), "previous": int(na_prev), "ratio": round(n_ratio, 2)},
            }
        )

    # --- SIGINT intel reports spike ---
    sr = cur["sigint_reports"]
    sr_prev = prev_m["sigint_reports"] if prev_m else 0.0
    sr_ratio = _ratio(sr, sr_prev) if prev_m is not None else None
    if prev_m is not None and sr >= 3 and sr_ratio is not None and sr_ratio >= 1.6 and (sr - sr_prev) >= 2:
        flags.append(
            {
                "id": "sigint_reports_spike",
                "category": "sigint",
                "severity": "medium",
                "title": "SIGINT report volume spike",
                "detail": f"Open-source conflict intel reports increased ({int(sr)} vs {int(sr_prev)}).",
                "metrics": {"current": int(sr), "previous": int(sr_prev), "ratio": round(sr_ratio, 2)},
            }
        )

    # --- Escalation score jump ---
    if prev_m is not None:
        de = cur["escalation_score"] - prev_m["escalation_score"]
        if de >= 14.0:
            flags.append(
                {
                    "id": "escalation_jump",
                    "category": "escalation",
                    "severity": "high" if de >= 22 else "medium",
                    "title": "Sharp escalation score jump",
                    "detail": f"Composite score moved by +{de:.0f} points vs last run.",
                    "metrics": {
                        "current": round(cur["escalation_score"], 1),
                        "previous": round(prev_m["escalation_score"], 1),
                        "delta": round(de, 1),
                    },
                }
            )

    # --- SOCMINT signals spike ---
    ss = cur["socmint_signals"]
    ss_prev = prev_m["socmint_signals"] if prev_m else 0.0
    ss_ratio = _ratio(ss, ss_prev) if prev_m is not None else None
    if prev_m is not None and ss >= 5 and ss_ratio is not None and ss_ratio >= 1.75 and (ss - ss_prev) >= 4:
        flags.append(
            {
                "id": "socmint_spike",
                "category": "socmint",
                "severity": "medium",
                "title": "Social signal volume spike",
                "detail": f"Top signals count ~{ss_ratio:.1f}× vs last run ({int(ss)} vs {int(ss_prev)}).",
                "metrics": {"current": int(ss), "previous": int(ss_prev), "ratio": round(ss_ratio, 2)},
            }
        )

    # Sort: high severity first, then by category
    sev_rank = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: (sev_rank.get(str(f.get("severity", "low")), 2), f.get("category", "")))
    return flags[:5]


def attach_pattern_flags(state_service: Any, conflict: str, result: Dict[str, Any]) -> None:
    """Mutate result to add `pattern_flags` by comparing to cached previous run."""
    prev: Optional[Dict[str, Any]] = None
    if state_service is not None and hasattr(state_service, "get_cache"):
        try:
            entry = state_service.get_cache(conflict)
            if isinstance(entry, dict):
                prev = entry.get("result")
        except Exception:
            prev = None
    if not isinstance(prev, dict):
        prev = None
    try:
        result["pattern_flags"] = compute_pattern_flags(result, prev)
    except Exception:
        result["pattern_flags"] = []
