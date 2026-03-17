"""
Compliance Risk Score Engine – computes an ordinal compliance risk level
(LOW / MEDIUM / HIGH / CRITICAL) with optional probability band and documented
driver breakdown.

Inputs:
- Sanctions search results (match levels)
- Geofencing alerts (zone types, count)
- Supply-chain screening (zone hits, suspicious hops)
- AIS anomalies (spoofing, dark activity flags)
- Escalation context (from predictive block)

Rules are documented and auditable. Each contributing factor maps to a risk
increment; the highest single factor sets the floor.

IMPORTANT: Intelligence signals only – not legal advice.
"""

import logging
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

ComplianceLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

DISCLAIMER = "Intelligence signals only – not legal advice. Supports due diligence but does not replace legal review."

# ── Documented scoring rules ─────────────────────────────────────────────────
# Each rule: (condition_description, check_fn, floor_level, score_increment)
# floor_level: if this rule triggers, the score cannot be below this level.
# score_increment: added to the numeric score (0–100 scale) for band calculation.

LEVEL_ORDER: Dict[ComplianceLevel, int] = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2,
    "CRITICAL": 3,
}

BAND_MAP: Dict[ComplianceLevel, Dict[str, float]] = {
    "LOW": {"min": 0.0, "max": 0.15},
    "MEDIUM": {"min": 0.15, "max": 0.40},
    "HIGH": {"min": 0.40, "max": 0.70},
    "CRITICAL": {"min": 0.70, "max": 0.95},
}


def _level_from_numeric(score: float) -> ComplianceLevel:
    if score >= 75:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 25:
        return "MEDIUM"
    return "LOW"


def _max_level(a: ComplianceLevel, b: ComplianceLevel) -> ComplianceLevel:
    return a if LEVEL_ORDER[a] >= LEVEL_ORDER[b] else b


_COMPREHENSIVE_REGIMES: List[Dict[str, Any]] = [
    {
        "keys": ["iran"],
        "level": "HIGH",
        "score": 35,
        "detail": "Iran – comprehensive US (OFAC EO 13846/13902), EU, and UN sanctions regime",
        "programs": "IRAN, IRAN-HR, IRGC, SDGT, NPWMD, ISA",
        "note": "Covers energy, finance, shipping, military, WMD. OFAC Maritime Advisory active.",
    },
    {
        "keys": ["north korea", "dprk"],
        "level": "HIGH",
        "score": 35,
        "detail": "North Korea – comprehensive UN/OFAC sanctions regime",
        "programs": "DPRK, DPRK2, DPRK3, DPRK4",
        "note": "Near-total embargo; all trade restricted.",
    },
    {
        "keys": ["syria"],
        "level": "HIGH",
        "score": 30,
        "detail": "Syria – comprehensive US (Caesar Act) and EU sanctions regime",
        "programs": "SYRIA, SDGT",
        "note": "Broad sanctions covering government, military, energy sector.",
    },
    {
        "keys": ["cuba"],
        "level": "HIGH",
        "score": 30,
        "detail": "Cuba – comprehensive US embargo (OFAC)",
        "programs": "CUBA",
        "note": "Near-total US embargo; limited EU restrictions.",
    },
    {
        "keys": ["russia", "ukraine"],
        "level": "MEDIUM",
        "score": 20,
        "detail": "Russia – extensive sectoral US/EU sanctions (post-2022); partial oil price cap; some waivers active",
        "programs": "RUSSIA-EO14024, RUSSIA-EO14066, UKRAINE-EO13660, SSI",
        "note": "Sectoral (energy, finance, tech); oil price cap with enforcement gaps. Temporary waivers possible.",
    },
]


