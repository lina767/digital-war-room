"""
GreyNoise Emerging Threats Agent – GNQL Stats, CVE Enrichment, Tag Discovery.

Monitors cyber threat landscape for conflict zones across the Middle East and
key state actors (Israel, Iran, USA, UAE, Saudi Arabia, Lebanon, Jordan).
Uses GNQL Stats as primary data source with bidirectional geo-mapping (outbound
scanners from region + inbound scans targeting region infrastructure).

Data flow:
  Scheduler (6h) → GNQL Stats → Tag Taxonomy match → CVE Enrichment → Scoring
  → LLM Summary → SQLite snapshot.
  REST endpoint reads from SQLite only (no live GreyNoise calls in request path).
"""

import asyncio
import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .config import (
    GREYNOISE_API_KEY,
    GREYNOISE_BASE_URL,
    GREYNOISE_SCHEDULER_CONFLICTS,
    GREYNOISE_TIMEOUT,
)
from .utils import ScoreConfidence, utc_now_iso

logger = logging.getLogger(__name__)

# ── GreyNoise API endpoints ───────────────────────────────────────────────

GNQL_STATS_URL = f"{GREYNOISE_BASE_URL}/v2/experimental/gnql/stats"
GNQL_QUERY_URL = f"{GREYNOISE_BASE_URL}/v3/gnql"
CVE_LOOKUP_URL = f"{GREYNOISE_BASE_URL}/v1/cve"
TAGS_API_URL = f"{GREYNOISE_BASE_URL}/v3/tags"
NOISE_CONTEXT_URL = f"{GREYNOISE_BASE_URL}/v2/noise/context"
RIOT_URL = f"{GREYNOISE_BASE_URL}/v3/riot"

MAX_CVE_LOOKUPS = 5

# ── Conflict → Country mapping (for GNQL metadata.country filters) ────────

# Iran-Konflikt: zusätzlich Gulf-Staaten (Hormuz, US-Stützpunkte), Transit- und Konfliktpartner
GREYNOISE_COUNTRY_FILTERS: Dict[str, List[str]] = {
    "iran": [
        "Iran",
        "Iraq",
        "Syria",
        "Lebanon",
        "United Arab Emirates",
        "Bahrain",
        "Qatar",
        "Kuwait",
        "Oman",  # Gulf / Hormuz
        "Saudi Arabia",
        "Jordan",
        "Turkey",  # NATO, Transit, Sanktionsumgehung
        "Pakistan",  # Grenze, Baluchistan, Eskalation
        "Azerbaijan",  # Nordgrenze, Energie
        "Afghanistan",  # Grenze, Taliban, Wasser
    ],
    "israel": ["Israel", "Palestine", "Lebanon"],
    "gaza/israel": ["Israel", "Palestine", "Lebanon"],
    "gaza": ["Israel", "Palestine", "Lebanon"],
    "usa": ["United States", "Canada"],
    "uae": ["United Arab Emirates", "Bahrain", "Qatar"],
    "saudi arabia": ["Saudi Arabia", "Bahrain", "Kuwait"],
    "lebanon": ["Lebanon", "Syria", "Israel"],
    "jordan": ["Jordan", "Syria", "Iraq"],
    "yemen": ["Yemen", "Saudi Arabia"],
    "middle east": [
        "Iran",
        "Iraq",
        "Syria",
        "Lebanon",
        "Israel",
        "Palestine",
        "Yemen",
        "Saudi Arabia",
        "Bahrain",
        "Qatar",
        "United Arab Emirates",
        "Kuwait",
        "Oman",
        "Jordan",
        "United States",
    ],
    "ukraine": ["Ukraine", "Russia"],
}

# Known ASN ranges for critical infrastructure in Middle East (for inbound queries)
MIDDLE_EAST_CRITICAL_ASNS: Dict[str, List[str]] = {
    "iran": ["AS12880", "AS44244", "AS197207", "AS48159"],  # TCI, Irancell, MCI, IRIB
    "iraq": ["AS51684", "AS203214"],
    "israel": ["AS1680", "AS8551", "AS378"],  # Bezeq, Bezeq International, IEC
    "usa": ["AS7922", "AS22773", "AS7018", "AS701"],  # Comcast, Cox, AT&T, Verizon
    "uae": ["AS5384", "AS15802", "AS8966"],  # Etisalat, du, Emirates Telecom
    "saudi arabia": ["AS25019", "AS39891", "AS35753"],  # STC, Mobily, ITC
    "lebanon": ["AS9051", "AS42020"],  # OGERO, LibanCell
    "jordan": ["AS8697", "AS9038"],  # JTC, Orange Jordan
}


# ── Conflict Tag Taxonomy (weight-based scoring) ─────────────────────────

