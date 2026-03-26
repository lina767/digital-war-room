"""
Typed per-agent Pydantic result contracts.

Each agent has a dedicated result model inheriting from BaseAgentResult.
Central definition ensures type safety across DAG nodes, division heads,
and the CEO synthesis layer.

Agent run_*_agent() functions return Dict[str, Any] shaped like the corresponding
*Result model (plus _meta). Use get_agent_fallback(name) for a valid default dict.

Data-quality fields (BaseAgentResult / dq_contract)
----------------------------------------------------
``dq_confidence`` (0–100), ``data_freshness``, ``source_count``, ``fallback_used``,
``error_summary``, ``provenance_refs`` — see ``agents/dq_contract.py`` for semantics.
Use ``sync_agent_quality_from_meta()`` to populate from ``_meta`` when building dicts.
"""

from typing import Any, Dict, List, Optional

from pydantic import Field

from .base import BaseAgentResult

# ---------------------------------------------------------------------------
# ENERGY
# ---------------------------------------------------------------------------


class EnergyResult(BaseAgentResult):
    schema_version: int = 1
    energy_score: float = 0.0
    agsi_storage: Dict[str, Any] = Field(default_factory=lambda: {"full": []})
    commodities: List[Dict[str, Any]] = Field(default_factory=list)
    food_commodities: List[Dict[str, Any]] = Field(default_factory=list)
    fao_fpi: Dict[str, Any] = Field(default_factory=dict)
    fertilizer: Dict[str, Any] = Field(default_factory=dict)
    world_bank_country: Dict[str, Any] = Field(
        default_factory=dict,
        description="World Bank Open Data country snapshot (GDP, CPI, electricity access, poverty headcount).",
    )
    food_security_risk: float = 0.0
    global_impact_note: Optional[str] = None


# ---------------------------------------------------------------------------
# SIGINT
# ---------------------------------------------------------------------------


class SigintResult(BaseAgentResult):
    schema_version: int = 1
    sigint_score: float = 0.0
    aircraft: List[Dict[str, Any]] = Field(default_factory=list)
    ships: List[Dict[str, Any]] = Field(default_factory=list)
    hormuz_tankers: List[Dict[str, Any]] = Field(default_factory=list)
    hormuz_tanker_count: int = 0
    conflict_reports: List[Dict[str, Any]] = Field(default_factory=list)
    notams: List[Dict[str, Any]] = Field(default_factory=list)
    alerts: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# NEWS
# ---------------------------------------------------------------------------


class NewsResult(BaseAgentResult):
    schema_version: int = 1
    news_score: float = 0.0
    articles: List[Dict[str, Any]] = Field(default_factory=list)
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    source_breakdown: Dict[str, int] = Field(default_factory=dict)
    overall_sentiment: Optional[float] = None
    sentiment_label: str = ""
    top_sources: List[Dict[str, Any]] = Field(default_factory=list)
    escalation_headlines: List[str] = Field(default_factory=list)
    escalation_score: float = 0.0


# ---------------------------------------------------------------------------
# FININT
# ---------------------------------------------------------------------------


class FinintResult(BaseAgentResult):
    schema_version: int = 1
    escalation_score: float = 0.0
    brent: Optional[Dict[str, Any]] = None
    wti: Optional[Dict[str, Any]] = None
    gold: Optional[Dict[str, Any]] = None
    vix: Optional[Dict[str, Any]] = None
    fear_greed: Optional[Dict[str, Any]] = None
    polymarket: List[Dict[str, Any]] = Field(default_factory=list)
    metaculus: List[Dict[str, Any]] = Field(default_factory=list)
    ofac_sanctions: Dict[str, Any] = Field(default_factory=dict)
    ofac_delta: Optional[Dict[str, Any]] = None
    tracked_wallets: List[Dict[str, Any]] = Field(default_factory=list)
    tracked_chain_wallets: List[Dict[str, Any]] = Field(default_factory=list)
    score_confidence: Optional[Dict[str, Any]] = None
    fetched_at: str = ""


# ---------------------------------------------------------------------------
# GEOINT
# ---------------------------------------------------------------------------


class GeointResult(BaseAgentResult):
    schema_version: int = 1
    geoint_score: float = 0.0
    anomalies: List[Dict[str, Any]] = Field(default_factory=list)
    anomaly_count: int = 0
    high_confidence_count: int = 0
    explosion_count: int = 0
    clusters: List[Dict[str, Any]] = Field(default_factory=list)
    hotspots: List[Dict[str, Any]] = Field(default_factory=list)
    reliefweb_reports: List[Dict[str, Any]] = Field(default_factory=list)
    eo_browser_links: List[Dict[str, Any]] = Field(default_factory=list)
    gdelt_geo_countries: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# SATINTEL
# ---------------------------------------------------------------------------


class SatintelResult(BaseAgentResult):
    schema_version: int = 1
    satintel_score: float = 0.0
    imagery_signals: List[Dict[str, Any]] = Field(default_factory=list)
    aoi: Dict[str, Any] = Field(default_factory=dict)
    copernicus_products: List[Dict[str, Any]] = Field(default_factory=list)
    source_status: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# SOCMINT
# ---------------------------------------------------------------------------


class SocmintResult(BaseAgentResult):
    schema_version: int = 1
    socmint_score: float = 0.0
    telegram_posts: List[Dict[str, Any]] = Field(default_factory=list)
    twitter_posts: List[Dict[str, Any]] = Field(default_factory=list)
    reddit_posts: List[Dict[str, Any]] = Field(default_factory=list)
    rss_articles: List[Dict[str, Any]] = Field(default_factory=list)
    reliefweb_reports: List[Dict[str, Any]] = Field(default_factory=list)
    total_signals: int = 0
    escalatory_count: int = 0
    de_escalatory_count: int = 0
    overall_sentiment: Optional[float] = None
    top_signals: List[Dict[str, Any]] = Field(default_factory=list)
    entities: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# TECHINT
