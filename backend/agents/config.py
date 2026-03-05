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


# When True (default), each agent skips its LLM loop and runs the fixed tool chain
# in documented order (see docs/AGENT-TOOL-CHAIN.md). Output shape is unchanged;
# the supervisor still receives the same payload and synthesizes as usual.
# Set to false to use Claude/OpenAI in each agent (higher cost).
USE_RULE_BASED_AGENTS = _env_true("USE_RULE_BASED_AGENTS", default=True)

# LLM provider: see agents/llm_factory.py. Use LLM_PROVIDER=openai + OPENAI_API_KEY
# for cheaper runs (e.g. gpt-4o-mini). Default is anthropic (ANTHROPIC_API_KEY).
