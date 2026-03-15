"""
CYBER / Threat Intel Agent – CISA KEV, threat reports, OTX, GreyNoise, InternetDB, NVD CVSS.
Structured Pydantic output, per-source fetched_at, KEV cache (TTL), dateAdded trend, MITRE ATT&CK extraction.
"""
import asyncio
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .utils import run_async
from services.http_client import get_http_client
from agents.otel_callbacks import traced

logger = logging.getLogger(__name__)

CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
GREYNOISE_GNQL_STATS_URL = "https://api.greynoise.io/v2/experimental/gnql/stats"
NVD_CVE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
INTERNETDB_BASE = "https://internetdb.shodan.io"
THREAT_RSS = [
    "https://www.mandiant.com/resources/blog/rss.xml",
    "https://www.crowdstrike.com/blog/feed/",
]
OTX_PULSES_URL = "https://otx.alienvault.com/api/v1/pulses/subscribed"

CISA_TIMEOUT = 25.0
RSS_TIMEOUT = 15.0
OTX_GN_TIMEOUT = 20.0
NVD_TIMEOUT = 15.0
INTERNETDB_TIMEOUT = 10.0

KEV_CACHE_TTL_SEC = 86400  # 24h – CISA updates daily
NVD_RATE_DELAY_SEC = 6.5   # 5 req/30s without key
MAX_NVD_LOOKUPS = 5
MAX_NVD_LOOKUPS_NO_KEY = 2  # fewer lookups when unauthenticated to avoid long runs
MAX_INTERNETDB_IPS = 5

MAX_RSS_WHEN_NO_KEYWORDS = 5
MAX_OTX_WHEN_NO_KEYWORDS = 10

# MITRE ATT&CK: technique T1234 / T1234.001, tactic TA0001
MITRE_REGEX = re.compile(r"T\d{4}(?:\.\d{3})?|TA\d{4}", re.IGNORECASE)