CONFLICT_TAG_TAXONOMY: Dict[str, Dict[str, Dict[str, Any]]] = {
    "iran": {
        "critical_infra": {
            "tags": ["ICS", "SCADA", "Modbus", "DNP3", "BACnet", "S7comm", "EtherNet/IP", "OPC"],
            "weight": 3.0,
        },
        "vpn_exploit": {
            "tags": ["Cisco", "Fortinet", "FortiGate", "Palo Alto", "Pulse Secure", "SonicWall", "Citrix", "VPN"],
            "weight": 2.5,
        },
        "apt_tooling": {
            "tags": ["Cobalt Strike", "Meterpreter", "Brute Ratel", "Sliver", "Havoc"],
            "weight": 2.0,
        },
        "router_exploit": {
            "tags": ["MikroTik", "Netgear", "TP-Link", "D-Link", "Zyxel", "Ubiquiti"],
            "weight": 1.8,
        },
        "generic_scan": {
            "tags": ["Mirai", "SSH Bruteforce", "Telnet", "RDP Bruteforce"],
            "weight": 1.0,
        },
    },
    "israel": {
        "critical_infra": {
            "tags": ["ICS", "SCADA", "Modbus", "DNP3", "BACnet"],
            "weight": 3.0,
        },
        "vpn_exploit": {
            "tags": ["Cisco", "Fortinet", "Palo Alto", "Check Point", "VPN"],
            "weight": 2.5,
        },
        "apt_tooling": {
            "tags": ["Cobalt Strike", "Meterpreter", "Sliver"],
            "weight": 2.0,
        },
        "router_exploit": {
            "tags": ["MikroTik", "Netgear", "TP-Link", "Ubiquiti"],
            "weight": 1.8,
        },
        "generic_scan": {
            "tags": ["Mirai", "SSH Bruteforce", "RDP Bruteforce"],
            "weight": 1.0,
        },
    },
    "gaza/israel": {
        "critical_infra": {
            "tags": ["ICS", "SCADA", "Modbus", "DNP3"],
            "weight": 3.0,
        },
        "vpn_exploit": {
            "tags": ["Cisco", "Fortinet", "Palo Alto", "Check Point", "VPN"],
            "weight": 2.5,
        },
        "apt_tooling": {
            "tags": ["Cobalt Strike", "Meterpreter"],
            "weight": 2.0,
        },
        "generic_scan": {
            "tags": ["Mirai", "SSH Bruteforce"],
            "weight": 1.0,
        },
    },
    "usa": {
        "critical_infra": {
            "tags": ["ICS", "SCADA", "Modbus", "DNP3", "BACnet", "S7comm", "EtherNet/IP", "OPC"],
            "weight": 3.0,
        },
        "vpn_exploit": {
            "tags": [
                "Cisco",
                "Fortinet",
                "FortiGate",
                "Palo Alto",
                "Pulse Secure",
                "SonicWall",
                "Citrix",
                "Ivanti",
                "VPN",
            ],
            "weight": 2.5,
        },
        "apt_tooling": {
            "tags": ["Cobalt Strike", "Meterpreter", "Brute Ratel", "Sliver", "Havoc"],
            "weight": 2.0,
        },
        "cloud_exploit": {
            "tags": ["AWS", "Azure", "Exchange", "Microsoft", "VMware", "Confluence", "Atlassian"],
            "weight": 2.2,
        },
        "router_exploit": {
            "tags": ["MikroTik", "Netgear", "TP-Link", "D-Link", "Zyxel", "Ubiquiti", "Juniper"],
            "weight": 1.8,
        },
        "generic_scan": {
            "tags": ["Mirai", "SSH Bruteforce", "Telnet", "RDP Bruteforce"],
            "weight": 1.0,
        },
    },
    "uae": {
        "critical_infra": {
            "tags": ["ICS", "SCADA", "Modbus", "DNP3", "BACnet", "OPC"],
            "weight": 3.0,
        },
        "vpn_exploit": {
            "tags": ["Cisco", "Fortinet", "FortiGate", "Palo Alto", "SonicWall", "VPN"],
            "weight": 2.5,
        },
        "apt_tooling": {
            "tags": ["Cobalt Strike", "Meterpreter", "Brute Ratel"],
            "weight": 2.0,
        },
        "router_exploit": {
            "tags": ["MikroTik", "Netgear", "TP-Link", "D-Link", "Zyxel"],
            "weight": 1.8,
        },
        "generic_scan": {
            "tags": ["Mirai", "SSH Bruteforce", "Telnet", "RDP Bruteforce"],
            "weight": 1.0,
        },
    },
    "saudi arabia": {
        "critical_infra": {
            "tags": ["ICS", "SCADA", "Modbus", "DNP3", "S7comm", "OPC", "Triton", "TRISIS"],
            "weight": 3.0,
        },
        "vpn_exploit": {
            "tags": ["Cisco", "Fortinet", "FortiGate", "Palo Alto", "SonicWall", "VPN"],
            "weight": 2.5,
        },
        "apt_tooling": {
            "tags": ["Cobalt Strike", "Meterpreter", "Shamoon", "Brute Ratel"],
            "weight": 2.5,
        },
        "router_exploit": {
            "tags": ["MikroTik", "Netgear", "TP-Link", "D-Link", "Zyxel"],
            "weight": 1.8,
        },
        "generic_scan": {
            "tags": ["Mirai", "SSH Bruteforce", "Telnet", "RDP Bruteforce"],
            "weight": 1.0,
        },
    },
    "jordan": {
        "critical_infra": {
            "tags": ["ICS", "SCADA", "Modbus", "DNP3"],
            "weight": 3.0,
        },
        "vpn_exploit": {
            "tags": ["Cisco", "Fortinet", "Palo Alto", "VPN"],
            "weight": 2.5,
        },
        "apt_tooling": {
            "tags": ["Cobalt Strike", "Meterpreter"],
            "weight": 2.0,
        },
        "router_exploit": {
            "tags": ["MikroTik", "Netgear", "TP-Link"],
            "weight": 1.8,
        },
        "generic_scan": {
            "tags": ["Mirai", "SSH Bruteforce", "RDP Bruteforce"],
            "weight": 1.0,
        },
    },
    "ukraine": {
        "wiper_related": {
            "tags": ["Wiper", "Destructive", "WhisperGate", "HermeticWiper", "CaddyWiper"],
            "weight": 3.0,
        },
        "critical_infra": {
            "tags": ["ICS", "SCADA", "Industroyer", "Modbus", "DNP3"],
            "weight": 3.0,
        },
        "ddos_botnet": {
            "tags": ["Mirai", "DDoS", "Moobot"],
            "weight": 2.0,
        },
        "apt_tooling": {
            "tags": ["Cobalt Strike", "Brute Ratel"],
            "weight": 2.0,
        },
    },
}

