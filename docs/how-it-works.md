# How It Works

Digital War Room runs a multi-agent intelligence workflow that turns heterogeneous OSINT inputs into a single, structured threat assessment.

## Interactive page

The **interactive How It Works** experience is a live walkthrough (dashboard guide, methodology, and related links) in the product UI:

- **Production:** <https://digital-war-room.com/how-it-works>
- **Same app (local or any deployment):** `/how-it-works`

Use that page when you want the guided, clickable version; this Markdown doc is the canonical **text** reference you can read in the [Documentation hub](https://digital-war-room.com/docs/documentation?doc=how-it-works) or on GitHub.

## End-to-end flow

1. A conflict context (for example `Iran`) is selected.
2. Specialized agents execute in parallel and fetch source-specific data.
3. Each agent returns structured output with score, summary, and findings.
4. A supervisor synthesizes the agent outputs into a composite assessment.
5. Results are cached and served to the dashboard, briefing, and downstream panels.

## Intelligence streams

The core streams include:

- FININT (financial indicators and market stress)
- SIGINT (air/naval signal activity)
- NEWS (open-source media velocity and sentiment)
- GEOINT (geospatial anomalies and hotspots)
- SOCMINT (social and narrative signals)
- TECHINT (technical infrastructure and connectivity indicators)
- CYBER (threat intelligence and scanner context)
- ENERGY (commodity and energy stress signals)
- PROTEST (civil unrest and protest dynamics)
- DIPLO (diplomatic/legal and sanctions context)
- PROXIMITY (strike-to-civilian proximity risk evidence)

Related pages:

- Methodology: <https://digital-war-room.com/methodology>
- Source Directory: <https://digital-war-room.com/sources>
- Documentation hub: <https://digital-war-room.com/docs/documentation>

## Operating modes

- **Rule-based baseline:** deterministic agent toolchains with stable output contracts.
- **Supervisor synthesis:** optional LLM synthesis layer that produces the final narrative and score interpretation.
- **Graceful fallback behavior:** if model responses fail, direct tool outputs and calculated scores are still returned so no empty payload is produced.

## Dashboard interpretation

The dashboard exposes:

- escalation score and threat level
- key findings and scenarios
- domain-specific panels (compliance, proximity, market/impact, narrative)

Use this page as the canonical narrative reference for system behavior. Implementation details remain in code and architecture docs.
