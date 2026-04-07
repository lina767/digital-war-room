# Methodology

This page defines the scoring and interpretation model used by Digital War Room. It consolidates the former standalone `/methodology` page into the [documentation hub](https://digital-war-room.com/docs/documentation?doc=methodology).

## Composite escalation score

Each agent returns a normalized score in `[0, 100]`.

Let **n = 12** agents, **s_i** the score of agent **i**, and **w_i** the weight with **Σ w_i = 100%**. The composite score is:

`S = Σ (w_i × s_i)` in the range **[0, 100]**

Weights emphasize leading indicators (e.g. signal mobility, chokepoint stress) while preserving coverage across narrative, cyber, energy, and political streams.

### Agent weights (illustrative baseline)

| Agent | Weight | Full name |
|------|--------|-----------|
| SIGINT | 12% | Signals Intelligence |
| CHOKEPOINT | 11% | Maritime Chokepoint Monitor |
| FININT | 9% | Financial Intelligence |
| NEWS | 9% | News / OSINT |
| SOCMINT | 9% | Social Media Intelligence |
| PROXIMITY | 9% | Strike–Civilian / Human-Shield |
| GEOINT | 7% | Geospatial Intelligence |
| TECHINT | 7% | Technical Intelligence |
| CYBER | 7% | Threat Intelligence |
| ENERGY | 7% | Energy / Commodities |
| CIVIL_UNREST | 0% | Civil Society / Protest (Agent stub; Gewicht auf andere Streams umgelegt) |
| DIPLO | 6% | Diplomacy / Legal |

Equivalent code-style summary: `combined_score = Σ (agent_score × weight)` with `Σ weight = 100%`.

## Threat level mapping

The composite score maps to a single threat level on the dashboard and in briefings. When the supervisor LLM is enabled, it may refine wording; the rule-based mapping below is the deterministic baseline.

**Decision rule L(S)** — threat level as a function of composite score **S**:

- `L(S) = CRITICAL` ⇔ `S ≥ 80`
- `L(S) = HIGH` ⇔ `60 ≤ S < 80`
- `L(S) = ELEVATED` ⇔ `40 ≤ S < 60`
- `L(S) = LOW` ⇔ `20 ≤ S < 40`
- `L(S) = MINIMAL` ⇔ `S < 20`

| Level | Min. S | Description |
|-------|-----------|-------------|
| CRITICAL | 80 | Severe escalation; immediate attention |
| HIGH | 60 | Elevated risk; significant indicators |
| ELEVATED | 40 | Moderate escalation |
| LOW | 20 | Low activity |
| MINIMAL | 0 | Baseline; no significant signals |

## Peak-weighted escalation (predictive block)

For the predictive block and short-horizon outlook, a **peak-weighted** score increases the influence of the strongest streams so a single quiet stream does not dampen the signal when others spike.

Let **s_(1) ≥ s_(2) ≥ … ≥ s_(n)** be agent scores sorted descending.

- **s̄_top3** = average of the top 3 scores  
- **S_peak** = `0.6 × s̄_top3 + 0.4 × S`  
- **S_esc** = `max(S, S_peak)` — used in the predictive block  

The displayed escalation score does not drop below **S**; when the top three streams are high, **S_esc** rises.

## Narrative / Signal Framework

The **Signal Framework** (narrative agent) compares state-aligned and exile/independent media for contexts such as Iran. It does not emit a numeric escalation score; it yields synthesis probability, a source comparison table, and latency/credibility gaps.

- **State-aligned (example):** IRNA, Fars, Tasnim, Press TV (RSS).
- **Exile / independent (example):** Iran International, Radio Farda, BBC Persian.

Implementation lives in the backend (`signal_framework_agent`). Outputs include `synthesis_text`, `synthesis_probability`, `source_comparison_table`, and `signal_assessment`. These feed the supervisor and the dashboard Narrative / Signal Framework panel.

## Further rule-based scores

- **Per-agent scores (0–100)** — Computed per stream via rule-based or LLM-assisted aggregation (see individual agents; e.g. TECHINT increments for IODA outages, OONI blocks; CYBER from KEV, threat reports, GreyNoise context).
- **Compliance risk** — Maps a numeric score (0–100) to LOW / MEDIUM / HIGH / CRITICAL (see `backend/compliance/risk_score`): e.g. LOW if score &lt; 25, MEDIUM 25–50, HIGH 50–75, CRITICAL ≥ 75. Inputs include sanctions matches, geofencing, AIS anomalies, and escalation context.

## Related

- [How It Works](https://digital-war-room.com/docs/documentation?doc=how-it-works)
- [Source Directory](https://digital-war-room.com/docs/documentation?doc=source-directory)
- [Documentation hub](https://digital-war-room.com/docs/documentation)
