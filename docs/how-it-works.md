# How It Works

Digital War Room runs a multi-agent intelligence workflow that turns heterogeneous OSINT inputs into a single, structured threat assessment.

## Documentation hub

This guide is the canonical **in-product** reference: open [Documentation → How It Works](https://digital-war-room.com/docs/documentation?doc=how-it-works). The former standalone pages `/how-it-works`, `/methodology`, and `/sources` now **redirect** to the documentation hub so bookmarks keep working.

- [Methodology (documentation)](https://digital-war-room.com/docs/documentation?doc=methodology)
- [Source Directory (documentation)](https://digital-war-room.com/docs/documentation?doc=source-directory)

## End-to-end flow

1. A conflict context (for example `Iran`) is selected.
2. Specialized agents execute in parallel and fetch source-specific data.
3. Each agent returns structured output with score, summary, and findings.
4. A supervisor synthesizes the agent outputs into a composite assessment.
5. Results are cached and served to the dashboard, briefing, and downstream panels.

## Common questions

**What is this platform?**  
An OSINT fusion dashboard: multiple specialist agents pull open data, normalize it, and a supervisor layer produces a single escalation-style assessment with structured panels (not operational orders).

**What intelligence streams does the platform use?**  
Twelve streams are represented in scoring and UI: SIGINT, Chokepoint, FININT, NEWS, SOCMINT, Proximity, GEOINT, TECHINT, CYBER, ENERGY, PROTEST, and DIPLO. Each stream is handled by a dedicated agent that calls external APIs and computes a stream-specific score.

**Where can I see the data sources?**  
In [Documentation → Source Directory](https://digital-war-room.com/docs/documentation?doc=source-directory) (searchable list). [Methodology](https://digital-war-room.com/docs/documentation?doc=methodology) explains composite scoring and threat levels.

## Intelligence streams (detail)

The platform combines several OSINT streams. Each stream uses a dedicated agent that calls external APIs, normalizes results, and computes a stream-specific score.

For conflict **Iran**, keywords and synthesis explicitly include Hezbollah–IDF and Houthis (no separate dropdown). Global impact (e.g. oil price moves, Strait of Hormuz / chokepoint risk) is derived from ENERGY and surfaced in key findings and the **Global Impact** panel.

### FININT – Financial Intelligence

- Brent / WTI oil prices and key market indicators
- Polymarket prediction markets (e.g. US–Iran, military actions, regime stability)
- Combined into a financial escalation score

### SIGINT – Signals Intelligence

- Military aircraft and naval movements (ADS-B / open feeds)
- Conflict reports from think tanks (Iran context includes Hezbollah, Houthis, Yemen, Lebanon in keywords)
- Aggregated into a SIGINT escalation score

### NEWS – Open-source media

- News articles for the selected conflict
- Headline and body sentiment (escalatory vs. de-escalatory)
- Summarised into `news_score` for the supervisor

### GEOINT – Geospatial Intelligence

- Thermal anomaly detections (e.g. NASA FIRMS)
- Hotspots and clusters in relevant regions
- Geospatial anomaly score for the conflict

### SOCMINT – Social Media Intelligence

- Signals from Telegram, Reddit, RSS (Iran: includes related actors in query scope)
- Focus on escalation-related narratives and spikes
- Top social signals passed to the supervisor

### TECHINT – Technical Intelligence

- Tech & export control news impacting escalation
- Internet outage signals (IODA, Cloudflare, OONI)
- Shodan exposure around relevant regions

### CYBER – Threat Intelligence

- CISA KEV, threat reports, AlienVault OTX pulses
- GreyNoise malicious scanner context
- Combined into a cyber escalation score

### ENERGY – Commodities & Gas

- EU gas storage (AGSI+), Brent/WTI
- For Iran: global impact note when oil moves significantly (Strait of Hormuz / chokepoint risk)
- Energy score and commodities feed supervisor and Global Impact panel

### PROTEST – Civil Society

- ACLED protests/riots, GDELT protest coverage
- Civil society unrest score for the supervisor

### DIPLO – Diplomacy / Legal

- OFAC SDN, EU sanctions, UN/ICJ press
- Feeds Sanctions Compliance risk score

### PROXIMITY – Strike–Civilian

- NASA FIRMS thermal anomalies vs. OSM schools/hospitals (and optional tunnel/military sites)
- Human-shield / collateral risk labels; evidence for key findings

### Chokepoint

- Maritime chokepoint traffic and risk (see dashboard Chokepoint Monitor and theater map overlays)

## Analysis pipeline

1. **Select a conflict.** In the dashboard header you choose a conflict (e.g. `Iran`). This value is passed to all agents. For Iran, Hezbollah, Houthis and global impact (oil, Hormuz) are included in keywords and synthesis without a separate dropdown.

2. **Agents run in parallel.** Agents run concurrently. Each agent calls its external APIs, handles timeouts gracefully, and computes a stream-specific score and structured result.

3. **Rule-based by default.** By default, agents follow fixed rule-based tool chains (predictable behaviour and cost control).

4. **Supervisor synthesis.** Agent results are fed into a supervisor that produces a single payload: `escalation_score` (0–100), `threat_level` (MINIMAL / LOW / ELEVATED / HIGH / CRITICAL), `key_findings`, `scenarios`, and a short BLUF-style `summary`.

5. **Background auto-runs.** A background job periodically re-runs analysis for the default conflict (e.g. every 6 hours). The latest result is cached and served when you open the dashboard.

## Dashboard features

- **Live ticker & threat level** — Headlines and signals from the latest analysis; threat level badge for at-a-glance escalation.
- **Agents panel** — All intelligence agents, names, and data sources for the selected conflict.
- **Conflict map & timeline** — Region map with thermal anomalies, aircraft, ships; optional heatmap (ACLED), SAM rings, air/sea routes; escalation timeline.
- **Intelligence feed & Global Impact** — Updated briefing, Global Impact (oil/Hormuz when available), headlines, events, proximity analyzer, connectivity, prediction markets.
- **Sanctions Compliance** — OFAC/EU, geofencing, AIS anomalies, compliance risk score; on-demand sanctions search.

## How to read the dashboard

The Intelligence Feed (right panel) is grouped into four domains (expand/collapse; choices persist):

- **Information** — Updated Briefing, Signal Framework, Predictive Outlook, Latest Headlines, Events Timeline
- **Political** — Sanctions Compliance
- **Security** — Chokepoint Monitor, Proximity Analyzer, Activity & Connectivity (GreyNoise, SIGINT tracker, prediction markets)
- **Economic** — Global Impact (oil/commodities, Hormuz risk)

Use the view toggle (list / grid / focus): **Full** (all sections by domain), **Summary** (briefing plus one line per panel), or **Focus** (escalation score, threat level, top findings only).

**Scores and risk** — Escalation score (0–100) and threat level come from supervisor synthesis. Compliance risk reflects sanctions lists, geofencing, and AIS signals. Chokepoint status reflects maritime/supply risk. All are indicative; not legal or operational advice.

When the supervisor provides context, you may see **“Why this matters”** under a finding. When multiple agents agree, **“Corroborated by N agents”** may appear. Sparklines show recent trend vs. current value where available.

Data sources are listed in the [Source Directory](https://digital-war-room.com/docs/documentation?doc=source-directory). The dashboard is for intelligence awareness only; it does not replace legal review or operational decisions.

## LLM modes & cost model

The platform stays useful when LLM usage is constrained. Agents can run purely rule-based. The supervisor can use a lightweight model (e.g. Haiku, `gpt-4o-mini`) or be replaced by deterministic scoring.

- **Default** — Rule-based agents; supervisor uses a small model for synthesis.
- **Savings** — Disable expensive fallbacks; use `gpt-4o-mini` for the supervisor; or run a fully rule-based supervisor (no LLM).

## Operating modes

- **Rule-based baseline:** deterministic agent toolchains with stable output contracts.
- **Supervisor synthesis:** optional LLM layer for narrative and score interpretation.
- **Graceful fallback:** if model responses fail, direct tool outputs and calculated scores still return so payloads are not empty.

## Related

- [Methodology](https://digital-war-room.com/docs/documentation?doc=methodology)
- [Source Directory](https://digital-war-room.com/docs/documentation?doc=source-directory)
- [Documentation hub](https://digital-war-room.com/docs/documentation)
