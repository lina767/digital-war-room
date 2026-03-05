"""
LLM factory: Anthropic (Claude) or OpenAI.
Set LLM_PROVIDER=openai and OPENAI_API_KEY to use cheaper OpenAI models (e.g. gpt-4o-mini).
"""
import os
from typing import Any, List, Optional

# Lazy imports to avoid loading both backends when only one is used


def _get_provider() -> str:
    """openai or anthropic (default)."""
    p = (os.getenv("LLM_PROVIDER") or "anthropic").strip().lower()
    return p if p in ("openai", "anthropic") else "anthropic"


def get_agent_model(tools: Optional[List[Any]] = None):
    """
    Model for agents (FININT, SIGINT, NEWS, GEOINT, SOCMINT).
    With tools: use .bind_tools(tools). Return type is LangChain BaseChatModel.
    """
    provider = _get_provider()
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        model_name = os.getenv("OPENAI_AGENT_MODEL", "gpt-4o-mini")
        model = ChatOpenAI(model=model_name, temperature=0)
    else:
        from langchain_anthropic import ChatAnthropic
        model_name = os.getenv("ANTHROPIC_AGENT_MODEL", "claude-haiku-4-5-20251001")
        model = ChatAnthropic(model=model_name, temperature=0)
    if tools:
        return model.bind_tools(tools)
    return model


def get_supervisor_model(complex_case: bool = False):
    """
    Model for the supervisor (synthesis only, no tools).
    When complex_case=True (e.g. agents disagree), use the fallback model (e.g. Sonnet)
    for better reasoning; otherwise use the default (e.g. Haiku).
    Requires ANTHROPIC_API_KEY if provider=anthropic, OPENAI_API_KEY if provider=openai.
    """
    provider = _get_provider()
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        if complex_case:
            model_name = os.getenv("OPENAI_SUPERVISOR_FALLBACK_MODEL", "gpt-4o")
        else:
            model_name = os.getenv("OPENAI_SUPERVISOR_MODEL", "gpt-4o-mini")
        return ChatOpenAI(model=model_name, temperature=0.1)
    from langchain_anthropic import ChatAnthropic
    if complex_case:
        model_name = os.getenv("SUPERVISOR_FALLBACK_MODEL", "claude-sonnet-4-6")
    else:
        model_name = os.getenv("SUPERVISOR_MODEL", "claude-haiku-4-5-20251001")
    return ChatAnthropic(model=model_name, temperature=0.1)


def require_supervisor_api_key() -> None:
    """Raise if no API key is set for the chosen provider."""
    provider = _get_provider()
    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set (LLM_PROVIDER=openai)")
    else:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