# ---------------------------------------------------------------------------


class TechintResult(BaseAgentResult):
    schema_version: int = 1
    techint_score: float = 0.0
    tech_indicators: List[Dict[str, Any]] = Field(default_factory=list)
    export_controls: List[Dict[str, Any]] = Field(default_factory=list)
    ioda_events: List[Dict[str, Any]] = Field(default_factory=list)
    ioda_outages: List[Dict[str, Any]] = Field(default_factory=list)
    ioda_signals_raw: List[Dict[str, Any]] = Field(default_factory=list)
    ioda_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    ioda_entities: List[Dict[str, Any]] = Field(default_factory=list)
    ooni: Dict[str, Any] = Field(default_factory=dict)
    cloudflare_outages: List[Dict[str, Any]] = Field(default_factory=list)
    shodan: Dict[str, Any] = Field(default_factory=dict)
    wayback: Dict[str, Any] = Field(default_factory=dict)
    whois_dns: Dict[str, Any] = Field(default_factory=dict)
    wigle: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# CYBER
# ---------------------------------------------------------------------------


class CyberResult(BaseAgentResult):
    schema_version: int = 1
    cyber_score: float = 0.0
    cisa_kev: Dict[str, Any] = Field(default_factory=dict)
    threat_reports: List[Dict[str, Any]] = Field(default_factory=list)
    otx_pulses: List[Dict[str, Any]] = Field(default_factory=list)
    greynoise_scan_context: Dict[str, Any] = Field(default_factory=dict)
    internet_db: Dict[str, Any] = Field(default_factory=dict)
    fetched_at: str = ""


# ---------------------------------------------------------------------------
# PROTEST
# ---------------------------------------------------------------------------


class ProtestResult(BaseAgentResult):
    schema_version: int = 1
    protest_score: float = 0.0
    protest_events: List[Dict[str, Any]] = Field(default_factory=list)
    protest_articles: List[Dict[str, Any]] = Field(default_factory=list)
    acled_aggregated: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# DIPLO
# ---------------------------------------------------------------------------


class DiploResult(BaseAgentResult):
    schema_version: int = 1
    diplo_score: float = 0.0
    ofac_sdn: Dict[str, Any] = Field(default_factory=dict)
    eu_sanctions: Dict[str, Any] = Field(default_factory=dict)
    un_icj_news: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# PROXIMITY
# ---------------------------------------------------------------------------


class ProximityResult(BaseAgentResult):
    schema_version: int = 1
    proximity_score: float = 0.0
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    reason_empty: Optional[str] = None
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# NARRATIVE / Signal Framework
# ---------------------------------------------------------------------------


class NarrativeResult(BaseAgentResult):
    schema_version: int = 1
    narrative_score: float = 0.0
    source_comparison_table: List[Dict[str, Any]] = Field(default_factory=list)
    signal_assessment: str = ""
    signals: List[Dict[str, Any]] = Field(default_factory=list)
    synthesis_probability: float = 0.0
    synthesis_text: str = ""
    anomalies: List[Dict[str, Any]] = Field(default_factory=list)
    lexical_state_terms: List[str] = Field(default_factory=list)
    lexical_exile_terms: List[str] = Field(default_factory=list)
    reaction_signals: List[Dict[str, Any]] = Field(default_factory=list)
    state_item_count: int = 0
    exile_item_count: int = 0


# ---------------------------------------------------------------------------
# PENTAGON_SIGNALS (informal DC-area OSINT proxies)
# ---------------------------------------------------------------------------


class PentagonSignalsResult(BaseAgentResult):
    schema_version: int = 1
    pentagon_signals_score: float = 0.0
    venues: List[Dict[str, Any]] = Field(default_factory=list)
    disclaimer: str = ""
    data_confidence: str = "degraded"


# ---------------------------------------------------------------------------
# CHOKEPOINT
# ---------------------------------------------------------------------------


class ChokepointResult(BaseAgentResult):
    schema_version: int = 1
    chokepoint_score: float = 0.0
    chokepoints: List[Dict[str, Any]] = Field(default_factory=list)
    gdelt_disruption: Dict[str, Any] = Field(default_factory=dict)
    external_status: Dict[str, Any] = Field(default_factory=dict)
    data_confidence: str = "estimated"  # live | estimated | degraded


# ---------------------------------------------------------------------------
# Lookup: agent name -> result type
# ---------------------------------------------------------------------------

AGENT_RESULT_TYPES: Dict[str, type] = {
    "energy": EnergyResult,
    "sigint": SigintResult,
    "news": NewsResult,
    "finint": FinintResult,
    "geoint": GeointResult,
    "satintel": SatintelResult,
    "socmint": SocmintResult,
    "techint": TechintResult,
    "cyber": CyberResult,
    "protest": ProtestResult,
    "diplo": DiploResult,
    "proximity": ProximityResult,
    "narrative": NarrativeResult,
    "chokepoint": ChokepointResult,
    "pentagon_signals": PentagonSignalsResult,
}


def get_agent_fallback(agent_name: str) -> Dict[str, Any]:
    """Return a minimal fallback dict for an agent (from its Pydantic model defaults).
    Shape matches the corresponding *Result model; use for error paths and defaults.
    """
    model_cls = AGENT_RESULT_TYPES.get(agent_name)
    if model_cls is None:
        return {}
    instance = model_cls()
    return instance.model_dump()