# Fallback taxonomy for conflicts not explicitly mapped
CONFLICT_TAG_TAXONOMY["gaza"] = CONFLICT_TAG_TAXONOMY["gaza/israel"]
CONFLICT_TAG_TAXONOMY["lebanon"] = CONFLICT_TAG_TAXONOMY["iran"]
CONFLICT_TAG_TAXONOMY["yemen"] = CONFLICT_TAG_TAXONOMY["iran"]
CONFLICT_TAG_TAXONOMY["middle east"] = CONFLICT_TAG_TAXONOMY["iran"]


def _get_taxonomy(conflict: str) -> Dict[str, Dict[str, Any]]:
    return CONFLICT_TAG_TAXONOMY.get(conflict.lower(), CONFLICT_TAG_TAXONOMY.get("iran", {}))


def _get_countries(conflict: str) -> List[str]:
    return GREYNOISE_COUNTRY_FILTERS.get(conflict.lower(), GREYNOISE_COUNTRY_FILTERS.get("middle east", ["Iran"]))


# ── Pydantic result models ───────────────────────────────────────────────


class EmergingThreat(BaseModel):
    tag: str = ""
    category: str = ""
    direction: str = "outbound"  # "inbound" | "outbound"
    scan_volume: int = 0
    scan_volume_change: Optional[float] = None
    priority: str = "medium"  # "low" | "medium" | "high"
    cve_id: Optional[str] = None
    cvss_score: Optional[float] = None
    products: Optional[List[str]] = None
    source_countries: List[str] = Field(default_factory=list)
    destination_countries: List[str] = Field(default_factory=list)
    weight: float = 1.0


class GreynoiseResult(BaseModel):
    conflict: str
    emerging_threats: List[EmergingThreat] = Field(default_factory=list)
    greynoise_score: float = 0.0
    absolute_score: float = 0.0
    delta_score: float = 0.0
    trend: str = "stable"  # "rising" | "stable" | "falling"
    alerts: List[str] = Field(default_factory=list)
    summary: str = ""
    score_confidence: ScoreConfidence = Field(default_factory=ScoreConfidence)
    fetched_at: str = Field(default_factory=utc_now_iso)
    outbound_count: int = 0
    inbound_count: int = 0
    top_tags_outbound: List[Dict[str, Any]] = Field(default_factory=list)
    top_tags_inbound: List[Dict[str, Any]] = Field(default_factory=list)
    pending_tags: List[str] = Field(default_factory=list)


# ── SQLite persistence ───────────────────────────────────────────────────

