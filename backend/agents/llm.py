"""
Direct LLM calls via Anthropic or OpenAI SDK.
No frameworks – just simple API calls.

Usage:
    from agents.llm import call_llm, run_tool_agent, run_agent_with_fallback, get_model_name

    # Simple call (e.g. supervisor synthesis)
    text = call_llm(system="...", user_content="...", model=get_model_name("supervisor"))

    # Tool-calling agent loop (e.g. FININT, SIGINT, ...)
    text = run_tool_agent(system="...", user_content="...", tool_fns={...}, tool_schemas=[...])

    # Full agent entry point with LLM → fallback to rule-based
    result = run_agent_with_fallback(
        conflict="Iran",
        rule_based_fn=_run_rule_based_sigint,
        system_prompt=SIGINT_SYSTEM,
        user_content_template="Monitor military movements for conflict: {conflict}",
        tool_fns={...}, tool_schemas=[...],
    )
"""

import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _get_provider() -> str:
    p = (os.getenv("LLM_PROVIDER") or "anthropic").strip().lower()
    return p if p in ("openai", "anthropic") else "anthropic"


_MODEL_DEFAULTS = {
    "anthropic": {
        "agent": ("ANTHROPIC_AGENT_MODEL", "claude-haiku-4-5-20251001"),
        "supervisor": ("SUPERVISOR_MODEL", "claude-sonnet-4-6"),
        "supervisor_routine": ("SUPERVISOR_ROUTINE_MODEL", "claude-haiku-4-5-20251001"),
        "supervisor_fallback": ("SUPERVISOR_FALLBACK_MODEL", "claude-sonnet-4-6"),
        # "So what?" assessment layer (costly, low frequency).
        "assessment": ("ASSESSMENT_MODEL", "claude-sonnet-4-6"),
        # Finding confidence scoring (cheap, runs on findings list).
        "confidence_scoring": ("CONFIDENCE_SCORING_MODEL", "claude-haiku-4-5-20251001"),
    },
    "openai": {
        "agent": ("OPENAI_AGENT_MODEL", "gpt-4o-mini"),
        "supervisor": ("OPENAI_SUPERVISOR_MODEL", "gpt-4o-mini"),
        "supervisor_routine": ("OPENAI_SUPERVISOR_ROUTINE_MODEL", "gpt-4o-mini"),
        "supervisor_fallback": ("OPENAI_SUPERVISOR_FALLBACK_MODEL", "gpt-4o"),
        "assessment": ("OPENAI_ASSESSMENT_MODEL", "gpt-4o"),
        "confidence_scoring": ("OPENAI_CONFIDENCE_SCORING_MODEL", "gpt-4o-mini"),
    },
}


def get_model_name(role: str = "agent") -> str:
    provider = _get_provider()
    env_key, default = _MODEL_DEFAULTS[provider].get(role, _MODEL_DEFAULTS[provider]["agent"])
    return os.getenv(env_key, default)


def require_api_key() -> None:
    provider = _get_provider()
    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set (LLM_PROVIDER=openai)")
    else:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set")


