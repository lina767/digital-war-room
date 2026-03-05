"""
Shared agent configuration (env flags).
Used to switch agents between LLM-driven and fixed tool-chain (rule-based) execution.
"""
import os


def _env_true(key: str, default: bool = False) -> bool:
    """True if env key is one of 1, true, yes (case-insensitive)."""
    val = (os.getenv(key) or "").strip().lower()
    if default and not val:
        return True
    return val in ("1", "true", "yes")


# When True, each agent skips its LLM (Haiku) loop and runs the fixed tool chain
# in documented order (see docs/AGENT-TOOL-CHAIN.md). Output shape is unchanged;
# the supervisor (Claude Sonnet) still receives the same payload and synthesizes as usual.
USE_RULE_BASED_AGENTS = _env_true("USE_RULE_BASED_AGENTS", default=False)