DB_PATH = Path(
    os.getenv("GREYNOISE_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "greynoise_snapshots.db")
)


def _ensure_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS greynoise_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflict TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            greynoise_score REAL NOT NULL DEFAULT 0,
            absolute_score REAL NOT NULL DEFAULT 0,
            total_events INTEGER NOT NULL DEFAULT 0,
            data_json TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_gn_conflict_ts
        ON greynoise_snapshots (conflict, timestamp DESC)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS greynoise_ips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflict TEXT NOT NULL,
            direction TEXT NOT NULL,
            ip TEXT NOT NULL,
            classification TEXT,
            tags_json TEXT,
            metadata_json TEXT,
            snapshot_timestamp TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_gn_ips_conflict_ts
        ON greynoise_ips (conflict, snapshot_timestamp DESC)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS greynoise_pending_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_name TEXT NOT NULL,
            conflict TEXT NOT NULL,
            matched_category TEXT,
            discovered_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        )
    """)
    conn.commit()
    return conn


def save_snapshot(result: GreynoiseResult) -> None:
    conn = _ensure_db()
    try:
        total_events = result.outbound_count + result.inbound_count
        conn.execute(
            "INSERT INTO greynoise_snapshots (conflict, timestamp, greynoise_score, absolute_score, total_events, data_json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                result.conflict,
                result.fetched_at,
                result.greynoise_score,
                result.absolute_score,
                total_events,
                json.dumps(result.model_dump(mode="json")),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_snapshot(conflict: str) -> Optional[Dict[str, Any]]:
    conn = _ensure_db()
    try:
        row = conn.execute(
            "SELECT data_json FROM greynoise_snapshots WHERE conflict = ? ORDER BY timestamp DESC LIMIT 1",
            (conflict,),
        ).fetchone()
        if row:
            return json.loads(row[0])
        return None
    finally:
        conn.close()


def get_trend_data(conflict: str, days: int = 7) -> List[Dict[str, Any]]:
    conn = _ensure_db()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = conn.execute(
            "SELECT timestamp, greynoise_score, absolute_score, total_events FROM greynoise_snapshots WHERE conflict = ? AND timestamp >= ? ORDER BY timestamp ASC",
            (conflict, cutoff),
        ).fetchall()
        return [
            {"timestamp": r[0], "greynoise_score": r[1], "absolute_score": r[2], "total_events": r[3]} for r in rows
        ]
    finally:
        conn.close()


def _get_historical_avg(conflict: str, days: int = 7) -> Optional[float]:
    conn = _ensure_db()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        row = conn.execute(
            "SELECT AVG(total_events) FROM greynoise_snapshots WHERE conflict = ? AND timestamp >= ?",
            (conflict, cutoff),
        ).fetchone()
        if row and row[0] is not None:
            return float(row[0])
        return None
    finally:
        conn.close()


# ── GreyNoise API helpers ────────────────────────────────────────────────


def _gn_headers() -> Dict[str, str]:
    return {
        "key": GREYNOISE_API_KEY or "",
        "Accept": "application/json",
        "User-Agent": "DigitalWarRoom/1.0",
    }


async def _fetch_gnql_stats(client: Any, query: str) -> Dict[str, Any]:
    try:
        resp = await client.get(
            GNQL_STATS_URL,
            params={"query": query, "count": 25},
            headers=_gn_headers(),
            timeout=GREYNOISE_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("GreyNoise GNQL stats returned %s for query: %s", resp.status_code, query)
            return {"count": 0, "stats": {}}
        return resp.json()
    except Exception as e:
        logger.warning("GreyNoise GNQL stats failed: %s", e)
        return {"count": 0, "stats": {}, "error": str(e)}


async def _fetch_cve_details(client: Any, cve_id: str) -> Optional[Dict[str, Any]]:
    try:
        resp = await client.get(
            f"{CVE_LOOKUP_URL}/{cve_id}",
            headers=_gn_headers(),
            timeout=GREYNOISE_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception as e:
        logger.debug("GreyNoise CVE lookup %s failed: %s", cve_id, e)
        return None


async def _fetch_tags_list(client: Any) -> List[Dict[str, Any]]:
    try:
        resp = await client.get(
            TAGS_API_URL,
            headers=_gn_headers(),
            timeout=GREYNOISE_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data if isinstance(data, list) else data.get("items", data.get("tags", []))
    except Exception as e:
        logger.debug("GreyNoise tags list fetch failed: %s", e)
        return []


async def _fetch_riot(client: Any, ip: str) -> Optional[Dict[str, Any]]:
    """
    RIOT (Rule It Out): check if IP is known benign (Shodan, Censys, Google, etc.).
    Returns dict with riot=True and name/category if benign, else None or riot=False.
    Used to exclude false positives from scoring.
    """
    if not ip or not ip.strip():
        return None
    try:
        url = f"{RIOT_URL}/{ip.strip()}"
        resp = await client.get(url, headers=_gn_headers(), timeout=GREYNOISE_TIMEOUT)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, dict):
            return None
        # Response may have: riot=True, name, category, description, etc.
        return data
    except Exception as e:
        logger.debug("GreyNoise RIOT check %s failed: %s", ip, e)
        return None


async def _fetch_ip_context(client: Any, ip: str) -> Optional[Dict[str, Any]]:
    """
    Full context for a single IP (v2/noise/context/{ip}): OS, ports, tags, CVEs, actor, ASN, RDNS.
    Used to enrich top IPs from GNQL for detail view.
    """
    if not ip or not ip.strip():
        return None
    try:
        url = f"{NOISE_CONTEXT_URL}/{ip.strip()}"
        resp = await client.get(url, headers=_gn_headers(), timeout=GREYNOISE_TIMEOUT)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception as e:
        logger.debug("GreyNoise IP context %s failed: %s", ip, e)
        return None


async def _fetch_gnql_results(client: Any, query: str, size: int = 100) -> List[Dict[str, Any]]:
    """
    Full GNQL query (v3/gnql) – returns IP records with metadata/tags/classification.
    Used to get concrete IPs (e.g. "which IPs are scanning Iranian infrastructure").
    """
    try:
        resp = await client.get(
            GNQL_QUERY_URL,
            params={"query": query, "size": min(size, 500)},
            headers=_gn_headers(),
            timeout=GREYNOISE_TIMEOUT,
        )
        if resp.status_code not in (200, 206):
            logger.warning("GreyNoise GNQL query returned %s for query: %s", resp.status_code, query[:80])
            return []
        data = resp.json()
        items = data.get("data") or data.get("results") or []
        if not isinstance(items, list):
            return []
        return items[:size]
    except Exception as e:
        logger.warning("GreyNoise GNQL query failed: %s", e)
        return []


def _save_gnql_ips(conflict: str, direction: str, ip_records: List[Dict[str, Any]], snapshot_timestamp: str) -> None:
    """Persist top IPs from GNQL query to greynoise_ips table."""
    if not ip_records:
        return
    conn = _ensure_db()
    now = utc_now_iso()
    try:
        for rec in ip_records[:50]:
            ip = rec.get("ip") or rec.get("address")
            if not ip:
                continue
            classification = rec.get("classification") or rec.get("trust_level") or ""
            tags = rec.get("tags") or []
            metadata = rec.get("metadata") or {}
            conn.execute(
                """INSERT INTO greynoise_ips (conflict, direction, ip, classification, tags_json, metadata_json, snapshot_timestamp, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    conflict,
                    direction,
                    ip,
                    classification,
                    json.dumps(tags) if isinstance(tags, list) else json.dumps([]),
                    json.dumps(metadata) if isinstance(metadata, dict) else "{}",
                    snapshot_timestamp,
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_greynoise_context_for_cyber(conflict: str) -> Optional[Dict[str, Any]]:
    """
    Return GreyNoise scan context from latest snapshot for use by cyber_agent.
    Avoids duplicate API calls; returns None if no snapshot for conflict.
    """
    snapshot = get_latest_snapshot(conflict)
    if not snapshot:
        return None
    out = int(snapshot.get("outbound_count") or 0)
    inc = int(snapshot.get("inbound_count") or 0)
    count = out + inc
    top_out = snapshot.get("top_tags_outbound") or []
    top_in = snapshot.get("top_tags_inbound") or []
    top_actors = []
    for t in (top_out + top_in)[:10]:
        if isinstance(t, dict) and (t.get("tag") or t.get("count")):
            top_actors.append({"actor": t.get("tag") or t.get("name"), "count": t.get("count", 0)})
    return {
        "available": True,
        "count": count,
        "query": f"conflict:{conflict}",
        "top_actors": top_actors,
        "top_source_countries": [],
        "classifications": [],
        "error": None,
        "fetched_at": snapshot.get("fetched_at") or utc_now_iso(),
    }


def get_latest_ips(conflict: str, limit: int = 30) -> List[Dict[str, Any]]:
    """Return latest stored IP records for conflict (from most recent snapshot)."""
    conn = _ensure_db()
    try:
        row = conn.execute(
            "SELECT snapshot_timestamp FROM greynoise_ips WHERE conflict = ? ORDER BY snapshot_timestamp DESC LIMIT 1",
            (conflict,),
        ).fetchone()
        if not row:
            return []
        ts = row[0]
        rows = conn.execute(
            """SELECT ip, direction, classification, tags_json, metadata_json FROM greynoise_ips
               WHERE conflict = ? AND snapshot_timestamp = ? ORDER BY id LIMIT ?""",
            (conflict, ts, limit),
        ).fetchall()
        result = []
        for r in rows:
            ip, direction, classification, tags_json, metadata_json = r
            rec = {"ip": ip, "direction": direction, "classification": classification or ""}
            try:
                if tags_json:
                    rec["tags"] = json.loads(tags_json)
                if metadata_json:
                    rec["metadata"] = json.loads(metadata_json)
            except (json.JSONDecodeError, TypeError):
                pass
            result.append(rec)
        return result
    finally:
        conn.close()


# ── Core pipeline ────────────────────────────────────────────────────────


def _match_tag_to_taxonomy(tag_name: str, taxonomy: Dict[str, Dict[str, Any]]) -> Tuple[Optional[str], float]:
    """Match a GreyNoise tag name against the taxonomy. Returns (category, weight) or (None, 1.0)."""
    tag_lower = tag_name.lower()
    for category, config in taxonomy.items():
        for keyword in config.get("tags", []):
            if keyword.lower() in tag_lower:
                return category, float(config.get("weight", 1.0))
    return None, 1.0


_CVE_PATTERN = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)