CONFLICT_COUNTRY_CODES: Dict[str, List[str]] = {
    "iran": ["IR"], "us-iran": ["IR", "US"], "russia": ["RU"], "ukraine": ["UA"],
    "china": ["CN"], "taiwan": ["TW"], "north korea": ["KP"],
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
    if "iran" in cl:
        return ["iran", "apt33", "apt34", "muddywater", "charming kitten", "oilrig"]
    if "russia" in cl or "ukraine" in cl:
        return ["russia", "ukraine", "sandworm", "apt28", "apt29", "gamaredon", "voodoobear"]
    if "china" in cl or "taiwan" in cl:
        return ["china", "apt40", "apt41", "mustang panda", "taiwan"]
    if "north korea" in cl:
        return ["north korea", "lazarus", "apt38"]
    if "israel" in cl or "gaza" in cl or "palestine" in cl or "hezbollah" in cl:
        return ["israel", "gaza", "palestine", "hezbollah", "apt34", "lebanon"]
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
            import redis
            import json
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
        vulns = (data.get("vulnerabilities") or [])
        if not vulns:
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
        return None
    except Exception as e:
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
    """Fetch threat intel RSS; filter by conflict; extract MITRE ATT&CK from titles."""
    import feedparser
    keywords = _conflict_to_keywords(conflict)
    entries: List[ThreatReportEntry] = []
    fetched_at = _utc_now()
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
                    entries.append(ThreatReportEntry(
                        title=title,
                        url=link,
                        summary=(summary[:200] if summary else ""),
                        mitre_tactics=_extract_mitre_tactics(title + " " + summary),
                        fetched_at=fetched_at,
                    ))
            if not keywords and len(entries) > MAX_RSS_WHEN_NO_KEYWORDS:
                entries = entries[:MAX_RSS_WHEN_NO_KEYWORDS]
        except Exception as e:
            logger.warning("CYBER: Threat RSS %s failed: %s", url[:50], e)
            entries.append(ThreatReportEntry(
                title="Feed error", url=url, summary="", error=str(e), fetched_at=fetched_at,
            ))
    return entries[:20]


async def _fetch_otx_pulses(client: Any, api_key: str, conflict: str) -> List[OtxPulseEntry]:
    """Fetch OTX pulses with indicator_count per pulse; filter by conflict."""
    if not (api_key or "").strip():
        return []
    keywords = _conflict_to_keywords(conflict)
    fetched_at = _utc_now()
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
                out.append(OtxPulseEntry(
                    name=p.get("name"),
                    id=str(p.get("id")) if p.get("id") is not None else None,
                    created=p.get("created"),
                    author_name=(p.get("author_name") or ""),
                    indicator_count=int(ind) if ind is not None else 0,
                    fetched_at=fetched_at,
                ))
        if not keywords and len(out) > MAX_OTX_WHEN_NO_KEYWORDS:
            out = out[:MAX_OTX_WHEN_NO_KEYWORDS]
        return out[:15]
    except Exception as e:
        logger.warning("CYBER: OTX pulses fetch failed: %s", e)
        return [OtxPulseEntry(name=None, error=str(e), fetched_at=fetched_at)]


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
        source_countries = [x for x in (stats.get("source_countries") or [])[:5] if isinstance(x, dict) and x.get("country")]
        classifications = [x for x in (stats.get("classifications") or []) if isinstance(x, dict)]
        return GreyNoiseScanContext(
            available=True,
            count=count,
            query=query,
            top_actors=[{"actor": a.get("actor"), "count": a.get("count")} for a in actors],
            top_source_countries=[{"country": c.get("country"), "count": c.get("count")} for c in source_countries],
            classifications=[{"classification": c.get("classification"), "count": c.get("count")} for c in classifications],
            fetched_at=fetched_at,
        )
    except Exception as e:
        logger.warning("CYBER: GreyNoise fetch failed: %s", e)
        return GreyNoiseScanContext(available=False, error=str(e), count=0, fetched_at=fetched_at)


def _get_internetdb_ips() -> List[str]:
    """Conflict-relevant IPs for Shodan InternetDB: from env CYBER_INTERNETDB_IPS (comma-separated)."""
    raw = (os.getenv("CYBER_INTERNETDB_IPS") or "").strip()
    if not raw:
        return []
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
            hosts.append(InternetDbHost(
                ip=data.get("ip", ip),
                ports=data.get("ports") or [],
                vulns=data.get("vulns") or [],
                tags=data.get("tags") or [],
                hostnames=data.get("hostnames") or [],
            ))
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
        out = await analyst_summary(system=system, data=data, max_tokens=256)
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


def run_cyber_agent(conflict: str) -> Dict[str, Any]:
    """
    Run CYBER agent: CISA KEV (cached), threat RSS, OTX, GreyNoise, InternetDB, NVD CVSS.
    Returns structured dict (from CyberAgentResult) for backward compatibility with supervisor.
    """
    otx_key = (os.getenv("OTX_API_KEY") or "").strip()
    greynoise_key = (os.getenv("GREYNOISE_API_KEY") or "").strip()
    internetdb_ips = _get_internetdb_ips()

    async def _no_otx() -> List[OtxPulseEntry]:
        return []

    async def _no_gn() -> GreyNoiseScanContext:
        return GreyNoiseScanContext(available=False, error="GREYNOISE_API_KEY not set", count=0, fetched_at=_utc_now())

    async def _run() -> CyberAgentResult:
        client = get_http_client()
        kev, threat_reports, otx_pulses, greynoise, internet_db = await asyncio.gather(
            _fetch_cisa_kev(client),
            _fetch_threat_rss(client, conflict),
            _fetch_otx_pulses(client, otx_key, conflict) if otx_key else _no_otx(),
            _fetch_greynoise_scan_context(client, greynoise_key) if greynoise_key else _no_gn(),
            _fetch_internetdb(client, internetdb_ips),
        )
        cyber_score = _compute_cyber_score(kev, threat_reports, otx_pulses, greynoise, internet_db)
        rule_summary = _build_summary(kev, threat_reports, otx_pulses, greynoise, internet_db, cyber_score)
        llm_summary = await _generate_haiku_summary_cyber(
            conflict, kev, threat_reports, otx_pulses, greynoise, internet_db, cyber_score,
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

    with traced("analysis.agent.cyber", {"conflict": conflict}):
        try:
            result = run_async(_run())
            return result.model_dump(mode="json")
        except Exception as e:
            logger.exception("CYBER agent run failed")
            fallback = CyberAgentResult(
                cyber_score=25.0,
                cisa_kev=CisaKevResult(total=0, sample=[], error=str(e)),
                summary=f"CYBER error: {e}",
            )
            return fallback.model_dump(mode="json")
