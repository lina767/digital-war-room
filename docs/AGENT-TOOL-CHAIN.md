# Agent- und Tool-Kette – Aufrufreihenfolge

Überblick für das regelbasierte System: Wo werden Agents/Tools in welcher Reihenfolge aufgerufen? (Stand: aktueller Code.)

**Tracing:** Wenn `OTEL_EXPORTER_OTLP_ENDPOINT` gesetzt ist, werden Supervisor-LLM, Agent-Tools und Sammlung als OpenTelemetry-Spans exportiert (z. B. an Jaeger oder einen anderen OTLP-kompatiblen Collector).

---

## Regelbasierten Modus aktivieren

- **Umgebungsvariable:** `USE_RULE_BASED_AGENTS` ist standardmäßig `true`. Zum Deaktivieren: `USE_RULE_BASED_AGENTS=false`.
- **Wirkung:** Jeder Agent (FININT, SIGINT, NEWS, GEOINT, SOCMINT) führt seine **feste Tool-Kette** in der unten dokumentierten Reihenfolge aus – **ohne** LLM-Aufruf (Haiku). TECHINT, CYBER, ENERGY, CIVIL_UNREST, DIPLO sind ohnehin regelbasiert.
- **Supervisor:** **Ein** LLM-Aufruf (Haiku/Sonnet) nach den **11** Agent-Ergebnissen. Der Supervisor ist darauf vorbereitet, dass die Agent-Daten aus regelbasierten Ketten stammen; er synthetisiert aus Scores und Rohdaten (articles, aircraft, anomalies, sanctions, civil unrest events, proximity evidence, etc.) zu key_findings, scenarios und summary.
- **Ausgabeformat:** Frontend und API liefern zusätzlich `cyber`, `energy`, `civil unrest`, `diplo`, `proximity` im Analyse-Ergebnis.

---

## 1. Pipeline-Ebene (Supervisor)

**Ablauf:** `collection_node` → alle **11** Agents **parallel** (ThreadPoolExecutor) → `supervisor_node` (Claude Haiku/Sonnet).

| Schritt | Reihenfolge | Beschreibung |
|--------|--------------|--------------|
| 1 | **Parallel** | Alle 11 Agents werden gleichzeitig gestartet (Reihenfolge der Submission ist fest, Ausführung parallel): |
|   | 1. FININT  | `run_finint_agent(conflict)` |
|   | 2. SIGINT  | `run_sigint_agent(conflict)` |
|   | 3. NEWS    | `run_news_agent(conflict)` |
|   | 4. GEOINT | `run_geoint_agent(conflict)` |
|   | 5. SOCMINT| `run_socmint_agent(conflict)` |
|   | 6. TECHINT| `run_techint_agent(conflict)` |
|   | 7. CYBER  | `run_cyber_agent(conflict)` |
|   | 8. ENERGY | `run_energy_agent(conflict)` |
|   | 9. CIVIL_UNREST| `run_civil unrest_agent(conflict)` |
|   | 10. DIPLO | `run_diplo_agent(conflict)` |
|   | 11. PROXIMITY | `run_proximity_agent(conflict)` |
| 2 | **Sequentiell** | Sobald alle 11 Ergebnisse da sind: `supervisor_node` (Claude Haiku/Sonnet) synthetisiert. |

Die **Reihenfolge der Agent-Ausführung** ist also: FININT, SIGINT, NEWS, GEOINT, SOCMINT, TECHINT, CYBER, ENERGY, CIVIL_UNREST, DIPLO, PROXIMITY (Submission); sie laufen parallel. Danach genau **ein** Supervisor-Aufruf.

---

## 2. Pro Agent: LLM-Pfad vs. Fallback (Tool-Kette)

Jeder Agent hat entweder:
- **LLM-Pfad:** Haiku entscheidet, welche Tools in welcher Reihenfolge aufgerufen werden (bis zu 5–6 Runden).
- **Fallback:** Feste Tool-Reihenfolge, keine LLM-Aufrufe (außer TECHINT, siehe unten).

Die **Fallback-Reihenfolge** ist die fest verdrahtete Tool-Kette, die du für ein regelbasiertes System nutzen kannst.

---

### FININT

- **Tools (Definition):** get_brent_price, get_wti_price, get_gold_price, get_polymarket_conflict_odds, get_metaculus_conflict_questions, get_ofac_sanctions_highlights, get_tracked_wallet_positions, get_tracked_chain_wallets
- **Fallback-Reihenfolge (fest):** Alle genannten Tools parallel (ThreadPoolExecutor).
- Danach: Score und Ergebnis (inkl. ofac_sanctions für Märkte/Sanktionen).

---

### SIGINT

