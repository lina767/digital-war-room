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
- **Sources:** NewsAPI (`NEWS_API_KEY`, optional), GNews (`GNEWS_API_KEY`, optional), NewsData.io (`NEWSDATA_API_KEY`, optional), The Guardian Content API (`THE_GUARDIAN_API_KEY`, optional), curated RSS feeds (BBC, DW, Al Jazeera, RFE/RL), plus GDELT BigQuery event-root summary.
- **Outputs:** `news_score`, `articles`, `summary`.
- **Use:** Open-source media sentiment and coverage volume.

---

## GEOINT

- **Input:** `conflict`.
- **Sources:** NASA FIRMS (thermal), ACLED, Sentinel Hub EO Browser.
- **Outputs:** `geoint_score`, `anomalies`, `hotspots`, `summary`.
- **Use:** Satellite-detected thermal anomalies and conflict events.

---

## SATINTEL

- **Input:** `conflict`.
- **Sources:** Sentinel Hub Process API (OAuth), Copernicus Data Space OData catalogue.
- **Outputs:** `satintel_score`, `imagery_signals`, `aoi`, `copernicus_products`, `summary`.
- **Use:** Top-level satellite imagery signal scoring from Sentinel/Copernicus products.

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
- **Sources:** Alpha Vantage (Brent/WTI), FRED, EIA; FAO Food Price Index (CSV); **World Bank Open Data** (global fertilizer Urea/DAP; **country-level** GDP, CPI, electricity access, poverty at $1.90/day when `conflict` maps to an ISO3 via slug or substring rules).
- **Outputs:** `energy_score`, `agsi_storage`, `commodities`, `food_commodities`, `fao_fpi`, `fertilizer`, `world_bank_country`, `food_security_risk`, `summary`, optional `global_impact_note`.
- **Use:** Energy supply stress, commodity price shocks, and structural macro context (WB) for the conflict geography.

---

## CIVIL_UNREST

- **Status:** Implementierung entfernt; `run_civil unrest_agent` liegt in `backend/agents/civil unrest_stub.py` und liefert ein leeres `ProtestResult` (Score 0, degraded meta), damit DAG/API-Shape erhalten bleibt.
- **Input:** `conflict` (wird ignoriert).
- **Outputs:** Wie `ProtestResult`-Fallback; keine Live-Quellen.

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
- **Outputs:** `synthesis_text`, `synthesis_probability`, `source_comparison_table`, `signal_assessment`, `anomalies`, plus optional LLM deep-analysis fields (Anthropic/OpenAI): `theme_clusters`, `quoted_passages`, `negotiation_narrative_score`, `method_notes`.
- **Feature flags:** `SIGNAL_FRAMEWORK_GEMINI_DEEP_ANALYSIS`, `SIGNAL_FRAMEWORK_GEMINI_MAX_ITEMS`, `SIGNAL_FRAMEWORK_GEMINI_MAX_QUOTES` (env names kept for backwards-compat; backend now uses Anthropic/OpenAI since Gemini was removed for cost reasons).
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
