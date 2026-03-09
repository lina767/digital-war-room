# Agent- und Tool-Kette – Aufrufreihenfolge

Überblick für das regelbasierte System: Wo werden Agents/Tools in welcher Reihenfolge aufgerufen? (Stand: aktueller Code.)

---

## Regelbasierten Modus aktivieren

- **Umgebungsvariable:** `USE_RULE_BASED_AGENTS` ist standardmäßig `true`. Zum Deaktivieren: `USE_RULE_BASED_AGENTS=false`.
- **Wirkung:** Jeder Agent (FININT, SIGINT, NEWS, GEOINT, SOCMINT) führt seine **feste Tool-Kette** in der unten dokumentierten Reihenfolge aus – **ohne** LLM-Aufruf (Haiku). TECHINT, CYBER, ENERGY, PROTEST, DIPLO sind ohnehin regelbasiert.
- **Supervisor:** **Ein** LLM-Aufruf (Haiku/Sonnet) nach den **10** Agent-Ergebnissen. Der Supervisor ist darauf vorbereitet, dass die Agent-Daten aus regelbasierten Ketten stammen; er synthetisiert aus Scores und Rohdaten (articles, aircraft, anomalies, sanctions, protests, etc.) zu key_findings, scenarios und summary.
- **Ausgabeformat:** Frontend und API liefern zusätzlich `cyber`, `energy`, `protest`, `diplo` im Analyse-Ergebnis.

---

## 1. Pipeline-Ebene (Supervisor)

**Ablauf:** `collection_node` → alle **10** Agents **parallel** (ThreadPoolExecutor) → `supervisor_node` (Claude Haiku/Sonnet).

| Schritt | Reihenfolge | Beschreibung |
|--------|--------------|--------------|
| 1 | **Parallel** | Alle 10 Agents werden gleichzeitig gestartet (Reihenfolge der Submission ist fest, Ausführung parallel): |
|   | 1. FININT  | `run_finint_agent(conflict)` |
|   | 2. SIGINT  | `run_sigint_agent(conflict)` |
|   | 3. NEWS    | `run_news_agent(conflict)` |
|   | 4. GEOINT | `run_geoint_agent(conflict)` |
|   | 5. SOCMINT| `run_socmint_agent(conflict)` |
|   | 6. TECHINT| `run_techint_agent(conflict)` |
|   | 7. CYBER  | `run_cyber_agent(conflict)` |
|   | 8. ENERGY | `run_energy_agent(conflict)` |
|   | 9. PROTEST| `run_protest_agent(conflict)` |
|   | 10. DIPLO | `run_diplo_agent(conflict)` |
| 2 | **Sequentiell** | Sobald alle 10 Ergebnisse da sind: `supervisor_node` (Claude Haiku/Sonnet) synthetisiert. |

Die **Reihenfolge der Agent-Ausführung** ist also: FININT, SIGINT, NEWS, GEOINT, SOCMINT, TECHINT, CYBER, ENERGY, PROTEST, DIPLO (Submission); sie laufen parallel. Danach genau **ein** Supervisor-Aufruf.

---

## 2. Pro Agent: LLM-Pfad vs. Fallback (Tool-Kette)

Jeder Agent hat entweder:
- **LLM-Pfad:** Haiku entscheidet, welche Tools in welcher Reihenfolge aufgerufen werden (bis zu 5–6 Runden).
- **Fallback:** Feste Tool-Reihenfolge, keine LLM-Aufrufe (außer TECHINT, siehe unten).

Die **Fallback-Reihenfolge** ist die fest verdrahtete Tool-Kette, die du für ein regelbasiertes System nutzen kannst.

---

### FININT

- **Tools (Definition):** `FININT_TOOLS = [get_brent_price, get_wti_price, get_polymarket_conflict_odds, get_tracked_wallet_positions]`
- **Fallback-Reihenfolge (fest):**
  1. `get_brent_price.invoke({})`
  2. `get_wti_price.invoke({})`
  3. `get_polymarket_conflict_odds.invoke({"conflict": conflict})`
  4. `get_tracked_wallet_positions.invoke({})`
- Danach: Score und Ergebnis aus den Rohdaten berechnen (regelbasiert).

---

### SIGINT

- **Tools:** `SIGINT_TOOLS = [get_military_aircraft, get_naval_vessels, get_spire_vessels, get_conflict_reports]`
- **Fallback-Reihenfolge (fest):**
  1. `get_military_aircraft.invoke({})`  // region default "Middle East"
  2. `get_naval_vessels.invoke({})`
  3. `get_spire_vessels.invoke({})`  // Subagent: Spire Maritime AIS (optional SPIRE_MARITIME_API_KEY)
  4. `get_conflict_reports.invoke({"conflict": conflict})`
- Danach: Score aus aircraft/ships (inkl. Spire)/reports, Alerts bauen.

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

- **Tools:** `GEOINT_TOOLS = [get_conflict_region, get_thermal_anomalies, get_conflict_hotspot_news, get_ucdp_events, get_eo_browser_links]`
- **Fallback-Reihenfolge (fest):**
  1. `get_conflict_region.invoke({"conflict": conflict})` → Region-String (z. B. `"middle_east"`)
  2. `get_thermal_anomalies.invoke({"region": region, "days": 3})`
  3. `get_conflict_hotspot_news.invoke({"conflict": conflict})`
  4. `get_ucdp_events.invoke({"conflict": conflict})` → UCDP GED (Uppsala); optional `UCDP_API_TOKEN`
  5. `get_eo_browser_links.invoke({"conflict": conflict})` → Sentinel Hub EO Browser URLs (Lebanon, Iran, …); kein API-Key nötig
