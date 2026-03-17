# Agents

Per-agent description: inputs, data sources, main output fields, and typical use. All agents share the signature `run_*_agent(conflict: str) -> Dict[str, Any]` and return at least a score (or equivalent) and domain-specific lists.

---

## FININT

- **Input:** `conflict` (e.g. `"Iran"`) — used to build queries and filter context.
- **Sources:** Brent/WTI/Gold (Alpha Vantage, FRED, EIA), Polymarket, Metaculus, OFAC, Etherscan.
- **Outputs:** `escalation_score`, `brent`, `polymarket` (list), `summary`, and other financial/on-chain fields.
- **Use:** Financial stress and market-implied conflict probability.

---

## SIGINT

- **Input:** `conflict`.
- **Sources:** ADS-B (adsb.fi, adsb.lol), CriticalThreats RSS, Hormuz tankers (Chokepoint AISStream).
- **Outputs:** `sigint_score`, `aircraft`, `ships`, `hormuz_tankers`, `hormuz_tanker_count`, `conflict_reports`, `summary`.
- **Use:** Military aircraft, intel reports, Hormuz tanker traffic. Feeds compliance geofencing and AIS anomaly detection.

---

## NEWS

- **Input:** `conflict`.
- **Sources:** NewsAPI, GDELT Doc API, RSS (BBC, DW, Al Jazeera, RFE/RL).
- **Outputs:** `news_score`, `articles`, `summary`.
- **Use:** Open-source media sentiment and coverage volume.

---

## GEOINT

- **Input:** `conflict`.
- **Sources:** NASA FIRMS (thermal), ACLED, Sentinel Hub EO Browser.
- **Outputs:** `geoint_score`, `anomalies`, `hotspots`, `summary`.
- **Use:** Satellite-detected thermal anomalies and conflict events.

---

## SOCMINT

- **Input:** `conflict`.
- **Sources:** Telegram, Nitter/X, Reddit, RSS, ReliefWeb.
- **Outputs:** `socmint_score`, `top_signals`, `summary`.
- **Use:** Social signal detection and grassroots sentiment.

---

## TECHINT

- **Input:** `conflict`.
- **Sources:** IODA, OONI, Shodan, Cloudflare Radar, Wayback Machine.
- **Outputs:** `techint_score`, `tech_indicators`, `ioda_events`, `ioda_outages`, `ioda_alerts`, `ioda_signals_raw`, `ioda_entities`, `summary`.
- **Use:** Internet disruptions, censorship, cyber exposure.

---

## CYBER

- **Input:** `conflict`.
- **Sources:** CISA KEV, Mandiant/CrowdStrike RSS, AlienVault OTX, GreyNoise.
- **Outputs:** `cyber_score`, `cisa_kev`, `threat_reports`, `otx_pulses`, `greynoise_scan_context`, `summary`.
- **Use:** Active exploits, threat intel, malicious scanning activity.

---

## ENERGY

- **Input:** `conflict`.
- **Sources:** AGSI+ (EU gas storage), Alpha Vantage (Brent/WTI), FRED, EIA.
- **Outputs:** `energy_score`, `agsi_storage`, `commodities`, `food_commodities`, `food_security_risk`, `summary`.
- **Use:** Energy supply stress and commodity price shocks.

---

## PROTEST

- **Input:** `conflict`.
- **Sources:** ACLED (protests/riots), GDELT (protest coverage).
- **Outputs:** `protest_score`, `protest_events`, `protest_articles`, `summary`.
- **Use:** Civil society unrest and protest intensity.

---

## DIPLO

- **Input:** `conflict`.
- **Sources:** OFAC SDN, EU Consolidated List, UN Press, ICJ RSS.
- **Outputs:** `diplo_score`, `ofac_sdn`, `eu_sanctions`, `un_icj_news`, `summary`.
- **Use:** Diplomatic/legal signals, sanctions activity.

---

## PROXIMITY

- **Input:** `conflict`.
- **Sources:** NASA FIRMS, OSM (Overpass API).
- **Outputs:** `proximity_score`, `evidence`, `summary`.
- **Use:** Strike-to-civilian-infrastructure correlation, human-shield flags.

---

## Narrative (Signal Framework)

- **Input:** `conflict`.
- **Role:** State vs. exile media comparison and narrative/signal assessment.
- **Outputs:** `synthesis_text`, `synthesis_probability`, `source_comparison_table`, `signal_assessment`, `anomalies`.
- **Use:** Post-processing layer over agent outputs; compares sources and highlights anomalies.

---

## Chokepoint

- **Input:** `conflict`.
- **Sources:** AISStream (Hormuz tankers), EIA baseline, configurable chokepoint definitions.
- **Outputs:** `chokepoint_score`, `chokepoints`, `summary`.
- **Use:** Strategic chokepoint (e.g. Strait of Hormuz) traffic and risk.

---

## Enrichment & Post-Processing (not standalone agents)

- **Compliance** — Geofencing, AIS anomaly detection, supply-chain screening, OFAC/EU cross-referencing; runs after collection.
- **Predictive** — 24h outlook block from supervisor/outputs.
- **Actors** — Builds actor list for the conflict (e.g. Iran: Israel, US, IRGC, Hezbollah) for compliance screening and UI.
- **ACLED reference** — Fetches reference analyses for the conflict in parallel with agents.

---

## References

- [Architecture](ARCHITECTURE.md)
- [One-pager (sources table)](social-assets/one-pager.md)
- [API keys & env](API-KEYS.md)
- [Agent tool chain](AGENT-TOOL-CHAIN.md)