def _extract_cves_from_tags(tags: List[Dict[str, Any]]) -> List[str]:
    """Extract CVE IDs from tag names/descriptions."""
    cves = set()
    for t in tags:
        tag_str = str(t.get("tag") or t.get("name") or "")
        for match in _CVE_PATTERN.findall(tag_str):
            cves.add(match.upper())
    return sorted(cves)[:MAX_CVE_LOOKUPS]


def _build_gnql_query(
    countries: List[str],
    direction: str = "outbound",
    time_window: str = "1d",
    conflict: Optional[str] = None,
) -> str:
    """Build GNQL query; optionally add critical-infrastructure ASN filters from MIDDLE_EAST_CRITICAL_ASNS."""
    asns = (MIDDLE_EAST_CRITICAL_ASNS.get((conflict or "").lower(), []) or [])[:10]
    asn_clause = " OR ".join(f"metadata.asn:{a}" for a in asns) if asns else ""
    dest_asn_clause = " OR ".join(f"metadata.destination_asns:{a}" for a in asns) if asns else ""

    if direction == "outbound":
        country_clause = " OR ".join(f"metadata.country:{c}" for c in countries)
        if len(countries) > 1:
            country_clause = f"({country_clause})"
        if asn_clause:
            country_clause = f"({country_clause} OR {asn_clause})"
        return f"classification:malicious {country_clause} last_seen:{time_window}"
    else:
        country_clause = " OR ".join(f"metadata.destination_country:{c}" for c in countries)
        if len(countries) > 1:
            country_clause = f"({country_clause})"
        if dest_asn_clause:
            country_clause = f"({country_clause} OR {dest_asn_clause})"
        return f"classification:malicious {country_clause} last_seen:{time_window}"


def _stats_to_threats(
    stats_data: Dict[str, Any],
    direction: str,
    taxonomy: Dict[str, Dict[str, Any]],
    countries: List[str],
) -> Tuple[List[EmergingThreat], List[Dict[str, Any]]]:
    """Convert GNQL stats response to EmergingThreat list. Returns (threats, raw_top_tags)."""
    stats = stats_data.get("stats", {})
    raw_tags = stats.get("tags") or stats.get("actors") or []
    if not isinstance(raw_tags, list):
        raw_tags = []

    top_tags = []
    threats: List[EmergingThreat] = []

    for t in raw_tags[:25]:
        if not isinstance(t, dict):
            continue
        tag_name = str(t.get("tag") or t.get("actor") or t.get("name") or "")
        count = int(t.get("count", 0))
        if not tag_name or count == 0:
            continue

        top_tags.append({"tag": tag_name, "count": count})
        category, weight = _match_tag_to_taxonomy(tag_name, taxonomy)

        if weight >= 2.0:
            priority = "high"
        elif weight >= 1.5:
            priority = "medium"
        else:
            priority = "low"

        cve_matches = _CVE_PATTERN.findall(tag_name)
        cve_id = cve_matches[0].upper() if cve_matches else None

        threats.append(
            EmergingThreat(
                tag=tag_name,
                category=category or "uncategorized",
                direction=direction,
                scan_volume=count,
                priority=priority,
                cve_id=cve_id,
                weight=weight,
                source_countries=countries if direction == "outbound" else [],
                destination_countries=countries if direction == "inbound" else [],
            )
        )

    return threats, top_tags


