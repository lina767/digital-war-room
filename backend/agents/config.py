"""
Shared agent configuration: env flags, timeouts, and common constants.
"""

import os


def _env_true(key: str, default: bool = False) -> bool:
    """True if env key is one of 1, true, yes (case-insensitive)."""
    val = (os.getenv(key) or "").strip().lower()
    if default and not val:
        return True
    return val in ("1", "true", "yes")


# When True (default), each agent skips its LLM loop and runs the fixed tool chain
# in documented order (see docs/AGENT-TOOL-CHAIN.md). Output shape is unchanged;
# the supervisor still receives the same payload and synthesizes as usual.
USE_RULE_BASED_AGENTS = _env_true("USE_RULE_BASED_AGENTS", default=True)

# LLM provider: see agents/llm.py. Use LLM_PROVIDER=openai + OPENAI_API_KEY
# for cheaper runs (e.g. gpt-4o-mini). Default is anthropic (ANTHROPIC_API_KEY).

# ── Shared HTTP defaults ──────────────────────────────────────────────────

USER_AGENT = "DigitalWarRoom/1.0 (OSINT analysis)"

DEFAULT_TIMEOUT = 15.0
LONG_TIMEOUT = 25.0
SHORT_TIMEOUT = 10.0

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

# ── GreyNoise (Emerging Threats agent) ────────────────────────────────────

GREYNOISE_API_KEY = (os.getenv("GREYNOISE_API_KEY") or "").strip() or None
GREYNOISE_BASE_URL = os.getenv("GREYNOISE_BASE_URL", "https://api.greynoise.io").rstrip("/")
GREYNOISE_TIMEOUT = float(os.getenv("GREYNOISE_TIMEOUT", "20"))
GREYNOISE_SCHEDULER_INTERVAL_SEC = int(os.getenv("GREYNOISE_SCHEDULER_INTERVAL_SEC", "21600"))  # 6h
GREYNOISE_SCHEDULER_CONFLICTS = [
    c.strip()
    for c in os.getenv(
        "GREYNOISE_CONFLICTS",
        "Iran,Israel,USA,UAE,Saudi Arabia,Lebanon,Jordan,Gaza/Israel,Yemen,Middle East",
    ).split(",")
    if c.strip()
]

# ── Multi-Agent Hierarchy Configuration ───────────────────────────────────

HIERARCHY_WEIGHTS = {
    "divisions": {
        "military": {
            "ceo_weight": 0.30,
            "agents": {"sigint": 0.30, "geoint": 0.25, "chokepoint": 0.25, "proximity": 0.20},
        },
        "financial": {"ceo_weight": 0.18, "agents": {"finint": 0.55, "energy": 0.45}},
        "information": {"ceo_weight": 0.22, "agents": {"news": 0.40, "socmint": 0.35, "narrative": 0.25}},
        "political": {"ceo_weight": 0.14, "agents": {"diplo": 0.55, "protest": 0.45}},
        "technical": {"ceo_weight": 0.16, "agents": {"techint": 0.50, "cyber": 0.50}},
    },
    "circuit_breaker": {
        "max_consecutive_failures": int(os.getenv("CB_MAX_FAILURES", "3")),
        "reopen_after_cycles": int(os.getenv("CB_REOPEN_CYCLES", "3")),
    },
    "anomaly": {
        "contradiction_score_spread": float(os.getenv("ANOMALY_CONTRADICTION_SPREAD", "50")),
        "threshold_breach_score": float(os.getenv("ANOMALY_THRESHOLD_SCORE", "75")),
        "haiku_trigger_severity": os.getenv("ANOMALY_HAIKU_SEVERITY", "medium"),
    },
    "dag_node_timeouts": {
        "agent": 75.0,
        "enrichment": 15.0,
        "division_summary": 10.0,
        "synthesis": 30.0,
    },
    "haiku_periodic_cycles": int(os.getenv("HAIKU_PERIODIC_CYCLES", "0")),
}

AGENT_TTLS = {
    "energy": int(os.getenv("AGENT_TTL_ENERGY", "900")),
    "diplo": int(os.getenv("AGENT_TTL_DIPLO", "3600")),
    "techint": int(os.getenv("AGENT_TTL_TECHINT", "1800")),
    "narrative": int(os.getenv("AGENT_TTL_NARRATIVE", "1800")),
    "news": 0,
    "socmint": 0,
    "sigint": 0,
    "chokepoint": 0,
    "finint": 0,
    "geoint": 0,
    "cyber": 0,
    "protest": 0,
    "proximity": 0,
}

STORE_RETENTION_CYCLES = int(os.getenv("STORE_RETENTION_CYCLES", "5"))
STORE_RETENTION_MINUTES = float(os.getenv("STORE_RETENTION_MINUTES", "60"))

DISABLED_AGENTS = [a.strip() for a in os.getenv("DISABLED_AGENTS", "").split(",") if a.strip()]

# Default conflict for analyze/status/latest and route defaults (e.g. "Iran").
DEFAULT_CONFLICT = (os.getenv("DEFAULT_CONFLICT", "Iran") or "Iran").strip()

# When True, run agents in two waves: wave 1 (foundation) then build AgentContext and run wave 2
# (context-aware) so agents can focus on each other's findings (e.g. GEOINT on SIGINT regions).
USE_AGENT_HANDOFF = _env_true("USE_AGENT_HANDOFF", default=False)

# ── News / shared API limits ───────────────────────────────────────────────

NEWS_MAX_PER_SOURCE = int(os.getenv("NEWS_MAX_PER_SOURCE", "5"))
NEWS_TOP_K = int(os.getenv("NEWS_TOP_K", "20"))
RELIEFWEB_APPNAME = (os.getenv("RELIEFWEB_APPNAME") or "").strip() or "digital-war-room"
