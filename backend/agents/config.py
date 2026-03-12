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