def call_llm(
    system: str,
    user_content: str,
    model: Optional[str] = None,
    temperature: float = 0,
    max_tokens: int = 4096,
) -> str:
    """Simple LLM call. Returns the text response."""
    provider = _get_provider()
    model = model or get_model_name("agent")

    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        from openai import OpenAI

        client = OpenAI()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
    else:
        from anthropic import Anthropic

        client = Anthropic()
        resp = client.messages.create(
            model=model,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.content[0].text if resp.content else ""


def _to_openai_tools(schemas: List[Dict]) -> List[Dict]:
    """Convert Anthropic-format tool schemas to OpenAI format."""
    return [
        {
            "type": "function",
            "function": {
                "name": s["name"],
                "description": s.get("description", ""),
                "parameters": s.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for s in schemas
    ]


def run_tool_agent(
    system: str,
    user_content: str,
    tool_fns: Dict[str, Callable],
    tool_schemas: List[Dict],
    model: Optional[str] = None,
    temperature: float = 0,
    max_rounds: int = 5,
    max_tokens: int = 4096,
) -> Optional[str]:
    """
    Run an agentic tool-calling loop. Returns the final text response, or None on failure.

    tool_fns:     {"tool_name": callable}
    tool_schemas: Anthropic-format tool definitions:
                  [{"name": "...", "description": "...", "input_schema": {...}}, ...]
    """
    provider = _get_provider()
    model = model or get_model_name("agent")

    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        return _run_openai_loop(
            system, user_content, tool_fns, tool_schemas, model, temperature, max_rounds, max_tokens
        )
    return _run_anthropic_loop(system, user_content, tool_fns, tool_schemas, model, temperature, max_rounds, max_tokens)


def _exec_tool(tool_fns: Dict[str, Callable], name: str, args: Dict) -> Any:
    fn = tool_fns.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}
    try:
        return fn(**args) if args else fn()
    except Exception as e:
        return {"error": str(e)}


def _run_anthropic_loop(
    system: str,
    user_content: str,
    tool_fns: Dict[str, Callable],
    tool_schemas: List[Dict],
    model: str,
    temperature: float,
    max_rounds: int,
    max_tokens: int,
) -> Optional[str]:
    from anthropic import Anthropic

    client = Anthropic()
    messages: list = [{"role": "user", "content": user_content}]

    for _ in range(max_rounds):
        resp = client.messages.create(
            model=model,
            system=system,
            messages=messages,
            tools=tool_schemas,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text_parts = []
        tool_uses = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        if not tool_uses:
            return " ".join(text_parts)

        assistant_content = []
        for block in resp.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
        messages.append({"role": "assistant", "content": assistant_content})

        tool_results = []
        for tu in tool_uses:
            result = _exec_tool(tool_fns, tu.name, tu.input or {})
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(result, default=str),
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return None


def _run_openai_loop(
    system: str,
    user_content: str,
    tool_fns: Dict[str, Callable],
    tool_schemas: List[Dict],
    model: str,
    temperature: float,
    max_rounds: int,
    max_tokens: int,
) -> Optional[str]:
    from openai import OpenAI

    client = OpenAI()
    messages: list = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    openai_tools = _to_openai_tools(tool_schemas)

    for _ in range(max_rounds):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=openai_tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = resp.choices[0]

        if not choice.message.tool_calls:
            return choice.message.content or ""

        messages.append(choice.message)
        for tc in choice.message.tool_calls:
            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            result = _exec_tool(tool_fns, tc.function.name, args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                }
            )

    return None


# ── Generic agent entry point ────────────────────────────────────────────


def run_agent_with_fallback(
    conflict: str,
    *,
    rule_based_fn: Callable[[str], Dict[str, Any]],
    system_prompt: str,
    user_content_template: str,
    tool_fns: Dict[str, Callable],
    tool_schemas: List[Dict],
    max_rounds: int = 5,
) -> Dict[str, Any]:
    """
    Unified agent entry point: rule-based when USE_RULE_BASED_AGENTS is set,
    otherwise LLM tool-calling loop with automatic fallback to rule-based on failure.
    """
    from .config import USE_RULE_BASED_AGENTS
    from .utils import parse_llm_json

    if USE_RULE_BASED_AGENTS:
        return rule_based_fn(conflict)

    text = run_tool_agent(
        system=system_prompt,
        user_content=user_content_template.format(conflict=conflict),
        tool_fns=tool_fns,
        tool_schemas=tool_schemas,
        max_rounds=max_rounds,
    )
    if text:
        result = parse_llm_json(text)
        if result is not None:
            result.setdefault("conflict", conflict)
            return result
        logger.warning("LLM returned unparseable JSON, falling back to rule-based")

    return rule_based_fn(conflict)