def compute_compliance_risk(
    sanctions_matches: Optional[List[Dict[str, Any]]] = None,
    geofencing_alerts: Optional[List[Dict[str, Any]]] = None,
    supply_chain_result: Optional[Dict[str, Any]] = None,
    ais_anomalies: Optional[List[Dict[str, Any]]] = None,
    escalation_level: Optional[str] = None,
    conflict: Optional[str] = None,
    ofac_sdn: Optional[Dict[str, Any]] = None,
    eu_sanctions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Compute compliance risk score from all available signals.

    Returns dict with: level, band (min/max), numeric_score, drivers[], disclaimer.
    """
    numeric = 0.0
    floor: ComplianceLevel = "LOW"
    drivers: List[Dict[str, Any]] = []

    # ── Rule 0: Conflict-level sanctions regime ───────────────────────────
    conflict_lower = (conflict or "").lower()
    for regime in _COMPREHENSIVE_REGIMES:
        if any(k in conflict_lower for k in regime["keys"]):
            regime_level: ComplianceLevel = regime["level"]
            floor = _max_level(floor, regime_level)
            numeric += regime["score"]
            drivers.append(
                {
                    "factor": "CONFLICT_SANCTIONS_REGIME",
                    "detail": regime["detail"],
                    "impact": f"{regime_level} floor + {regime['score']}",
                    "rule": f"Active sanctions regime → at least {regime_level}",
                    "programs": regime["programs"],
                    "note": regime["note"],
                }
            )
            break

    # ── Rule 0b: OFAC SDN list hits from DIPLO agent ─────────────────────
    ofac_total = int((ofac_sdn or {}).get("total_matches") or 0)
    if ofac_total > 0:
        if ofac_total > 200:
            floor = _max_level(floor, "HIGH")
            numeric += 20
            drivers.append(
                {
                    "factor": "OFAC_SDN_EXTENSIVE",
                    "detail": f"{ofac_total} OFAC SDN entries match conflict entities",
                    "impact": "HIGH floor + 20",
                    "rule": "Extensive OFAC SDN coverage (>200 entries) → at least HIGH",
                }
            )
        elif ofac_total > 50:
            floor = _max_level(floor, "MEDIUM")
            numeric += 15
            drivers.append(
                {
                    "factor": "OFAC_SDN_SIGNIFICANT",
                    "detail": f"{ofac_total} OFAC SDN entries match conflict entities",
                    "impact": "MEDIUM floor + 15",
                    "rule": "Significant OFAC SDN coverage (>50 entries) → at least MEDIUM",
                }
            )
        else:
            numeric += 10
            drivers.append(
                {
                    "factor": "OFAC_SDN_PRESENT",
                    "detail": f"{ofac_total} OFAC SDN entries match conflict entities",
                    "impact": "+10",
                    "rule": "OFAC SDN matches present → score increment",
                }
            )

    # ── Rule 0c: EU sanctions list hits from DIPLO agent ──────────────────
    eu_mentions = int((eu_sanctions or {}).get("keyword_mentions") or 0)
    if eu_mentions > 0:
        if eu_mentions > 500:
            numeric += 10
            drivers.append(
                {
                    "factor": "EU_SANCTIONS_EXTENSIVE",
                    "detail": f"{eu_mentions} keyword mentions in EU consolidated sanctions list",
                    "impact": "+10",
                    "rule": "Extensive EU sanctions coverage → score increment",
                }
            )
        elif eu_mentions > 50:
            numeric += 5
            drivers.append(
                {
                    "factor": "EU_SANCTIONS_PRESENT",
                    "detail": f"{eu_mentions} keyword mentions in EU consolidated sanctions list",
                    "impact": "+5",
                    "rule": "EU sanctions mentions present → score increment",
                }
            )

    # ── Rule 1: Direct sanctions match → at least HIGH ────────────────────
    if sanctions_matches:
        exact_count = sum(1 for m in sanctions_matches if m.get("match_level") == "EXACT")
        strong_count = sum(1 for m in sanctions_matches if m.get("match_level") == "STRONG_FUZZY")
        weak_count = sum(1 for m in sanctions_matches if m.get("match_level") in ("WEAK_FUZZY", "REVIEW"))

        if exact_count > 0:
            floor = _max_level(floor, "CRITICAL")
            numeric += 40
            drivers.append(
                {
                    "factor": "SANCTIONS_EXACT_MATCH",
                    "detail": f"{exact_count} exact match(es) on sanctions lists",
                    "impact": "CRITICAL floor",
                    "rule": "Direct OFAC/EU/UN list hit → CRITICAL",
                }
            )
        if strong_count > 0:
            floor = _max_level(floor, "HIGH")
            numeric += 20
            drivers.append(
                {
                    "factor": "SANCTIONS_STRONG_FUZZY",
                    "detail": f"{strong_count} strong fuzzy match(es)",
                    "impact": "HIGH floor",
                    "rule": "Strong fuzzy match (>90% similarity) → at least HIGH",
                }
            )
        if weak_count > 0:
            numeric += 10
            drivers.append(
                {
                    "factor": "SANCTIONS_WEAK_FUZZY",
                    "detail": f"{weak_count} weak/review match(es)",
                    "impact": "+10 score",
                    "rule": "Weak fuzzy / review matches → score increment, manual review recommended",
                }
            )

    # ── Rule 2: Geofencing alerts ─────────────────────────────────────────
    if geofencing_alerts:
        sanctions_zone_alerts = [a for a in geofencing_alerts if a.get("zone_type") == "sanctions"]
        embargo_alerts = [a for a in geofencing_alerts if a.get("zone_type") == "embargo"]

        if embargo_alerts:
            floor = _max_level(floor, "HIGH")
            numeric += 25
            drivers.append(
                {
                    "factor": "GEOFENCING_EMBARGO_ZONE",
                    "detail": f"{len(embargo_alerts)} asset(s) in embargo zone(s)",
                    "impact": "HIGH floor + 25",
                    "rule": "Asset in embargo zone → at least HIGH",
                }
            )
        if sanctions_zone_alerts:
            floor = _max_level(floor, "MEDIUM")
            numeric += min(20, len(sanctions_zone_alerts) * 5)
            drivers.append(
                {
                    "factor": "GEOFENCING_SANCTIONS_ZONE",
                    "detail": f"{len(sanctions_zone_alerts)} asset(s) in sanctions zone(s)",
                    "impact": f"MEDIUM floor + {min(20, len(sanctions_zone_alerts) * 5)}",
                    "rule": "Asset in sanctions zone → at least MEDIUM, +5 per alert (max +20)",
                }
            )

    # ── Rule 3: Supply chain ──────────────────────────────────────────────
    if supply_chain_result:
        zone_hits = supply_chain_result.get("zone_hits") or []
        suspicious_hops = supply_chain_result.get("suspicious_hops") or []

        if zone_hits:
            floor = _max_level(floor, "MEDIUM")
            numeric += min(15, len(zone_hits) * 5)
            drivers.append(
                {
                    "factor": "SUPPLY_CHAIN_ZONE_HIT",
                    "detail": f"Route touches {len(zone_hits)} sanctions zone(s)",
                    "impact": f"MEDIUM floor + {min(15, len(zone_hits) * 5)}",
                    "rule": "Trade route through sanctions zone → at least MEDIUM",
                }
            )
        if suspicious_hops:
            numeric += min(15, len(suspicious_hops) * 5)
            drivers.append(
                {
                    "factor": "SUPPLY_CHAIN_SUSPICIOUS_HOP",
                    "detail": f"{len(suspicious_hops)} transit hub(s) flagged by intermediary policy",
                    "impact": f"+{min(15, len(suspicious_hops) * 5)}",
                    "rule": "Transit through documented evasion hub → score increment + review",
                }
            )

    # ── Rule 4: AIS anomalies ─────────────────────────────────────────────
    if ais_anomalies:
        spoofing = [a for a in ais_anomalies if a.get("anomaly_type") == "spoofing"]
        dark = [a for a in ais_anomalies if a.get("anomaly_type") == "dark_activity"]

        if spoofing:
            floor = _max_level(floor, "HIGH")
            numeric += 20
            drivers.append(
                {
                    "factor": "AIS_SPOOFING",
                    "detail": f"{len(spoofing)} vessel(s) with suspected AIS spoofing",
                    "impact": "HIGH floor + 20",
                    "rule": "AIS spoofing indicators → at least HIGH (evasion signal)",
                }
            )
        if dark:
            numeric += min(15, len(dark) * 8)
            drivers.append(
                {
                    "factor": "AIS_DARK_ACTIVITY",
                    "detail": f"{len(dark)} vessel(s) with dark AIS periods in sensitive zones",
                    "impact": f"+{min(15, len(dark) * 8)}",
                    "rule": "AIS dark periods in sanctions/high-risk zones → score increment",
                }
            )

    # ── Rule 5: Escalation context ────────────────────────────────────────
    if escalation_level and escalation_level in ("HIGH", "CRITICAL"):
        numeric += 10
        drivers.append(
            {
                "factor": "ESCALATION_CONTEXT",
                "detail": f"Current escalation level: {escalation_level}",
                "impact": "+10",
                "rule": "HIGH/CRITICAL escalation context → increased compliance sensitivity",
            }
        )

    # ── Final score computation ───────────────────────────────────────────
    numeric = max(0.0, min(100.0, numeric))
    computed_level = _level_from_numeric(numeric)
    final_level = _max_level(floor, computed_level)
    band = BAND_MAP[final_level]

    if not drivers:
        drivers.append(
            {
                "factor": "NO_SIGNALS",
                "detail": "No compliance risk signals detected",
                "impact": "LOW",
                "rule": "No triggers → LOW baseline",
            }
        )

    return {
        "level": final_level,
        "band": band,
        "numeric_score": round(numeric, 1),
        "drivers": drivers,
        "disclaimer": DISCLAIMER,
    }
