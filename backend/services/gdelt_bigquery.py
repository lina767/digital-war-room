"""GDELT Events via BigQuery (`gdelt-bq.gdeltv2.events`) — optional CAMEO/EventRoot summaries.

Requires Application Default Credentials or `GOOGLE_APPLICATION_CREDENTIALS`.
Disabled when `GDELT_BQ_ENABLED` is false or when the optional dependency / auth is missing.

See docs/GDELT-API-REFERENCE.md (Events DB — BigQuery).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

GDELT_EVENTS_TABLE = "`gdelt-bq.gdeltv2.events`"

_STOP_WORDS = frozenset(
    {
        "the",
        "of",
        "and",
        "in",
        "to",
        "a",
        "for",
        "on",
        "with",
        "or",
        "an",
        "at",
        "by",
        "from",
        "war",
    }
)

# Maritime strait keywords for chokepoint agent (sanitized fragments).
CHOKEPOINT_BQ_SEARCH_TERMS = ("hormuz", "mandeb", "suez", "canal")


def _env_enabled() -> bool:
    v = (os.getenv("GDELT_BQ_ENABLED") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name) or default)
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name) or default)
    except (TypeError, ValueError):
        return default


def _sqldate_range(lookback_days: int) -> Tuple[int, int]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=max(1, min(lookback_days, 30)))
    return int(start.strftime("%Y%m%d")), int(end.strftime("%Y%m%d"))


def _sanitize_term(raw: str) -> Optional[str]:
    s = raw.lower().strip()
    s = re.sub(r"[^a-z0-9\s\-]", " ", s)
    s = " ".join(s.split())
    if len(s) < 2 or len(s) > 48:
        return None
    return s


def _terms_from_conflict(conflict: str, max_terms: int = 4) -> List[str]:
    chunk = (conflict or "").split(",")[0]
    out: List[str] = []
    for w in re.split(r"\s+", chunk):
        t = _sanitize_term(w)
        if not t or t in _STOP_WORDS:
            continue
        if t not in out:
            out.append(t)
        if len(out) >= max_terms:
            break
    if not out:
        whole = _sanitize_term(chunk)
        if whole:
            out.append(whole)
    return out[:max_terms]


def _match_sql(terms: Sequence[str]) -> Tuple[str, List[Tuple[str, str]]]:
    """Build OR-of-(Actor1/Actor2/SOURCEURL LIKE) using named parameters @p0 .. @pN."""
    params: List[Tuple[str, str]] = []
    clauses: List[str] = []
    for i, term in enumerate(terms):
        pat = f"%{term.lower()}%"
        pname = f"p{i}"
        clauses.append(
            "("
            f"LOWER(IFNULL(Actor1Name, '')) LIKE @{pname} OR "
            f"LOWER(IFNULL(Actor2Name, '')) LIKE @{pname} OR "
            f"LOWER(IFNULL(SOURCEURL, '')) LIKE @{pname}"
            ")"
        )
        params.append((pname, pat))
    return "(" + " OR ".join(clauses) + ")", params


@dataclass
class _BQConfig:
    lookback_days: int
    timeout_sec: float
    max_root_groups: int
    max_terms: int


def _load_config(for_chokepoint: bool = False) -> _BQConfig:
    if for_chokepoint:
        days = _int_env("GDELT_BQ_CHOKEPOINT_LOOKBACK_DAYS", 4)
    else:
        days = _int_env("GDELT_BQ_LOOKBACK_DAYS", 7)
    return _BQConfig(
        lookback_days=min(30, max(1, days)),
        timeout_sec=_float_env("GDELT_BQ_TIMEOUT_SEC", 25.0),
        max_root_groups=min(80, max(5, _int_env("GDELT_BQ_MAX_ROOT_GROUPS", 35))),
        max_terms=min(6, max(1, _int_env("GDELT_BQ_MAX_TERMS", 4))),
    )


def gdelt_bigquery_wants_run() -> bool:
    """True if feature flag allows attempting BigQuery (subject to auth)."""
    if not _env_enabled():
        return False
    try:
        from google.cloud import bigquery  # noqa: F401
    except ImportError:
        return False
    return True


def fetch_gdelt_event_roots_summary(
    conflict: str,
    *,
    search_terms: Optional[Sequence[str]] = None,
    lookback_days: Optional[int] = None,
    for_chokepoint: bool = False,
) -> Dict[str, Any]:
    """Query GDELT events (BigQuery) grouped by EventRootCode; return summary dict.

    On skip/error returns dict with ``ok: False`` and a ``reason`` / ``error`` string.
    """
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    base: Dict[str, Any] = {
        "source": "gdelt_bigquery",
        "fetched_at": fetched_at,
        "table": "gdelt-bq.gdeltv2.events",
    }

    if not _env_enabled():
        return {**base, "ok": False, "skipped": True, "reason": "GDELT_BQ_ENABLED is off"}

    try:
        from google.cloud import bigquery
    except ImportError:
        return {
            **base,
            "ok": False,
            "skipped": True,
            "reason": "google-cloud-bigquery not installed",
        }

    cfg = _load_config(for_chokepoint=for_chokepoint)
    if lookback_days is not None:
        cfg.lookback_days = min(30, max(1, lookback_days))

    if search_terms is not None:
        terms = []
        for t in search_terms:
            st = _sanitize_term(str(t))
            if st:
                terms.append(st.split()[0] if " " in st else st)
        terms = terms[: cfg.max_terms]
    else:
        terms = _terms_from_conflict(conflict, max_terms=cfg.max_terms)

    if not terms:
        return {**base, "ok": False, "skipped": True, "reason": "no_search_terms", "conflict": conflict}

    match_sql, param_pairs = _match_sql(terms)
    start_d, end_d = _sqldate_range(cfg.lookback_days)

    sql = f"""