def _compute_absolute_score(threats: List[EmergingThreat], outbound_count: int, inbound_count: int) -> float:
    base = 20.0

    for t in threats:
        contribution = t.weight * min(t.scan_volume / 500, 3.0)
        if t.direction == "inbound":
            contribution *= 1.5
        base += contribution

    if inbound_count > 100:
        base += 10
    if outbound_count > 1000:
        base += 5

    high_threats = sum(1 for t in threats if t.priority == "high")
    base += high_threats * 5

    return max(0.0, min(100.0, base))


def _compute_delta_score(current_total: int, avg_7d: Optional[float]) -> float:
    if avg_7d is None or avg_7d <= 0:
        return 0.0
    ratio = current_total / avg_7d
    return max(0.0, min(100.0, (ratio - 1.0) * 50.0))


def _derive_trend(delta_score: float) -> str:
    if delta_score > 25:
        return "rising"
    if delta_score < -10:
        return "falling"
    return "stable"


def _cvss_score_bonus(cvss: Optional[float]) -> float:
    if cvss is None:
        return 0.0
    if cvss >= 9.0:
        return 20.0
    if cvss >= 7.0:
        return 10.0
    return 5.0


async def _enrich_cves(client: Any, threats: List[EmergingThreat]) -> float:
    """Enrich threats with CVE data and return total CVSS bonus for scoring."""
    cve_ids = list({t.cve_id for t in threats if t.cve_id})[:MAX_CVE_LOOKUPS]
    if not cve_ids:
        return 0.0

    bonus = 0.0
    cve_cache: Dict[str, Dict[str, Any]] = {}

    for cve_id in cve_ids:
        data = await _fetch_cve_details(client, cve_id)
        if data:
            cve_cache[cve_id] = data

    for t in threats:
        if not t.cve_id or t.cve_id not in cve_cache:
            continue
        cve_data = cve_cache[t.cve_id]
        cvss = None
        products = []
        if isinstance(cve_data, dict):
            cvss = cve_data.get("cvss_score") or cve_data.get("cvss3_score")
            if cvss is not None:
                try:
                    cvss = float(cvss)
                except (TypeError, ValueError):
                    cvss = None
            prods = cve_data.get("vendors") or cve_data.get("products") or []
            if isinstance(prods, list):
                products = [str(p) for p in prods[:5]]
        t.cvss_score = cvss
        t.products = products if products else None
        bonus += _cvss_score_bonus(cvss)

    return min(40.0, bonus)


def _generate_alerts(
    threats: List[EmergingThreat], outbound_count: int, inbound_count: int, delta_score: float
) -> List[str]:
    alerts: List[str] = []

    high_inbound = [t for t in threats if t.direction == "inbound" and t.priority == "high"]
    if high_inbound:
        tags = ", ".join(t.tag for t in high_inbound[:3])
        alerts.append(f"HIGH-PRIORITY inbound scans targeting region infrastructure: {tags}")

    ics_threats = [t for t in threats if t.category == "critical_infra"]
    if ics_threats:
        alerts.append(f"{len(ics_threats)} ICS/SCADA-related scanning pattern(s) detected")

    if delta_score > 50:
        alerts.append(f"Significant scan volume increase: {delta_score:.0f}% above 7-day baseline")

    high_cvss = [t for t in threats if t.cvss_score and t.cvss_score >= 9.0]
    if high_cvss:
        cves = ", ".join(t.cve_id or t.tag for t in high_cvss[:3])
        alerts.append(f"Critical CVEs actively scanned: {cves}")

    if outbound_count + inbound_count > 5000:
        alerts.append(f"High total scan volume: {outbound_count + inbound_count:,} malicious IPs")

    return alerts


async def _generate_llm_summary(conflict: str, result: GreynoiseResult) -> str:
    """Generate analyst-style summary via Haiku (optional, falls back to rule-based). Uses haiku_service for budget tracking."""
    try:
        from services.haiku_service import analyst_summary

        top_threats = [
            {
                "tag": t.tag,
                "category": t.category,
                "direction": t.direction,
                "volume": t.scan_volume,
                "priority": t.priority,
                "cve": t.cve_id,
                "cvss": t.cvss_score,
            }
            for t in sorted(result.emerging_threats, key=lambda x: x.weight * x.scan_volume, reverse=True)[:5]
        ]
        prompt_data = json.dumps(
            {
                "conflict": conflict,
                "greynoise_score": result.greynoise_score,
                "trend": result.trend,
                "outbound_count": result.outbound_count,
                "inbound_count": result.inbound_count,
                "top_threats": top_threats,
                "alerts": result.alerts,
            },
            indent=2,
        )
        system = (
            "You are a cyber-threat analyst for conflict zones. Summarize the following "
            "GreyNoise Emerging Threats data in 2-3 sentences. Focus on the most critical "
            "signals and what they mean for the security situation. Be concise and analytical. "
            "Write in English."
        )
        summary = await analyst_summary(system=system, data=prompt_data, max_tokens=300)
        return summary.strip() if summary else ""
    except Exception as e:
        logger.debug("GreyNoise LLM summary failed, using rule-based: %s", e)
        return ""