- **Tools:** get_military_aircraft, get_naval_vessels, get_conflict_reports; zusätzlich NOTAMs via `iaea_tracker.fetch_notams`.
- **Fallback-Reihenfolge (fest):** aircraft → vessels → conflict_reports → NOTAMs (fetch_notams, days=3, limit=15).
- Danach: Score aus aircraft/ships/reports, Alerts; `notams` im Ergebnis (optional NOTAM_API_KEY für Autorouter).

---

### NEWS

- **Tools:** `NEWS_TOOLS = [search_conflict_news, search_gdelt_news, search_rss_feeds]`
- **Fallback-Reihenfolge (fest):**
  1. `search_conflict_news.invoke({"conflict": conflict, "hours_back": 48})`
  2. `search_gdelt_news.invoke({"conflict": conflict})`
  3. `search_rss_feeds.invoke({"conflict": conflict})`
- Danach: `_merge_news_results(newsapi_ok, gdelt_ok, rss_ok)`, Score und Summary.

---

### GEOINT

- **Tools:** `GEOINT_TOOLS = [get_conflict_region, get_thermal_anomalies, get_conflict_hotspot_news, get_eo_browser_links]`
- **Fallback-Reihenfolge (fest):**
  1. `get_conflict_region.invoke({"conflict": conflict})` → Region-String (z. B. `"middle_east"`)
  2. `get_thermal_anomalies.invoke({"region": region, "days": 3})`
  3. `get_conflict_hotspot_news.invoke({"conflict": conflict})`
  4. `get_eo_browser_links.invoke({"conflict": conflict})` → Sentinel Hub EO Browser URLs (Lebanon, Iran, …); kein API-Key nötig
- Danach: `_compute_geoint_score`, Hotspots, ReliefWeb-Reports, `eo_browser_links`.
- **Sentinel Hub:** EO Browser-Links sind integriert; voller Process API-Zugriff optional über `SENTINELHUB_CLIENT_ID` / `SENTINELHUB_CLIENT_SECRET` (siehe Doku).

---

### SOCMINT

- **Tools:** `SOCMINT_TOOLS = [scrape_telegram_channels, scrape_twitter_nitter, search_reddit, fetch_rss_feeds, fetch_reliefweb_reports]`
- **Fallback-Reihenfolge (fest):**
  1. `scrape_telegram_channels.invoke({"conflict": conflict})`
  2. `scrape_twitter_nitter.invoke({"conflict": conflict})`
  3. `search_reddit.invoke({"conflict": conflict})`
  4. `fetch_rss_feeds.invoke({"conflict": conflict})`
  5. `fetch_reliefweb_reports.invoke({"conflict": conflict})`
- Danach: Aggregation, Sentiment, Score, `top_signals`.

---

### TECHINT (bereits vollständig regelbasiert, kein LLM)

- Interne async Funktionen in fester Reihenfolge (kein externes Tool-Framework):
  1. `_fetch_tech_indicators(av_key)` (wenn ALPHAVANTAGE_API_KEY)
  2. `_fetch_export_control_news(news_key, conflict)` (wenn NEWS_API_KEY)
  3. `_fetch_ioda_all(conflict)` – IODA v2 API: outages/events, signals/raw (BGP/Ping/Telescope), alerts, entities/query (ASNs)
  4. `_fetch_ooni_measurements(conflict)`
  5. `_fetch_cloudflare_outages(cf_token, conflict)` (wenn CLOUDFLARE_RADAR_API_TOKEN)
  6. `_fetch_shodan_activity(shodan_key, conflict)` (wenn SHODAN_API_KEY)
  7. `_fetch_wayback_snapshots(conflict)` – Archive.org CDX: Snapshot-Count und letzte Erfassung pro URL (kein Key nötig)
- Danach: `_compute_techint_score`, `_build_summary`. Kein Claude-Aufruf in TECHINT.

---

### CYBER (Threat Intel, regelbasiert, kein LLM)

- **Interne async Funktionen:**
  1. `_fetch_cisa_kev()` – CISA Known Exploited Vulnerabilities (kostenlos, kein Key)
  2. `_fetch_threat_rss(conflict)` – Mandiant/CrowdStrike RSS, gefiltert nach Konflikt-Keywords
  3. `_fetch_otx_pulses(api_key, conflict)` – AlienVault OTX (optional `OTX_API_KEY`)
  4. `_fetch_greynoise_scan_context(api_key)` – GreyNoise GNQL Stats: malicious scanners (7d), top actors/countries (optional `GREYNOISE_API_KEY`)
- Danach: `_compute_cyber_score`, `_build_summary`. Ausgabe: `cyber_score`, `cisa_kev`, `threat_reports`, `otx_pulses`, `greynoise_scan_context`.

---

### ENERGY (Commodities, regelbasiert, kein LLM)