WITH filtered AS (
  SELECT EventRootCode, GoldsteinScale, AvgTone
  FROM {GDELT_EVENTS_TABLE}
  WHERE SQLDATE BETWEEN @start_sqldate AND @end_sqldate
    AND {match_sql}
)
SELECT
  EventRootCode,
  COUNT(*) AS event_count,
  ROUND(AVG(GoldsteinScale), 4) AS avg_goldstein,
  ROUND(AVG(AvgTone), 4) AS avg_tone,
  (SELECT COUNT(*) FROM filtered) AS total_matched
FROM filtered
GROUP BY EventRootCode
ORDER BY event_count DESC
LIMIT @max_roots
"""

    bq_params: List[bigquery.ScalarQueryParameter] = [
        bigquery.ScalarQueryParameter("start_sqldate", "INT64", start_d),
        bigquery.ScalarQueryParameter("end_sqldate", "INT64", end_d),
        bigquery.ScalarQueryParameter("max_roots", "INT64", cfg.max_root_groups),
    ]
    for pname, pat in param_pairs:
        bq_params.append(bigquery.ScalarQueryParameter(pname, "STRING", pat))

    job_config = bigquery.QueryJobConfig(query_parameters=bq_params)

    project = (os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or "").strip() or None

    try:
        client = bigquery.Client(project=project) if project else bigquery.Client()
        job = client.query(sql, job_config=job_config)
        rows = list(job.result(timeout=cfg.timeout_sec))
    except Exception as e:
        logger.warning("GDELT BigQuery query failed: %s", e)
        return {
            **base,
            "ok": False,
            "error": str(e),
            "conflict": conflict,
            "search_terms": terms,
            "lookback_days": cfg.lookback_days,
        }

    by_root: List[Dict[str, Any]] = []
    total_matched = 0
    for row in rows:
        r = dict(row)
        if total_matched == 0 and r.get("total_matched") is not None:
            total_matched = int(r.get("total_matched") or 0)
        by_root.append(
            {
                "event_root_code": r.get("EventRootCode"),
                "count": int(r.get("event_count") or 0),
                "avg_goldstein": float(r["avg_goldstein"]) if r.get("avg_goldstein") is not None else None,
                "avg_tone": float(r["avg_tone"]) if r.get("avg_tone") is not None else None,
            }
        )

    return {
        **base,
        "ok": True,
        "conflict": conflict,
        "search_terms": terms,
        "lookback_days": cfg.lookback_days,
        "sqldate_start": start_d,
        "sqldate_end": end_d,
        "total_matched": total_matched,
        "by_event_root": by_root,
    }


def fetch_chokepoint_maritime_events_summary() -> Dict[str, Any]:
    """BigQuery GDELT slice for common chokepoint keywords (Hormuz, Mandeb, Suez)."""
    terms: List[str] = []
    seen: set[str] = set()
    for t in CHOKEPOINT_BQ_SEARCH_TERMS:
        s = _sanitize_term(t)
        if s and s not in seen:
            seen.add(s)
            terms.append(s)
    return fetch_gdelt_event_roots_summary(
        "chokepoint_maritime",
        search_terms=terms,
        for_chokepoint=True,
    )