- Danach: `_compute_geoint_score`, Hotspots, ReliefWeb-Reports, `ucdp_events`, `eo_browser_links`.
- **UCDP:** https://ucdpapi.pcr.uu.se/api/gedevents/25.1 – Token bei API-Maintainer anfragen (x-ucdp-access-token).
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

- **Keine LangChain-Tools;** interne async Funktionen in fester Reihenfolge:
  1. `_fetch_tech_indicators(av_key)` (wenn ALPHAVANTAGE_API_KEY)
  2. `_fetch_export_control_news(news_key, conflict)` (wenn NEWS_API_KEY)
  3. `_fetch_ioda_events(conflict)`
  4. `_fetch_ooni_measurements(conflict)`
  5. `_fetch_cloudflare_outages(cf_token, conflict)` (wenn CLOUDFLARE_RADAR_API_TOKEN)
  6. `_fetch_shodan_activity(shodan_key, conflict)` (wenn SHODAN_API_KEY)
- Danach: `_compute_techint_score`, `_build_summary`. Kein Claude-Aufruf in TECHINT.

---

### CYBER (Threat Intel, regelbasiert, kein LLM)

- **Interne async Funktionen:**
  1. `_fetch_cisa_kev()` – CISA Known Exploited Vulnerabilities (kostenlos, kein Key)
  2. `_fetch_threat_rss(conflict)` – Mandiant/CrowdStrike RSS, gefiltert nach Konflikt-Keywords
  3. `_fetch_otx_pulses(api_key, conflict)` – AlienVault OTX (optional `OTX_API_KEY`)
- Danach: `_compute_cyber_score`, `_build_summary`. Ausgabe: `cyber_score`, `cisa_kev`, `threat_reports`, `otx_pulses`.

---

### ENERGY (Commodities, regelbasiert, kein LLM)

- **Interne async Funktionen:**
  1. `_fetch_agsi_storage(api_key)` – EU-Gasspeicher (AGSI+), optional `AGSI_API_KEY`
  2. `_fetch_commodity_prices(api_key)` – Brent/WTI über Alpha Vantage (optional `ALPHAVANTAGE_API_KEY`)
- Danach: `_compute_energy_score`, `_build_summary`. Ausgabe: `energy_score`, `agsi_storage`, `commodities`.

---

### PROTEST (Civil Society, regelbasiert, kein LLM)

- **Interne async Funktionen:**
  1. `_fetch_acled_protests(api_key, conflict)` – ACLED mit event_type Protests/Riots (optional `ACLED_API_KEY`)
  2. `_fetch_gdelt_protest(conflict)` – GDELT Doc API für Protest-Artikel (kostenlos)
- Danach: `_compute_protest_score`, `_build_summary`. Ausgabe: `protest_score`, `protest_events`, `protest_articles`.

---

### DIPLO (Diplomatie/Recht, regelbasiert, kein LLM)

- **Interne async Funktionen:**
  1. `_fetch_ofac_sdn(conflict)` – OFAC SDN CSV (kostenlos), gefiltert nach Konflikt-Keywords
  2. `_fetch_eu_sanctions(conflict)` – EU Consolidated List (Open Data)
  3. `_fetch_un_icj_news(conflict)` – UN Press RSS, ICJ RSS, gefiltert nach Konflikt
- Danach: `_compute_diplo_score`, `_build_summary`. Ausgabe: `diplo_score`, `ofac_sdn`, `eu_sanctions`, `un_icj_news`.

---

## 3. Kurzüberblick für feste Tool-Kette

| Agent  | Anzahl/Quellen | Feste Reihenfolge (Fallback) |
|--------|----------------|-------------------------------|
| FININT | 4             | get_brent_price → get_wti_price → get_polymarket_conflict_odds → get_tracked_wallet_positions |
| SIGINT | 4       | get_military_aircraft → get_naval_vessels → get_spire_vessels → get_conflict_reports |
| NEWS   | 3       | search_conflict_news → search_gdelt_news → search_rss_feeds |
| GEOINT | 5       | get_conflict_region → get_thermal_anomalies → get_conflict_hotspot_news → get_ucdp_events → get_eo_browser_links |
| SOCMINT| 5       | scrape_telegram_channels → scrape_twitter_nitter → search_reddit → fetch_rss_feeds → fetch_reliefweb_reports |
| TECHINT| 6 (intern) | _fetch_tech_indicators → _fetch_export_control_news → _fetch_ioda_events → _fetch_ooni_measurements → _fetch_cloudflare_outages → _fetch_shodan_activity |
| CYBER  | 3 (intern) | _fetch_cisa_kev → _fetch_threat_rss → _fetch_otx_pulses |
| ENERGY | 2 (intern) | _fetch_agsi_storage → _fetch_commodity_prices |
| PROTEST| 2 (intern) | _fetch_acled_protests → _fetch_gdelt_protest |
| DIPLO  | 3 (intern) | _fetch_ofac_sdn → _fetch_eu_sanctions → _fetch_un_icj_news |

**Supervisor:** 1× Claude Haiku/Sonnet nach den 10 Agent-Ergebnissen.

Um ein **regelbasiertes System** zu bauen: Pro Agent den **Fallback-Pfad** als Standard nutzen (Tools in dieser Reihenfolge aufrufen, dann die bestehende Score-/Aggregationslogik). So kannst du jeden Agent fest in die Tool-Kette verdrahten und die Haiku-Aufrufe in den Agents weglassen.