- **Interne async Funktionen:**
  1. `_fetch_agsi_storage(api_key)` – EU-Gasspeicher (AGSI+), optional `AGSI_API_KEY`
  2. `_fetch_commodity_prices(api_key)` – Brent/WTI über Alpha Vantage (optional `ALPHAVANTAGE_API_KEY`)
- Danach: `_compute_energy_score`, `_build_summary`. Ausgabe: `energy_score`, `agsi_storage`, `commodities`.

---

### CIVIL_UNREST (Civil Society, regelbasiert, kein LLM)

- **Interne async Funktionen:**
  1. `_fetch_acled_civil unrest events(api_key, conflict)` – ACLED mit event_type Protests/Riots (optional `ACLED_API_KEY`)
  2. `_fetch_gdelt_civil unrest(conflict)` – GDELT Doc API für Protest-Artikel (kostenlos)
- Danach: `_compute_civil unrest_score`, `_build_summary`. Ausgabe: `civil unrest_score`, `civil unrest_events`, `civil unrest_articles`.

---

### DIPLO (Diplomatie/Recht, regelbasiert, kein LLM)

- **Interne async Funktionen:**
  1. `_fetch_ofac_sdn(conflict)` – OFAC SDN CSV (kostenlos), gefiltert nach Konflikt-Keywords
  2. `_fetch_eu_sanctions(conflict)` – EU Consolidated List (Open Data)
  3. `_fetch_un_icj_news(conflict)` – UN Press RSS, ICJ RSS, gefiltert nach Konflikt
- Danach: `_compute_diplo_score`, `_build_summary`. Ausgabe: `diplo_score`, `ofac_sdn`, `eu_sanctions`, `un_icj_news`.

---

### PROXIMITY (Strike–Civilian / Human-Shield, regelbasiert, kein LLM)

- **Ablauf:** Konflikt → Region (z. B. Iran → iran); NASA FIRMS Thermal-Anomalien (GEOINT-Tool `get_thermal_anomalies`), optional Tunnel/Militär-GeoJSON (`TUNNEL_SITES_GEOJSON_URL`), dann `run_correlation_for_events` (Overpass: Schulen/Krankenhäuser/Regierung in 300 m; Human-Shield-Flag wenn Militärstandort nahe).
- **Shared Service:** `services.proximity_correlation` (von API-Route `/api/proximity/analyze` und PROXIMITY-Agent genutzt).
- Ausgabe: `proximity_score`, `evidence` (Liste mit riskLabel, facilityName, distanceMeters, summary), `summary`.

---

## 3. Kurzüberblick für feste Tool-Kette

| Agent  | Anzahl/Quellen | Feste Reihenfolge (Fallback) |
|--------|----------------|-------------------------------|
| FININT | 8             | get_brent_price → get_wti_price → get_gold_price → get_polymarket_conflict_odds → get_metaculus_conflict_questions → get_ofac_sanctions_highlights → get_tracked_wallet_positions → get_tracked_chain_wallets (parallel) |
| SIGINT | 3       | get_military_aircraft → get_naval_vessels → get_conflict_reports |
| NEWS   | 3       | search_conflict_news → search_gdelt_news → search_rss_feeds |
| GEOINT | 4       | get_conflict_region → get_thermal_anomalies → get_conflict_hotspot_news → get_eo_browser_links |
| SOCMINT| 5       | scrape_telegram_channels → scrape_twitter_nitter → search_reddit → fetch_rss_feeds → fetch_reliefweb_reports |
| TECHINT| 7 (intern) | _fetch_tech_indicators → _fetch_export_control_news → _fetch_ioda_events → _fetch_ooni_measurements → _fetch_cloudflare_outages → _fetch_shodan_activity → _fetch_wayback_snapshots |
| CYBER  | 4 (intern) | _fetch_cisa_kev → _fetch_threat_rss → _fetch_otx_pulses → _fetch_greynoise_scan_context |
| ENERGY | 2 (intern) | _fetch_agsi_storage → _fetch_commodity_prices |
| CIVIL_UNREST| 2 (intern) | _fetch_acled_civil unrest events → _fetch_gdelt_civil unrest |
| DIPLO  | 3 (intern) | _fetch_ofac_sdn → _fetch_eu_sanctions → _fetch_un_icj_news |
| PROXIMITY | 3 (intern) | get_thermal_anomalies(region) → optional tunnel GeoJSON → run_correlation_for_events (Overpass) |

**Supervisor:** 1× Claude Haiku/Sonnet nach den 11 Agent-Ergebnissen.

Um ein **regelbasiertes System** zu bauen: Pro Agent den **Fallback-Pfad** als Standard nutzen (Tools in dieser Reihenfolge aufrufen, dann die bestehende Score-/Aggregationslogik). So kannst du jeden Agent fest in die Tool-Kette verdrahten und die Haiku-Aufrufe in den Agents weglassen.