def _rule_based_summary(result: GreynoiseResult) -> str:
    parts = [f"GreyNoise Emerging Threats ({result.conflict}):"]
    parts.append(f"{result.outbound_count} outbound, {result.inbound_count} inbound malicious IPs.")

    high = [t for t in result.emerging_threats if t.priority == "high"]
    if high:
        parts.append(f"{len(high)} high-priority threat(s): {', '.join(t.tag for t in high[:3])}.")

    if result.trend == "rising":
        parts.append("Scan volume is rising above 7-day baseline.")
    elif result.trend == "falling":
        parts.append("Scan volume is below 7-day baseline.")

    parts.append(f"Score: {result.greynoise_score:.0f}/100.")
    return " ".join(parts)


# ── Tag Discovery ────────────────────────────────────────────────────────

DISCOVERY_KEYWORDS = [
    "iran",
    "iranian",
    "irgc",
    "apt33",
    "apt34",
    "apt35",
    "muddywater",
    "charming kitten",
    "oilrig",
    "israel",
    "israeli",
    "gaza",
    "check point",
    "usa",
    "united states",
    "apt28",
    "apt29",
    "lazarus",
    "volt typhoon",
    "salt typhoon",
    "sandworm",
    "uae",
    "emirates",
    "abu dhabi",
    "saudi",
    "aramco",
    "shamoon",
    "triton",
    "trisis",
    "lebanon",
    "hezbollah",
    "jordan",
    "jordanian",
    "hamas",
    "houthi",
    "yemen",
    "ics",
    "scada",
    "modbus",
    "dnp3",
    "plc",
    "cobalt strike",
    "meterpreter",
    "brute ratel",
    "sliver",
    "havoc",
    "ukraine",
    "gamaredon",
    "fortinet",
    "cisco",
    "palo alto",
    "ivanti",
    "vpn",
    "wiper",
    "destructive",
    "exchange",
    "vmware",
    "confluence",
]


async def _run_tag_discovery(client: Any) -> List[str]:
    """Discover new tags from GreyNoise Tags API that match conflict keywords."""
    tags = await _fetch_tags_list(client)
    discovered = []
    for t in tags:
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or t.get("tag") or "").lower()
        desc = str(t.get("description") or "").lower()
        combined = name + " " + desc
        for kw in DISCOVERY_KEYWORDS:
            if kw in combined:
                discovered.append(str(t.get("name") or t.get("tag") or ""))
                break
    return discovered[:50]


def _save_pending_tags(tags: List[str], conflict: str) -> None:
    if not tags:
        return
    conn = _ensure_db()
    try:
        now = utc_now_iso()
        for tag in tags:
            exists = conn.execute(
                "SELECT 1 FROM greynoise_pending_tags WHERE tag_name = ? AND conflict = ?",
                (tag, conflict),
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO greynoise_pending_tags (tag_name, conflict, discovered_at, status) VALUES (?, ?, ?, 'pending')",
                    (tag, conflict, now),
                )
        conn.commit()
    finally:
        conn.close()


# ── Main pipeline ────────────────────────────────────────────────────────


