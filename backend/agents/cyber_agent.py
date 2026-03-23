"""
CYBER / Threat Intel Agent – CISA KEV, threat reports, OTX, GreyNoise, InternetDB, NVD CVSS.
Structured Pydantic output, per-source fetched_at, KEV cache (TTL), dateAdded trend, MITRE ATT&CK extraction.
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from agents.otel_callbacks import traced
from services.http_client import get_http_client

from .health_registry import get_health_registry
from .utils import SourceResult, build_agent_meta, run_async, utc_now_iso

logger = logging.getLogger(__name__)

CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
GREYNOISE_GNQL_STATS_URL = "https://api.greynoise.io/v2/experimental/gnql/stats"
NVD_CVE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
INTERNETDB_BASE = "https://internetdb.shodan.io"
THREAT_RSS = [
    "https://cloudblog.withgoogle.com/topics/threat-intelligence/rss/",
    "https://www.crowdstrike.com/en-us/blog/feed",
]
OTX_PULSES_URL = "https://otx.alienvault.com/api/v1/pulses/subscribed"

CISA_TIMEOUT = 25.0
RSS_TIMEOUT = 15.0
OTX_GN_TIMEOUT = 20.0
NVD_TIMEOUT = 15.0
INTERNETDB_TIMEOUT = 10.0

KEV_CACHE_TTL_SEC = 86400  # 24h – CISA updates daily
NVD_RATE_DELAY_SEC = 6.5  # 5 req/30s without key
MAX_NVD_LOOKUPS = 5
MAX_NVD_LOOKUPS_NO_KEY = 2  # fewer lookups when unauthenticated to avoid long runs
MAX_INTERNETDB_IPS = 5

MAX_RSS_WHEN_NO_KEYWORDS = 5
MAX_OTX_WHEN_NO_KEYWORDS = 10

# MITRE ATT&CK: technique T1234 / T1234.001, tactic TA0001
MITRE_REGEX = re.compile(r"T\d{4}(?:\.\d{3})?|TA\d{4}", re.IGNORECASE)

CONFLICT_COUNTRY_CODES: Dict[str, List[str]] = {
    "iran": ["IR"],
    "us-iran": ["IR", "US"],
    "russia": ["RU"],
    "ukraine": ["UA"],
    "china": ["CN"],
    "taiwan": ["TW"],
    "north korea": ["KP"],
    "middle east": ["IR", "IL", "SY", "LB", "YE", "IQ", "JO", "SA", "AE"],
    "hezbollah": ["LB", "IL", "SY"],
    "houthis": ["YE", "SA"],
}


# ─── Pydantic models ───────────────────────────────────────────────────────


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CisaKevEntry(BaseModel):
    cve_id: Optional[str] = None
    vendor: Optional[str] = None
    product: Optional[str] = None
    date_added: Optional[str] = None
    cvss_score: Optional[float] = None
    cvss_severity: Optional[str] = None


class CisaKevResult(BaseModel):
    total: int = 0
    sample: List[CisaKevEntry] = Field(default_factory=list)
    added_7d: int = 0
    added_30d: int = 0
    error: Optional[str] = None
    fetched_at: datetime = Field(default_factory=_utc_now)


class ThreatReportEntry(BaseModel):
    title: str = ""
    url: str = ""
    summary: str = ""
    mitre_tactics: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    fetched_at: datetime = Field(default_factory=_utc_now)


class OtxPulseEntry(BaseModel):
    name: Optional[str] = None
    id: Optional[str] = None
    created: Optional[str] = None
    author_name: Optional[str] = None
    indicator_count: int = 0
    error: Optional[str] = None
    fetched_at: datetime = Field(default_factory=_utc_now)


class GreyNoiseScanContext(BaseModel):
    available: bool = False
    count: int = 0
    query: Optional[str] = None
    top_actors: List[Dict[str, Any]] = Field(default_factory=list)
    top_source_countries: List[Dict[str, Any]] = Field(default_factory=list)
    classifications: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    fetched_at: datetime = Field(default_factory=_utc_now)


class InternetDbHost(BaseModel):
    ip: str = ""
    ports: List[int] = Field(default_factory=list)
    vulns: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    hostnames: List[str] = Field(default_factory=list)


class InternetDbResult(BaseModel):
    hosts: List[InternetDbHost] = Field(default_factory=list)
    error: Optional[str] = None
    fetched_at: datetime = Field(default_factory=_utc_now)


class CyberAgentResult(BaseModel):
    cyber_score: float = 0.0
    cisa_kev: CisaKevResult = Field(default_factory=CisaKevResult)
    threat_reports: List[ThreatReportEntry] = Field(default_factory=list)
    otx_pulses: List[OtxPulseEntry] = Field(default_factory=list)
    greynoise_scan_context: GreyNoiseScanContext = Field(default_factory=GreyNoiseScanContext)
    internet_db: InternetDbResult = Field(default_factory=InternetDbResult)
    summary: str = ""
    fetched_at: datetime = Field(default_factory=_utc_now)


def _conflict_to_keywords(conflict: str) -> List[str]:
    """Keywords for filtering threat reports / OTX by conflict."""
    cl = (conflict or "").lower()
    if "iran" in cl and "middle east" not in cl and "naher osten" not in cl:
        return ["iran", "apt33", "apt34", "muddywater", "charming kitten", "oilrig"]
    if "russia" in cl or "ukraine" in cl:
        return ["russia", "ukraine", "sandworm", "apt28", "apt29", "gamaredon", "voodoobear"]
    if "china" in cl or "taiwan" in cl:
        return ["china", "apt40", "apt41", "mustang panda", "taiwan"]
    if "north korea" in cl:
        return ["north korea", "lazarus", "apt38"]
    if "hezbollah" in cl:
        return ["hezbollah", "lebanon", "nasrallah", "idf", "israel", "litani", "south lebanon", "apt34"]
    if "houthi" in cl or "houthis" in cl:
        return ["houthi", "houthis", "yemen", "ansar allah", "red sea", "sanaa", "red sea attacks"]
    if "israel" in cl or "gaza" in cl or "palestine" in cl:
        return ["israel", "gaza", "palestine", "hezbollah", "apt34", "lebanon"]
    # Naher Osten / Middle East: breite Abdeckung Iran, Levante, Golf, Jemen
    if "middle east" in cl or "naher osten" in cl or "middleeast" in cl:
        return [
            "iran",
            "apt33",
            "apt34",
            "muddywater",
            "oilrig",
            "israel",
            "gaza",
            "palestine",
            "hezbollah",
            "lebanon",
            "idf",
            "hamas",
            "houthi",
            "yemen",
            "ansar allah",
            "red sea",
            "syria",
            "iraq",
            "irgc",
            "tehran",
        ]
    return [cl] if cl else []


def _kev_cache_get() -> Optional[Dict[str, Any]]:
    """Get KEV from cache (Redis or in-memory TTL)."""
    redis_url = (os.getenv("REDIS_URL") or "").strip()
    if redis_url:
        try:
            import redis

            r = redis.from_url(redis_url, decode_responses=True)
            raw = r.get("cyber:kev:raw")
            if raw:
                import json

                return json.loads(raw)
        except Exception as e:
            logger.debug("CYBER: Redis KEV cache get failed: %s", e)
    try:
        from cachetools import TTLCache

        if not hasattr(_kev_cache_get, "_mem_cache"):
            _kev_cache_get._mem_cache = TTLCache(maxsize=1, ttl=KEV_CACHE_TTL_SEC)
        cache = _kev_cache_get._mem_cache
        return cache.get("kev")
    except Exception as e:
        logger.debug("CYBER: In-memory KEV cache get failed: %s", e)
    return None


def _kev_cache_set(data: Dict[str, Any]) -> None:
    """Store KEV in cache (Redis or in-memory TTL)."""
    redis_url = (os.getenv("REDIS_URL") or "").strip()
    if redis_url:
        try:
            import json

            import redis

            r = redis.from_url(redis_url, decode_responses=True)
            r.setex("cyber:kev:raw", KEV_CACHE_TTL_SEC, json.dumps(data))
        except Exception as e:
            logger.debug("CYBER: Redis KEV cache set failed: %s", e)
        return
    try:
        from cachetools import TTLCache

        if not hasattr(_kev_cache_get, "_mem_cache"):
            _kev_cache_get._mem_cache = TTLCache(maxsize=1, ttl=KEV_CACHE_TTL_SEC)
        _kev_cache_get._mem_cache["kev"] = data
    except Exception:
        pass


def _parse_kev_date(s: Optional[str]) -> Optional[datetime]:
    """Parse CISA date_added (YYYY-MM-DD)."""
    if not s:
        return None
    try:
        return datetime.strptime(s.strip()[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _count_kev_added_in_days(vulns: List[Dict], days: int) -> int:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    count = 0
    for v in vulns:
        d = _parse_kev_date(v.get("dateAdded") or v.get("date_added"))
        if d and d >= cutoff:
            count += 1
    return count


async def _fetch_nvd_cvss(client: Any, cve_id: str, api_key: Optional[str]) -> Optional[Dict[str, Any]]:
    """Fetch NVD CVE and return cvssMetricV31/v2 score and severity."""

    def _nvd_error_detail(resp: Any) -> str:
        """Best-effort extraction of NVD error payload for observability."""
        if resp is None:
            return ""
        try:
            payload = resp.json()
            if isinstance(payload, dict):
                detail = payload.get("message") or payload.get("error") or payload.get("errors") or payload
            else:
                detail = payload
            if isinstance(detail, (dict, list)):
                return json.dumps(detail)[:240]
            return str(detail)[:240]
        except Exception:
            return (getattr(resp, "text", "") or "")[:240]

    headers = {}
    if (api_key or "").strip():
        headers["apiKey"] = api_key.strip()
    try:
        resp = await client.request(
            "GET",
            NVD_CVE_URL,
            params={"cveId": cve_id},
            headers=headers or None,
            timeout=NVD_TIMEOUT,
        )
        data = resp.json()
        vulns = data.get("vulnerabilities") or []
        if not vulns:
            logger.info("CYBER: NVD returned no vulnerabilities for %s (possible data gap).", cve_id)
            return None
        cve = vulns[0].get("cve") or {}
        metrics = cve.get("metrics") or {}
        # Prefer CVSS 3.1, then 3.0, then 2.0
        for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            arr = metrics.get(key)
            if arr and isinstance(arr, list) and len(arr) > 0:
                m = arr[0].get("cvssData") or {}
                return {
                    "score": float(m.get("baseScore", 0)),
                    "severity": (m.get("baseSeverity") or m.get("severity") or ""),
                }
        logger.info("CYBER: NVD returned %s without CVSS metrics.", cve_id)
        return None
    except Exception as e:
        resp = getattr(e, "response", None)
        status = getattr(resp, "status_code", None)
        detail = _nvd_error_detail(resp)
        key_state = "set" if (api_key or "").strip() else "missing"
        if status == 403:
            logger.warning(
                "CYBER: NVD 403 for %s (api_key=%s). Check key validity/activation. detail=%s",
                cve_id,
                key_state,
                detail or "n/a",
            )
        elif status == 429:
            logger.warning(
                "CYBER: NVD 429 rate limit for %s (api_key=%s). detail=%s",
                cve_id,
                key_state,
                detail or "n/a",
            )
        elif status is not None:
            logger.warning(
                "CYBER: NVD %s for %s (api_key=%s). detail=%s",
                status,
                cve_id,
                key_state,
                detail or "n/a",
            )
        else:
            logger.debug("CYBER: NVD lookup %s failed: %s", cve_id, e)
        return None


async def _fetch_cisa_kev(client: Any) -> CisaKevResult:
    """Fetch CISA KEV (with cache) and optionally enrich sample with NVD CVSS; compute added_7d/30d."""
    fetched_at = _utc_now()
    vulns: List[Dict] = []
    err: Optional[str] = None
    cached = _kev_cache_get()
    if cached and isinstance(cached.get("vulnerabilities"), list):
        vulns = cached["vulnerabilities"]
    else:
        try:
            resp = await client.request("GET", CISA_KEV_URL, timeout=CISA_TIMEOUT)
            data = resp.json()
            vulns = data.get("vulnerabilities") or []
            _kev_cache_set(data)
        except Exception as e:
            logger.warning("CYBER: CISA KEV fetch failed: %s", e)
            err = str(e)
    total = len(vulns)
    added_7d = _count_kev_added_in_days(vulns, 7)
    added_30d = _count_kev_added_in_days(vulns, 30)
    sample_raw = vulns[:15]
    nvd_key = (os.getenv("NVD_API_KEY") or "").strip()
    sample: List[CisaKevEntry] = []
    for i, v in enumerate(sample_raw):
        cve_id = v.get("cveID") or v.get("cve_id")
        entry = CisaKevEntry(
            cve_id=cve_id,
            vendor=v.get("vendorProject") or v.get("vendor"),
            product=v.get("product"),
            date_added=v.get("dateAdded") or v.get("date_added"),
        )
        max_lookups = MAX_NVD_LOOKUPS if nvd_key else MAX_NVD_LOOKUPS_NO_KEY
        if cve_id and i < max_lookups:
            cvss = await _fetch_nvd_cvss(client, cve_id, nvd_key)
            if cvss:
                entry.cvss_score = cvss.get("score")
                entry.cvss_severity = cvss.get("severity")
            if not nvd_key:
                await asyncio.sleep(NVD_RATE_DELAY_SEC)
        sample.append(entry)
    return CisaKevResult(
        total=total,
        sample=sample,
        added_7d=added_7d,
        added_30d=added_30d,
        error=err,
        fetched_at=fetched_at,
    )


def _extract_mitre_tactics(text: str) -> List[str]:
    """Extract MITRE ATT&CK tactic/technique IDs from title or summary (regex)."""
    if not text:
        return []
    return list(dict.fromkeys(MITRE_REGEX.findall(text)))


async def _fetch_threat_rss(client: Any, conflict: str) -> List[ThreatReportEntry]:
    """Fetch threat intel RSS (Mandiant, CrowdStrike); filter by conflict; extract MITRE ATT&CK from titles."""
    import feedparser

    try:
        import httpx
    except ImportError:
        httpx = None  # type: ignore[assignment]
    keywords = _conflict_to_keywords(conflict)
    entries: List[ThreatReportEntry] = []
    fetched_at = _utc_now()
    feed_errors: List[str] = []
    for url in THREAT_RSS[:2]:
        try:
            resp = await client.request("GET", url, timeout=RSS_TIMEOUT, follow_redirects=True)
            feed = feedparser.parse(resp.text)
            raw = getattr(feed, "entries", [])[:15]
            for e in raw:
                title = (e.get("title") or "").strip()
                link = e.get("link") or ""
                summary = (e.get("summary") or e.get("description") or "")[:300]
                if not keywords or any(k in (title + summary).lower() for k in keywords):
                    entries.append(
                        ThreatReportEntry(
                            title=title,
                            url=link,
                            summary=(summary[:200] if summary else ""),
                            mitre_tactics=_extract_mitre_tactics(title + " " + summary),
                            fetched_at=fetched_at,
                        )
                    )
            if not keywords and len(entries) > MAX_RSS_WHEN_NO_KEYWORDS:
                entries = entries[:MAX_RSS_WHEN_NO_KEYWORDS]
        except Exception as e:
            err_msg = str(e)
            if httpx and isinstance(e, httpx.HTTPStatusError):
                err_msg = f"HTTP {e.response.status_code}"
            feed_errors.append(f"{url[:40]}… ({err_msg})")
            logger.warning("CYBER: Threat RSS %s failed: %s", url[:50], e)
            entries.append(
                ThreatReportEntry(
                    title="Feed error",
                    url=url,
                    summary="",
                    error=err_msg,
                    fetched_at=fetched_at,
                )
            )
    valid_count = len([r for r in entries if not r.error])
    if valid_count == 0 and feed_errors:
        logger.info(
            "CYBER: Threat RSS – no articles (feeds failed: %s). Check URLs or network.",
            "; ".join(feed_errors),
        )
    elif valid_count == 0 and keywords:
        logger.info(
            "CYBER: Threat RSS – feeds OK but no article matched conflict '%s' (keywords: %s). Try another conflict or check feed content.",
            conflict,
            keywords[:5],
        )
    return entries[:20]


async def _fetch_otx_pulses(client: Any, api_key: str, conflict: str) -> List[OtxPulseEntry]:
    """Fetch OTX pulses (subscribed only) with indicator_count per pulse; filter by conflict."""
    if not (api_key or "").strip():
        return []
    keywords = _conflict_to_keywords(conflict)
    fetched_at = _utc_now()
    try:
        import httpx
    except ImportError:
        httpx = None  # type: ignore[assignment]
    try:
        resp = await client.request(
            "GET",
            OTX_PULSES_URL,
            params={"limit": 30},
            headers={"X-OTX-API-KEY": api_key.strip()},
            timeout=OTX_GN_TIMEOUT,
        )
        data = resp.json()
        results = data.get("results") or []
        out: List[OtxPulseEntry] = []
        for p in results:
            name = (p.get("name") or "").lower()
            desc = (p.get("description") or "").lower()
            if not keywords or any(k in name or k in desc for k in keywords):
                ind = p.get("indicator_count")
                if ind is None and isinstance(p.get("indicators"), list):
                    ind = len(p["indicators"])
                out.append(
                    OtxPulseEntry(
                        name=p.get("name"),
                        id=str(p.get("id")) if p.get("id") is not None else None,
                        created=p.get("created"),
                        author_name=(p.get("author_name") or ""),
                        indicator_count=int(ind) if ind is not None else 0,
                        fetched_at=fetched_at,
                    )
                )
        if not keywords and len(out) > MAX_OTX_WHEN_NO_KEYWORDS:
            out = out[:MAX_OTX_WHEN_NO_KEYWORDS]
        if not results:
            logger.info(
                "CYBER: OTX – API OK but 0 subscribed pulses. At otx.alienvault.com subscribe to pulses/channels to get data (endpoint is /pulses/subscribed)."
            )
        elif not out and keywords:
            logger.info(
                "CYBER: OTX – %d pulse(s) from API but none matched conflict '%s' (keywords: %s).",
                len(results),
                conflict,
                keywords[:5],
            )
        return out[:15]
    except Exception as e:
        err_msg = str(e)
        if httpx and isinstance(e, httpx.HTTPStatusError):
            err_msg = f"HTTP {e.response.status_code}"
            try:
                body = (e.response.text or "")[:200]
                if body:
                    logger.warning("CYBER: OTX pulses failed %s – %s", err_msg, body)
            except Exception:
                pass
        else:
            logger.warning("CYBER: OTX pulses fetch failed: %s", e)
        return [OtxPulseEntry(name=None, error=err_msg, fetched_at=fetched_at)]


async def _fetch_greynoise_scan_context(client: Any, api_key: str) -> GreyNoiseScanContext:
    """GreyNoise GNQL stats for malicious scanners (last 7d). Requires GREYNOISE_API_KEY."""
    fetched_at = _utc_now()
    if not (api_key or "").strip():
        return GreyNoiseScanContext(available=False, error="GREYNOISE_API_KEY not set", count=0, fetched_at=fetched_at)
    query = "classification:malicious last_seen:1w"
    try:
        resp = await client.request(
            "GET",
            GREYNOISE_GNQL_STATS_URL,
            params={"query": query, "count": 10},
            headers={"key": api_key.strip(), "Accept": "application/json"},
            timeout=OTX_GN_TIMEOUT,
        )
        data = resp.json()
        count = int(data.get("count") or 0)
        stats = data.get("stats") or {}
        actors = [x for x in (stats.get("actors") or [])[:5] if isinstance(x, dict) and x.get("actor")]
        source_countries = [
            x for x in (stats.get("source_countries") or [])[:5] if isinstance(x, dict) and x.get("country")
        ]
        classifications = [x for x in (stats.get("classifications") or []) if isinstance(x, dict)]
        return GreyNoiseScanContext(
            available=True,
            count=count,
            query=query,
            top_actors=[{"actor": a.get("actor"), "count": a.get("count")} for a in actors],
            top_source_countries=[{"country": c.get("country"), "count": c.get("count")} for c in source_countries],
            classifications=[
                {"classification": c.get("classification"), "count": c.get("count")} for c in classifications
            ],
            fetched_at=fetched_at,
        )
    except Exception as e:
        logger.warning("CYBER: GreyNoise fetch failed: %s", e)
        return GreyNoiseScanContext(available=False, error=str(e), count=0, fetched_at=fetched_at)


INTERNETDB_DEFAULT_IPS = [
    "78.39.159.1",  # Iran (AS12880, IRNIC)
    "185.143.233.1",  # Iran (AS203214, HiWeb)
    "5.160.218.1",  # Iran (AS48159, Telecommunication Infrastructure)
    "91.108.128.1",  # Iran (AS44208, IRANCELL)
]


def _get_internetdb_ips() -> List[str]:
    """Conflict-relevant IPs for Shodan InternetDB: from env CYBER_INTERNETDB_IPS or defaults."""
    raw = (os.getenv("CYBER_INTERNETDB_IPS") or "").strip()
    if not raw:
        return INTERNETDB_DEFAULT_IPS[:MAX_INTERNETDB_IPS]
    return [ip.strip() for ip in raw.split(",") if ip.strip()][:MAX_INTERNETDB_IPS]


async def _fetch_internetdb(client: Any, ips: List[str]) -> InternetDbResult:
    """Query Shodan InternetDB for open ports, vulns, tags per IP (no API key)."""
    fetched_at = _utc_now()
    if not ips:
        return InternetDbResult(hosts=[], fetched_at=fetched_at)
    hosts: List[InternetDbHost] = []
    for ip in ips[:MAX_INTERNETDB_IPS]:
        try:
            resp = await client.request(
                "GET",
                f"{INTERNETDB_BASE}/{ip.strip()}",
                timeout=INTERNETDB_TIMEOUT,
            )
            data = resp.json() if resp.status_code == 200 else {}
            hosts.append(
                InternetDbHost(
                    ip=data.get("ip", ip),
                    ports=data.get("ports") or [],
                    vulns=data.get("vulns") or [],
                    tags=data.get("tags") or [],
                    hostnames=data.get("hostnames") or [],
                )
            )
        except Exception as e:
            logger.debug("CYBER: InternetDB %s failed: %s", ip, e)
    return InternetDbResult(hosts=hosts, fetched_at=fetched_at)


def _compute_cyber_score(
    kev: CisaKevResult,
    threat_reports: List[ThreatReportEntry],
    otx_pulses: List[OtxPulseEntry],
    greynoise: GreyNoiseScanContext,
    internet_db: InternetDbResult,
) -> float:
    """Compute CYBER escalation score 0–100."""
    base = 25.0
    if kev.total > 400:
        base += 20
    elif kev.total > 200:
        base += 12
    elif kev.total > 100:
        base += 8
    if kev.added_30d > 10:
        base += 3
    elif kev.added_7d > 3:
        base += 2

    valid_reports = [r for r in threat_reports if not r.error and r.title and "Feed error" not in r.title]
    if len(valid_reports) >= 5:
        base += 25
    elif len(valid_reports) >= 2:
        base += 15
    elif len(valid_reports) >= 1:
        base += 8

    valid_otx = [p for p in otx_pulses if not p.error and p.name]
    if len(valid_otx) >= 3:
        base += 22
    elif len(valid_otx) >= 1:
        base += 10

    if greynoise.available and greynoise.count > 0:
        base += min(8, 2 + (greynoise.count // 5000))

    if internet_db.hosts:
        vuln_hosts = sum(1 for h in internet_db.hosts if h.vulns)
        if vuln_hosts > 0:
            base += min(5, vuln_hosts)
    return min(100.0, max(0.0, base))


async def _generate_haiku_summary_cyber(
    conflict: str,
    kev: CisaKevResult,
    threat_reports: List[ThreatReportEntry],
    otx_pulses: List[OtxPulseEntry],
    greynoise: GreyNoiseScanContext,
    internet_db: InternetDbResult,
    score: float,
) -> Optional[str]:
    """Optional 2-3 sentence analyst summary via haiku_service.analyst_summary."""
    try:
        from services.haiku_service import analyst_summary

        compact = {
            "conflict": conflict,
            "cyber_score": score,
            "cisa_kev_total": kev.total,
            "cisa_kev_new_7d": kev.added_7d,
            "threat_reports_count": len([r for r in threat_reports if r.title and not r.error]),
            "otx_pulses_count": len([p for p in otx_pulses if p.name and not p.error]),
            "greynoise_count": greynoise.count if greynoise.available else None,
            "internet_db_hosts": len(internet_db.hosts) if internet_db.hosts else 0,
        }
        import json

        data = json.dumps(compact, indent=2)
        system = (
            "You are a cyber-threat analyst for conflict zones. Summarize the following "
            "CYBER data in 2-3 sentences: CISA KEV, threat reports, OTX pulses, GreyNoise, InternetDB. "
            "Focus on the most critical signals. Write in English."
        )
        out = await analyst_summary(system=system, data=data, max_tokens=256, usage_agent="cyber")
        return out.strip() if out else None
    except Exception:
        return None


def _build_summary(
    kev: CisaKevResult,
    threat_reports: List[ThreatReportEntry],
    otx_pulses: List[OtxPulseEntry],
    greynoise: GreyNoiseScanContext,
    internet_db: InternetDbResult,
    score: float,
) -> str:
    parts = []
    if kev.total:
        parts.append(f"CISA KEV: {kev.total} known exploited ({kev.added_7d} new 7d, {kev.added_30d} new 30d).")
    valid_r = [r for r in threat_reports if r.title and not r.error and "Feed error" not in r.title]
    if valid_r:
        parts.append(f"Threat reports: {len(valid_r)} conflict-related.")
    valid_o = [p for p in otx_pulses if p.name and not p.error]
    if valid_o:
        parts.append(f"OTX pulses: {len(valid_o)} relevant.")
    if greynoise.available and greynoise.count is not None:
        parts.append(f"GreyNoise: {greynoise.count} malicious scanners (7d).")
    elif greynoise.error and "not set" not in str(greynoise.error):
        parts.append("GreyNoise: unavailable.")
    if internet_db.hosts:
        parts.append(f"InternetDB: {len(internet_db.hosts)} conflict-relevant IP(s) checked.")
    if not parts:
        return "CYBER: No CISA KEV, threat RSS, OTX, or GreyNoise data available."
    return "CYBER: " + " ".join(parts)


def _greynoise_context_from_snapshot(conflict: str) -> Optional[GreyNoiseScanContext]:
    """Use greynoise_agent stored snapshot for this conflict (avoids duplicate API calls)."""
    try:
        from agents.greynoise_agent import get_greynoise_context_for_cyber

        data = get_greynoise_context_for_cyber(conflict)
        if not data:
            return None
        fetched_at = data.get("fetched_at")
        if isinstance(fetched_at, str):
            try:
                fetched_at = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                fetched_at = _utc_now()
        elif not isinstance(fetched_at, datetime):
            fetched_at = _utc_now()
        return GreyNoiseScanContext(
            available=data.get("available", True),
            count=int(data.get("count") or 0),
            query=data.get("query"),
            top_actors=data.get("top_actors") or [],
            top_source_countries=data.get("top_source_countries") or [],
            classifications=data.get("classifications") or [],
            error=data.get("error"),
            fetched_at=fetched_at,
        )
    except Exception as e:
        logger.debug("CYBER: GreyNoise snapshot for %s failed: %s", conflict, e)
        return None


def run_cyber_agent(conflict: str, peers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Run CYBER agent: CISA KEV (cached), threat RSS, OTX, GreyNoise, InternetDB, NVD CVSS.
    Returns structured dict (from CyberAgentResult) for backward compatibility with supervisor.
    GreyNoise: uses greynoise_agent stored snapshot when available to avoid duplicate API calls.
    """
    otx_key = (os.getenv("OTX_API_KEY") or "").strip()
    greynoise_key = (os.getenv("GREYNOISE_API_KEY") or "").strip()
    internetdb_ips = _get_internetdb_ips()
    if not otx_key:
        logger.info(
            "CYBER: OTX_API_KEY not set – OTX pulses skipped. Set in backend/.env for AlienVault OTX (otx.alienvault.com)."
        )

    async def _no_otx() -> List[OtxPulseEntry]:
        return []

    async def _no_gn() -> GreyNoiseScanContext:
        return GreyNoiseScanContext(available=False, error="GREYNOISE_API_KEY not set", count=0, fetched_at=_utc_now())

    async def _run() -> CyberAgentResult:
        client = get_http_client()
        # Prefer GreyNoise data from greynoise_agent store (conflict-specific, no extra API call)
        greynoise_snapshot = _greynoise_context_from_snapshot(conflict)

        async def _greynoise_source():
            if greynoise_snapshot is not None:
                return greynoise_snapshot
            return await (_fetch_greynoise_scan_context(client, greynoise_key) if greynoise_key else _no_gn())

        kev, threat_reports, otx_pulses, greynoise, internet_db = await asyncio.gather(
            _fetch_cisa_kev(client),
            _fetch_threat_rss(client, conflict),
            _fetch_otx_pulses(client, otx_key, conflict) if otx_key else _no_otx(),
            _greynoise_source(),
            _fetch_internetdb(client, internetdb_ips),
        )
        cyber_score = _compute_cyber_score(kev, threat_reports, otx_pulses, greynoise, internet_db)
        rule_summary = _build_summary(kev, threat_reports, otx_pulses, greynoise, internet_db, cyber_score)
        llm_summary = await _generate_haiku_summary_cyber(
            conflict,
            kev,
            threat_reports,
            otx_pulses,
            greynoise,
            internet_db,
            cyber_score,
        )
        summary = llm_summary if llm_summary else rule_summary
        return CyberAgentResult(
            cyber_score=round(cyber_score, 1),
            cisa_kev=kev,
            threat_reports=threat_reports,
            otx_pulses=otx_pulses,
            greynoise_scan_context=greynoise,
            internet_db=internet_db,
            summary=summary,
            fetched_at=_utc_now(),
        )

    start = time.perf_counter()
    fetched_at = utc_now_iso()
    with traced("analysis.agent.cyber", {"conflict": conflict}):
        try:
            result = run_async(_run())
            out = result.model_dump(mode="json")
            kev = result.cisa_kev
            tr = result.threat_reports
            otx = result.otx_pulses
            gn = result.greynoise_scan_context
            idb = result.internet_db
            nvd_enriched = len(
                [e for e in (kev.sample or []) if e.cve_id and (e.cvss_score is not None or e.cvss_severity)]
            )
            nvd_candidates = len([e for e in (kev.sample or []) if e.cve_id])
            source_results = [
                SourceResult(
                    name="CISA KEV",
                    status="ok" if (kev.total or kev.sample) and not kev.error else "error",
                    fetched_at=fetched_at,
                    record_count=kev.total or 0,
                ),
                SourceResult(
                    name="Threat RSS",
                    status="ok"
                    if not any(r.error for r in tr)
                    else ("ok" if any(r.title and not r.error for r in tr) else "error"),
                    fetched_at=fetched_at,
                    record_count=len([r for r in tr if not r.error]),
                ),
                SourceResult(
                    name="OTX",
                    status="ok"
                    if not any(p.error for p in otx)
                    else ("ok" if any(p.name and not p.error for p in otx) else "error"),
                    fetched_at=fetched_at,
                    record_count=len([p for p in otx if not p.error]),
                ),
                SourceResult(
                    name="GreyNoise",
                    status="ok" if (gn and gn.available and not gn.error) else "error",
                    fetched_at=fetched_at,
                    record_count=gn.count if gn else 0,
                ),
                SourceResult(
                    name="InternetDB",
                    status="ok" if (idb and idb.hosts) else "error",
                    fetched_at=fetched_at,
                    record_count=len(idb.hosts) if idb else 0,
                ),
                SourceResult(
                    name="NVD",
                    status="ok" if nvd_enriched > 0 else ("error" if nvd_candidates > 0 else "ok"),
                    fetched_at=fetched_at,
                    record_count=nvd_enriched,
                ),
            ]
            reg = get_health_registry()
            if reg:
                for sr in source_results:
                    reg.record_result(sr.name, "cyber", sr)
            duration_ms = int((time.perf_counter() - start) * 1000)
            has_data = bool(result.cisa_kev.sample or result.threat_reports or result.otx_pulses)
            out["_meta"] = build_agent_meta(
                "cyber",
                fetched_at,
                duration_ms,
                source_results,
                has_any_data=has_data,
            )
            return out
        except Exception as e:
            logger.exception("CYBER agent run failed")
            duration_ms = int((time.perf_counter() - start) * 1000)
            fallback = CyberAgentResult(
                cyber_score=25.0,
                cisa_kev=CisaKevResult(total=0, sample=[], error=str(e)),
                summary=f"CYBER error: {e}",
            )
            out = fallback.model_dump(mode="json")
            out["_meta"] = build_agent_meta(
                "cyber",
                fetched_at,
                duration_ms,
                [],
                fallback_used=True,
                error_summary=str(e),
                has_any_data=False,
            )
            return out
