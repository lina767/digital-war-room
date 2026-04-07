# Code Snippets for Social Media

Clean, annotated snippets from the Digital War Room codebase. Use these in X threads, LinkedIn posts, and Reddit Show & Tell. Always sanitize before posting (no API keys, no internal URLs).

---

## 1. Parallel Agent Orchestration (Supervisor)

The core pattern: 11 agents run in parallel with `ThreadPoolExecutor`, each with a 75-second timeout and a fallback dict so one failing API never blocks the others.

```python
def _collect_all_agents(conflict: str) -> Dict[str, Any]:
    """Run all 11 intelligence agents + ACLED reference in parallel."""
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {
            "finint":    (executor.submit(run_finint_agent, conflict),
                          {"escalation_score": 0.0, "brent": None, "polymarket": []}),
            "sigint":    (executor.submit(run_sigint_agent, conflict),
                          {"sigint_score": 0.0, "aircraft": [], "ships": []}),
            "news":      (executor.submit(run_news_agent, conflict),
                          {"news_score": 0.0, "articles": [], "summary": ""}),
            "geoint":    (executor.submit(run_geoint_agent, conflict),
                          {"geoint_score": 0.0, "anomalies": [], "hotspots": []}),
            # ... 7 more agents (SOCMINT, TECHINT, CYBER, ENERGY, CIVIL_UNREST, DIPLO, PROXIMITY)
        }

        results = {}
        for name, (fut, fallback) in futures.items():
            try:
                results[name] = fut.result(timeout=75)  # 75s per agent
            except Exception as e:
                results[name] = {**fallback, "error": str(e)}

    return results
```

**Why this matters:** No LangGraph, no CrewAI, no framework overhead. Just Python's stdlib doing concurrent I/O with explicit timeouts and fallbacks.

---

## 2. LLM Abstraction — Provider-Agnostic in 30 Lines

Swap between Anthropic and OpenAI with one env var. No framework lock-in.

```python
def call_llm(
    system: str,
    user_content: str,
    model: Optional[str] = None,
    temperature: float = 0,
    max_tokens: int = 4096,
) -> str:
    provider = _get_provider()  # reads LLM_PROVIDER env var
    model = model or get_model_name("agent")

    if provider == "openai":
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature, max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
    else:
        from anthropic import Anthropic
        client = Anthropic()
        resp = client.messages.create(
            model=model, system=system,
            messages=[{"role": "user", "content": user_content}],
            temperature=temperature, max_tokens=max_tokens,
        )
        return resp.content[0].text if resp.content else ""
```

---

## 3. Dual-Mode Agents: LLM or Rule-Based

Every agent supports two paths — LLM tool-calling or deterministic rule-based. Controlled by one env var, with automatic fallback if the LLM fails.

```python
def run_agent_with_fallback(
    conflict: str,
    *,
    rule_based_fn: Callable[[str], Dict[str, Any]],
    system_prompt: str,
    user_content_template: str,
    tool_fns: Dict[str, Callable],
    tool_schemas: List[Dict],
) -> Dict[str, Any]:
    if USE_RULE_BASED_AGENTS:
        return rule_based_fn(conflict)

    text = run_tool_agent(
        system=system_prompt,
        user_content=user_content_template.format(conflict=conflict),
        tool_fns=tool_fns, tool_schemas=tool_schemas,
    )
    if text:
        result = parse_llm_json(text)
        if result is not None:
            return result

    # LLM failed or returned garbage → fall back to deterministic path
    return rule_based_fn(conflict)
```

**The philosophy:** LLMs are powerful but unreliable. Every agent must work without one.

---

## 4. Weighted Multi-Source Scoring

11 intelligence streams fused into one composite score with configurable weights.

```python
combined_score = (
    finint_score   * 0.10 +
    sigint_score   * 0.13 +   # SIGINT weighted highest — military movements
    news_score     * 0.10 +
    geoint_score   * 0.08 +
    socmint_score  * 0.10 +
    techint_score  * 0.08 +
    cyber_score    * 0.08 +
    energy_score   * 0.08 +
    civil unrest_score  * 0.08 +
    diplo_score    * 0.07 +
    proximity_score * 0.10    # Proximity weighted high — civilian risk
)
```

The LLM supervisor sees this composite score plus raw data from all streams, then produces the final `threat_level` (MINIMAL → CRITICAL), `key_findings`, `scenarios`, and `summary`.

---

## 5. Military Aircraft Classification (SIGINT)

How the SIGINT agent distinguishes surveillance drones from tankers from fighters using ADS-B data:

```python
MILITARY_CALLSIGN_PREFIXES = [
    "RCH", "USAF", "NAVY", "DUKE", "REACH", "FORTE",  # RQ-4 Global Hawk
    "TACAMO",   # E-6B Mercury (nuclear C3)
]

SURVEILLANCE_TYPES = [
    "RC-135", "E-3", "E-8", "P-8", "RQ-4", "MQ-9", "U-2",
    "E-7",    # E-7A Wedgetail (drone/cruise missile detection)
    "E6B",    # E-6B Mercury (TACAMO — nuclear C3, doomsday plane)
]

TANKER_TYPES = [
    "KC-135", "KC-10", "KC-46",
    "A330",   # A330 MRTT (Israel/NATO/UAE — long-range refueling)
]

FIGHTER_TYPES = ["F-16", "F-15", "F-35", "F/A-18", "B-52", "B-2", "B1"]
```

When FORTE11 (RQ-4 Global Hawk) shows up over the Persian Gulf alongside KC-135 tankers, the SIGINT score spikes. That's not a coincidence — it's pre-strike surveillance posture.