async def _run_greynoise_pipeline(conflict: str) -> GreynoiseResult:
    """Full pipeline: GNQL Stats (outbound+inbound) → taxonomy → CVE enrichment → scoring → summary."""
    import httpx

    if not GREYNOISE_API_KEY:
        return GreynoiseResult(
            conflict=conflict,
            summary="GreyNoise API key not configured.",
            score_confidence=ScoreConfidence(level="low", sources_missing=["greynoise"]),
        )

    countries = _get_countries(conflict)
    taxonomy = _get_taxonomy(conflict)

    async with httpx.AsyncClient(timeout=GREYNOISE_TIMEOUT) as client:
        # Parallel GNQL Stats: outbound + inbound
        outbound_query = _build_gnql_query(countries, "outbound", "1d", conflict=conflict)
        inbound_query = _build_gnql_query(countries, "inbound", "1d", conflict=conflict)

        outbound_data, inbound_data = await asyncio.gather(
            _fetch_gnql_stats(client, outbound_query),
            _fetch_gnql_stats(client, inbound_query),
        )

        outbound_count = int(outbound_data.get("count", 0))
        inbound_count = int(inbound_data.get("count", 0))

        # Full GNQL query: fetch concrete IP records for detail view (stored in greynoise_ips)
        outbound_ips = await _fetch_gnql_results(client, outbound_query, size=50)
        inbound_ips = await _fetch_gnql_results(client, inbound_query, size=50)

        # Enrich top 5 outbound + top 5 inbound IPs with full context (v2/noise/context/{ip})
        for rec in outbound_ips[:5]:
            ip = rec.get("ip") or rec.get("address")
            if ip:
                ctx = await _fetch_ip_context(client, ip)
                if ctx:
                    rec["metadata"] = dict(rec.get("metadata") or {})
                    rec["metadata"]["ip_context"] = ctx
        for rec in inbound_ips[:5]:
            ip = rec.get("ip") or rec.get("address")
            if ip:
                ctx = await _fetch_ip_context(client, ip)
                if ctx:
                    rec["metadata"] = dict(rec.get("metadata") or {})
                    rec["metadata"]["ip_context"] = ctx

        # RIOT check: sample top IPs; if benign (Shodan/Censys/etc.), reduce count for scoring
        riot_sample_size = 10
        outbound_riot_benign = 0
        for rec in outbound_ips[:riot_sample_size]:
            ip = rec.get("ip") or rec.get("address")
            if ip:
                riot_data = await _fetch_riot(client, ip)
                if riot_data and (riot_data.get("riot") is True or riot_data.get("trust_level") == "benign"):
                    outbound_riot_benign += 1
        inbound_riot_benign = 0
        for rec in inbound_ips[:riot_sample_size]:
            ip = rec.get("ip") or rec.get("address")
            if ip:
                riot_data = await _fetch_riot(client, ip)
                if riot_data and (riot_data.get("riot") is True or riot_data.get("trust_level") == "benign"):
                    inbound_riot_benign += 1
        outbound_sample_n = min(riot_sample_size, len(outbound_ips)) or 1
        inbound_sample_n = min(riot_sample_size, len(inbound_ips)) or 1
        outbound_riot_ratio = outbound_riot_benign / outbound_sample_n
        inbound_riot_ratio = inbound_riot_benign / inbound_sample_n
        # Discount count by up to 50% based on RIOT benign fraction in sample
        outbound_count_adj = int(outbound_count * (1.0 - 0.5 * outbound_riot_ratio))
        inbound_count_adj = int(inbound_count * (1.0 - 0.5 * inbound_riot_ratio))
        outbound_count_adj = max(0, outbound_count_adj)
        inbound_count_adj = max(0, inbound_count_adj)

        outbound_threats, top_tags_out = _stats_to_threats(outbound_data, "outbound", taxonomy, countries)
        inbound_threats, top_tags_in = _stats_to_threats(inbound_data, "inbound", taxonomy, countries)

        all_threats = outbound_threats + inbound_threats
        all_threats.sort(key=lambda t: t.weight * t.scan_volume, reverse=True)

        # CVE enrichment
        cvss_bonus = await _enrich_cves(client, all_threats)

        # Compute scores (use RIOT-adjusted counts to reduce false-positive inflation)
        absolute = _compute_absolute_score(all_threats, outbound_count_adj, inbound_count_adj) + cvss_bonus
        absolute = min(100.0, absolute)

        avg_7d = _get_historical_avg(conflict, days=7)
        current_total = outbound_count + inbound_count
        delta = _compute_delta_score(current_total, avg_7d)
        trend = _derive_trend(delta)

        final_score = 0.6 * absolute + 0.4 * delta
        final_score = max(0.0, min(100.0, final_score))

        alerts = _generate_alerts(all_threats, outbound_count, inbound_count, delta)

        # Confidence
        sources_ok = []
        sources_missing = []
        if outbound_count > 0 or outbound_data.get("stats"):
            sources_ok.append("gnql_outbound")
        else:
            sources_missing.append("gnql_outbound")
        if inbound_count > 0 or inbound_data.get("stats"):
            sources_ok.append("gnql_inbound")
        else:
            sources_missing.append("gnql_inbound")
        if avg_7d is not None:
            sources_ok.append("historical_baseline")
        else:
            sources_missing.append("historical_baseline")

        result = GreynoiseResult(
            conflict=conflict,
            emerging_threats=all_threats[:30],
            greynoise_score=round(final_score, 1),
            absolute_score=round(absolute, 1),
            delta_score=round(delta, 1),
            trend=trend,
            alerts=alerts,
            summary="",
            score_confidence=ScoreConfidence(
                level="high" if len(sources_ok) >= 2 else "low",
                sources_ok=sources_ok,
                sources_missing=sources_missing,
            ),
            outbound_count=outbound_count,
            inbound_count=inbound_count,
            top_tags_outbound=top_tags_out[:10],
            top_tags_inbound=top_tags_in[:10],
        )

        # LLM summary (non-blocking fallback to rule-based)
        llm_summary = await _generate_llm_summary(conflict, result)
        result.summary = llm_summary if llm_summary else _rule_based_summary(result)

        # Persist GNQL IP results for detail view (greynoise_ips table)
        _save_gnql_ips(conflict, "outbound", outbound_ips, result.fetched_at)
        _save_gnql_ips(conflict, "inbound", inbound_ips, result.fetched_at)

        return result


def run_greynoise_agent(conflict: str) -> Dict[str, Any]:
    """Synchronous entry point: run pipeline and persist snapshot."""
    from .utils import run_async

    try:
        result = run_async(_run_greynoise_pipeline(conflict))
        save_snapshot(result)
        return result.model_dump(mode="json")
    except Exception as e:
        logger.exception("GreyNoise agent failed for %s: %s", conflict, e)
        fallback = GreynoiseResult(
            conflict=conflict,
            summary=f"GreyNoise pipeline error: {e}",
            score_confidence=ScoreConfidence(level="low", sources_missing=["greynoise"]),
        )
        return fallback.model_dump(mode="json")


# ── Scheduler ────────────────────────────────────────────────────────────


async def run_greynoise_scheduler_cycle() -> None:
    """Run one scheduler cycle: pipeline for all configured conflicts."""

    for conflict in GREYNOISE_SCHEDULER_CONFLICTS:
        try:
            logger.info("GreyNoise scheduler: running pipeline for %s", conflict)
            result = await _run_greynoise_pipeline(conflict)
            save_snapshot(result)
            logger.info("GreyNoise scheduler: %s done (score=%.1f)", conflict, result.greynoise_score)
        except Exception as e:
            logger.exception("GreyNoise scheduler: pipeline failed for %s: %s", conflict, e)
        await asyncio.sleep(2)


async def run_tag_discovery_cycle() -> None:
    """Run tag discovery for all conflicts (once daily)."""
    import httpx

    if not GREYNOISE_API_KEY:
        return

    async with httpx.AsyncClient(timeout=GREYNOISE_TIMEOUT) as client:
        discovered = await _run_tag_discovery(client)
        if discovered:
            for conflict in GREYNOISE_SCHEDULER_CONFLICTS:
                _save_pending_tags(discovered, conflict)
            logger.info("GreyNoise tag discovery: found %d matching tags", len(discovered))
