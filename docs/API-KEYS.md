# API-Keys – Übersicht & Bezugsquellen

Alle in der Digital-War-Room-Plattform verwendeten Umgebungsvariablen (API-Keys), wo sie im Code genutzt werden und **wo du die Keys bekommst**.

---

## Pflicht (für volle Analyse)

| Key | Verwendung im Code | Bezugsquelle |
|-----|---------------------|--------------|
| **ANTHROPIC_API_KEY** oder **OPENAI_API_KEY** | `backend/agents/llm_factory.py` – Supervisor (LLM-Synthese) | **Anthropic:** [console.anthropic.com](https://console.anthropic.com/) → API Keys. **OpenAI:** [platform.openai.com/api-keys](https://platform.openai.com/api-keys). |
| **NEWS_API_KEY** | `backend/agents/news_agent.py` | [newsapi.org/register](https://newsapi.org/register) – kostenloser Plan. **Free:** 100 Requests/Tag, keine Zusatz-Requests; Artikel haben **24h Verzögerung** (kein Echtzeit); Suche bis 1 Monat zurück; kein Uptime-SLA; Basic-Support; CORS für localhost. |
| **NASA_FIRMS_KEY** | `backend/agents/geoint_agent.py` (NASA FIRMS) | [firms.modaps.eosdis.nasa.gov](https://firms.modaps.eosdis.nasa.gov/) → „Request Key“ (kostenlos). |
| **ALPHAVANTAGE_API_KEY** | `backend/agents/finint_agent.py`, `energy_agent.py`, `techint_agent.py` | [alphavantage.co/support/#api-key](https://www.alphavantage.co/support/#api-key) – kostenloser Key. Wird für Öl (Brent, WTI) und Food-Commodities (Wheat, Corn, Soybean) genutzt. |

---

## Optional – Hugging Face & Haiku (Embeddings, Ranking, Translation)

| Key | Verwendung im Code | Bezugsquelle |
|-----|---------------------|--------------|
| **HUGGINGFACE_API_KEY** | `backend/services/hf_service.py` – Embeddings (Deduplizierung), Cross-Encoder (Relevanz-Ranking), später NER-Bulk, Document QA, OCR, CLIP | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) – **Free Tier** reicht für Phase 1–4 (Embeddings, Cross-Encoder, NER-Bulk). Ab Phase 5 (CV/Bilder): **HF Pro** ($9/Monat) empfohlen. |
| **HAIKU_MODEL** | `backend/services/haiku_service.py` – Modell für Translation, Sentiment, NER, Classification | Default: `claude-haiku-4-5-20251001`. Nutzt den bestehenden **ANTHROPIC_API_KEY** (kein separater Key nötig). |
| **HAIKU_MONTHLY_BUDGET** | `backend/services/haiku_service.py` – Monatliches Budget-Limit in USD | Default: `20.0`. Warnung bei 80 %. Budget wird anhand echter `usage.input_tokens` / `usage.output_tokens` aus der API-Response getrackt. |
| **RANKING_QUERY_IRAN** | `backend/services/hf_service.py` – Cross-Encoder Ranking-Query für Iran-Konflikt | Default: `Iran nuclear sanctions military IRGC`. Konfigurierbares Profil pro Konflikt: `RANKING_QUERY_<KONFLIKT>` (z. B. `RANKING_QUERY_UKRAINE`). Fallback: `conflict`-String. |
| **DATABASE_URL** | `backend/services/storage_service.py` – pgvector-Anbindung für persistente Embeddings und DB-Similarity | Railway PostgreSQL URL (Format: `postgresql://user:pass@host:5432/dbname`). Migration: `backend/migrations/001_pgvector_setup.sql`. Ohne DATABASE_URL: In-Memory-Only (Phase 1–2 Verhalten). |
| **CLASSIFY_CONFIDENCE_THRESHOLD** | `backend/agents/supervisor.py` – Schwellenwert für Zero-Shot Pre-Filter | Default: `0.3`. Items mit Kategorie "other" und Confidence unter diesem Wert werden vor der Synthese gefiltert. |
| **SUMMARIZE_CHAR_THRESHOLD** | `backend/agents/supervisor.py` – Zeichenlänge ab der Texte zusammengefasst werden | Default: `600`. Artikel/Posts mit längerem Text werden per Haiku auf 2–4 Sätze kondensiert. |
| **HF_DOC_QA_MODEL** | `backend/services/hf_service.py` – HF-Modell für extractive Document QA | Default: `deepset/roberta-base-squad2`. Extractive QA als Fallback zu Haiku Document QA. |
| **PDF_CHUNK_SIZE** | `backend/services/pdf_ingest_service.py` – Zeichenlänge pro PDF-Chunk | Default: `800`. Steuert Chunk-Granularität für Document QA. |
| **HAIKU_MAX_DOCQA_PER_RUN** | `backend/services/haiku_service.py` – Max. Document QA Calls pro 6h-Lauf | Default: `10`. Begrenzt teure Haiku-DocQA-Calls. |

---

### API-Endpunkte (Phase 4: Document QA)

| Endpunkt | Methode | Beschreibung |
|----------|---------|-------------|
| `/api/documents/ingest` | POST | PDF-URL ingestieren: Download → Text-Extraktion → Chunking → Embedding → Speicherung. Body: `{"url": "...", "source": "ofac", "conflict": "Iran"}` |
| `/api/documents` | GET | Alle ingestierten Dokumente auflisten (doc_id, URL, Chunk-Count, etc.) |
| `/api/documents/qa` | POST | Frage über PDF-Chunks beantworten. Body: `{"question": "...", "source": "ofac", "conflict": "Iran"}`. Nutzt Haiku (primary) oder HF extractive QA (Fallback). |

---

## Optional (neue Agents: CYBER, ENERGY, PROTEST, DIPLO)

| Key | Verwendung im Code | Bezugsquelle |
|-----|---------------------|--------------|
| **OTX_API_KEY** | `backend/agents/cyber_agent.py` – AlienVault OTX (Threat Intel) | [otx.alienvault.com](https://otx.alienvault.com/) → Sign Up → Einstellungen (Avatar) → API Key. Kostenlos. |
| **GREYNOISE_API_KEY** | `backend/agents/cyber_agent.py` (Scan-Kontext), `backend/agents/greynoise_agent.py` (Emerging Threats: GNQL Stats, CVE Lookup, Tags API) | [greynoise.io](https://www.greynoise.io/) → Account → API Key. VIP Researcher Community Access empfohlen für GNQL Stats + CVE-Endpunkte. Scheduler läuft alle 6h (konfigurierbar via `GREYNOISE_SCHEDULER_INTERVAL_SEC`). Konflikte: `GREYNOISE_CONFLICTS` (Default: `Iran,Israel,USA,UAE,Saudi Arabia,Lebanon,Jordan,Gaza/Israel,Yemen,Middle East`). **Iran-Konflikt:** Es werden zusätzlich getrackt: Iran, Iraq, Syria, Lebanon; Gulf (UAE, Bahrain, Qatar, Kuwait, Oman); Saudi Arabia, Jordan; Turkey, Pakistan, Azerbaijan, Afghanistan (siehe `GREYNOISE_COUNTRY_FILTERS` in `greynoise_agent.py`). |
| **AGSI_API_KEY** | `backend/agents/energy_agent.py` – EU-Gasspeicher (AGSI+) | [agsi.gie.eu/account](https://agsi.gie.eu/account) – Registrierung (kostenlos). Key nach Login in der API-Doku. |
| **EIA_API_KEY** | `backend/agents/chokepoint_agent.py` (EIA Baseline), `backend/agents/energy_agent.py` (Brent/WTI Spot, täglich) | [eia.gov/opendata/register](https://www.eia.gov/opendata/register.php) – kostenlos. Chokepoint: Baseline; Energy: PET.RBRTE.D, PET.RWTC.D. Ohne Key: Fallback FRED oder Alpha Vantage. |
| **FRED_API_KEY** | `backend/agents/energy_agent.py` – FRED (Federal Reserve): Öl DCOILBRENTEU/DCOILWTICO (täglich), Food PWHEAMTUSDM/PMAIZMTUSDM/PSOYBUSDM (monatlich) als Fallback | [fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html) – kostenloser Key. Wird genutzt wenn EIA für Öl fehlt; Food primär über FRED, sonst Alpha Vantage. |
| **ACLED_EMAIL** | `backend/agents/protest_agent.py`, `geoint_agent.py`, `services/acled_auth.py` | Deine myACLED-Registrierungs-E-Mail. **OAuth (empfohlen):** zusammen mit `ACLED_PASSWORD` für Token-Auth. |
| **ACLED_PASSWORD** | `backend/services/acled_auth.py` – OAuth Token-Abruf | Dein myACLED-Passwort. Mit `ACLED_EMAIL` erhält die App ein Zugangs-Token (24h gültig) gemäß [ACLED API Getting started](https://acleddata.com/api-documentation/getting-started). |
| **ACLED_API_KEY** | (Legacy) Falls ACLED noch einen API-Key anbietet | Optional; primär wird **OAuth (ACLED_EMAIL + ACLED_PASSWORD)** genutzt. |

**Ohne ACLED-API:** Auf der ACLED-Webseite gibt es öffentlich einsehbare Crisis-Live-Daten, z. B. **[Iran Crisis Live](https://acleddata.com/iran-crisis-live)** – tägliche Updates, Karten und Analysen zum Iran-Konflikt (täglich 10:30 EST / 15:30 CET). Für die Plattform-Heatmap und PROTEST-Events wird weiterhin ein API-Key benötigt; die Webseite eignet sich als manuelle Ergänzung.

**DIPLO** benötigt **keine** Keys (OFAC, EU-Liste, UN/ICJ-RSS sind öffentlich).

---

## Weitere optionale Keys (bestehende Agents)

| Key | Verwendung im Code | Bezugsquelle |
|-----|---------------------|--------------|
| **POLYMARKET_BUILDER_API_KEY** | `backend/agents/finint_agent.py` – Polymarket (höhere Limits) | [polymarket.com](https://polymarket.com/) – Builder/API-Zugang. |
| **METALS_API_KEY** | `backend/agents/finint_agent.py` – Gold (XAU) Preis (metals-api.com) | [metals-api.com](https://metals-api.com/) – Registrierung, Free Tier. |
| **ETHEREUM_ETHERSCAN_API_KEY** | `backend/agents/finint_agent.py` – On-Chain-Wallets (Etherscan) | [etherscan.io/myapikey](https://etherscan.io/myapikey) – **Free Tier:** 3 calls/s, bis 100.000 Calls/Tag, **Attribution erforderlich** (z. B. „Data by Etherscan“ im UI). Nur ausgewählte Chains/Community-Endpoints; 90 % Multichain-Abdeckung. |
| **SHODAN_API_KEY** | `backend/agents/techint_agent.py` – Shodan Host-Counts | [account.shodan.io](https://account.shodan.io/) – Registrierung, API Key im Dashboard. |
| **CLOUDFLARE_RADAR_API_TOKEN** | `backend/agents/techint_agent.py` – Outage-Annotations | [dash.cloudflare.com](https://dash.cloudflare.com/) → Radar / API. |
| **WIGLE_API_TOKEN** (und optional **WIGLE_API_NAME**) | `backend/agents/techint_agent.py` – Wigle.net WLAN-Datenbank (TECHINT) | [wigle.net](https://wigle.net/) – Account, API-Token im Profil. Entweder nur **WIGLE_API_TOKEN** = `username:token`, oder **WIGLE_API_NAME** + **WIGLE_API_TOKEN** getrennt. |
| **SPIRE_MARITIME_API_KEY** | `backend/agents/sigint_agent.py`, `chokepoint_agent.py` – Spire Maritime (Schiffe/AIS, Tanker in Chokepoints) | [spire.com](https://spire.com/) – Maritime API. Alternativ **SPIRE_API_KEY**. Optional: **SPIRE_MARITIME_BASE_URL** (Default: `https://api.sense.spire.com`). |
| **SPIRE_AIRSAFE_TOKEN** | `backend/agents/sigint_agent.py` – Spire Airsafe (Flugzeug-Tracking) | [api.airsafe.spire.com](https://api.airsafe.spire.com) – Bearer Token. Endpoint: `/v2/targets/stream` (Batch mit start/end). Alternativ: **SPIRE_API_KEY** falls ein Token für alle Spire-APIs. |
| **AISHUB_USERNAME** | `backend/agents/chokepoint_agent.py` – AISHub (Community-AIS, Tanker-Dichte) | [aishub.net](https://www.aishub.net/) – kostenloser Account, Username für API. Ohne Key: Chokepoint nutzt EIA-Baseline + News-Signale (data_quality: estimated/baseline_only). |
| **AIRSTREAM_API_KEY** | `backend/agents/chokepoint_agent.py` – AISStream (aisstream.io), WebSocket-Echtzeit-AIS mit BoundingBox (Hormuz, Bab el-Mandeb, Suez) | [aisstream.io/apikeys](https://aisstream.io/apikeys). Doku: [aisstream.io/documentation](https://aisstream.io/documentation). Optional: **AIRSTREAM_COLLECT_SECONDS** (Default 15). |
| **MARINETRAFFIC_API_KEY** | `backend/agents/chokepoint_agent.py` – MarineTraffic (Area-Queries, Schiffstypfilter) | [marinetraffic.com](https://www.marinetraffic.com/en/ais-api-services) – Basic-Tier ca. 15 $/Monat. Ohne Key: Fallback auf AISHub/Spire oder Baseline. |
| **ADSBEXCHANGE_RAPIDAPI_KEY** | `backend/agents/sigint_agent.py` – ADSBexchange via RapidAPI | [RapidAPI: ADSBexchange](https://rapidapi.com/adsbx/api/adsbexchange-com1). **Nutzung:** (1) **Militärflugzeug-Liste:** 4 Regionen × 2 Kreise (100 nm) = 8 Requests, merge mit adsb.fi/adsb.lol. (2) **Tracked Targets:** Abfrage per **Callsign** (`/api/aircraft/call/{callsign}`), dann ICAO, dann Region-Scan. Host optional: **ADSBEXCHANGE_RAPIDAPI_HOST**. Ziele: `TARGET_AIRCRAFT` bzw. **TARGET_AIRCRAFT_EXTRA**, pro Ziel optional **TARGET_&lt;NAME&gt;_HEX**. **Kostenanalyse siehe unten.** |
| **UCDP_API_TOKEN** | `backend/agents/geoint_agent.py` – Uppsala Conflict Data Program (GED events) | Bei UCDP anfragen ([ucdp.uu.se](https://ucdp.uu.se/), [API-Doku](https://ucdp.uu.se/apidocs/)). Header: `x-ucdp-access-token`. **Limit:** 5.000 Requests/Tag (Mitternacht UTC); jeder paginierte Request zählt. |
| **LIVEUAMAP_API_KEY** | GEOINT (Liveuamap, falls integriert) | Liveuamap – oft kostenpflichtig. |
| **NOTAM_API_KEY** | `backend/agents/iaea_tracker.py` – NOTAM (Autorouter.aero) | [autorouter.aero](https://www.autorouter.aero/) – falls der Endpunkt Auth verlangt. |
| **NEWSDATA_API_KEY** | `backend/agents/news_agent.py` – NewsData.io (zusätzliche News-Quelle) | [newsdata.io/register](https://newsdata.io/register). **Free:** 200 API-Credits/Tag, max. 10 Artikel pro Request. Filter: Location (`country`), Language (`language`), Category (`category`). Pro Request 1 Credit (Latest); sinnvoll: ein Request pro Lauf, Query über Konflikt-Keywords. |
| **GNEWS_API_KEY** | `backend/agents/news_agent.py` – GNews (gnews.io) | [gnews.io/register](https://gnews.io/register). **Free:** 100 Requests/Tag. Search-Endpoint: `q`, `lang`, `country`, `max` (bis 10). Ein Request pro Lauf empfohlen. |
| **FIRECRAWL_API_KEY** | `acled_reference.py` – ACLED-Referenzseiten; `signal_framework_agent.py` – optional Fallback für State-RSS (IRNA, Fars, etc.), wenn `SIGNAL_FRAMEWORK_USE_FIRECRAWL=true` | [firecrawl.dev](https://firecrawl.dev) – Free Plan: 500 Credits einmalig, 2 gleichzeitige Requests. Ohne Key: Fallback auf httpx bzw. kein State-Fallback. |
| **SIGNAL_FRAMEWORK_USE_FIRECRAWL** | `signal_framework_agent.py` – bei `true`: nach fehlgeschlagenem/leerem State-RSS Firecrawl als Fallback nutzen | Optional. Erfordert `FIRECRAWL_API_KEY`. State-Feed-URL wird per Firecrawl geladen; Headlines werden aus Markdown extrahiert. |
| **SIGNAL_FRAMEWORK_STATE_TIMEOUT** | `signal_framework_agent.py` – Timeout in Sekunden für State-Feed-Requests | Optional, Default 25. Erhöhen, wenn State-Server langsam antworten. |

---

## News-APIs gemeinsam einsetzen (NEWS_API_KEY, NEWSDATA_API_KEY, GNEWS_API_KEY)

Der NEWS-Agent nutzt alle gesetzten Keys **parallel** in einem Lauf; pro API wird **genau ein Request** ausgeführt, um die Tageslimits nicht zu überschreiten.

| API | Key | Limit (Free) | Pro Lauf | Empf. max. Runs/Tag |
|-----|-----|--------------|----------|----------------------|
| NewsAPI.org | NEWS_API_KEY | 100 Requests/Tag, 24h Artikel-Verzögerung | 1 Request | ≤ 100 (z. B. alle 15 Min = 96) |
| NewsData.io | NEWSDATA_API_KEY | 200 Credits/Tag, 10 Artikel/Request | 1 Request | ≤ 200 |
| GNews (gnews.io) | GNEWS_API_KEY | 100 Requests/Tag | 1 Request | ≤ 100 |

**Strategie im Code** ([backend/agents/news_agent.py](backend/agents/news_agent.py)):

1. **Paralleler Abruf:** NewsAPI, GDELT, RSS und – falls Key gesetzt – NewsData und GNews laufen gleichzeitig im `ThreadPoolExecutor` (ein Aufruf pro Quelle).
2. **Einheitliche Query:** Alle APIs erhalten dieselbe konfliktbezogene Suchanfrage aus `_build_query(conflict)` (z. B. Iran: IRGC, Persian Gulf, sanctions, …; Ukraine: Zelensky, Donbas, Russia, …). So bleiben die Ergebnisse vergleichbar und Duplikate können sauber erkannt werden.
3. **Merge & Deduplizierung:** Alle Artikel werden nach URL zusammengeführt und dedupliziert; danach semantische Deduplizierung (HF) und Relevanz-Ranking (Cross-Encoder). Pro Quelle gilt ein Cap (z. B. max. 5 Artikel pro Outlet), damit eine Quelle die Liste nicht dominiert.
4. **Gewichtung:** NewsAPI 35 %, GDELT 25 %, RSS 20 %, NewsData 10 %, GNews 10 %. Sentiment wird gewichtet gemischt; bei Ausfall einer API liefern die anderen weiter.
5. **Frische:** NewsAPI hat 24 h Verzögerung; GDELT, RSS, NewsData und GNews liefern oft aktuellere Artikel und gleichen das aus.

**Empfehlung:** Alle drei Keys setzen, wenn verfügbar. Scheduler so wählen, dass pro Tag nicht mehr als 100 NEWS-Läufe ausgeführt werden (z. B. alle 15–30 Minuten), damit NewsAPI und GNews im Limit bleiben. NewsData erlaubt bis 200 Läufe/Tag.

---

## ADSBexchange RapidAPI – Kostenanalyse für dieses Projekt

| Faktor | Wert in diesem Projekt |
|--------|-------------------------|
| **Aufrufer** | (1) `get_military_aircraft`: **8** Region-Requests (4 Regionen × 2 Kreise). (2) `get_target_aircraft` pro Ziel: Callsign-Lookups, ggf. ICAO, ggf. mehrere Region-Scans. |
| **Requests pro Lauf** | **ca. 8–20+** (8 für Militärliste + 1–4 pro Tracked Target je nach Treffer). |
| **Automatische Läufe** | `main.py`: periodische Analyse alle **6 h** (Default `AUTO_ANALYZE_INTERVAL_SEC=21600`). → **4 Läufe/Tag** ≈ **120 Läufe/Monat**. |
| **Manuelle/API-Läufe** | `/api/analyze/refresh`, Trigger, Sync – je nach Nutzung grob **0–50** zusätzliche Läufe/Monat. |
| **RapidAPI-Requests/Monat** | **~120–350** (bei 6-h-Intervall + wenig manuell). Selbst bei 1-h-Intervall: ≈ 720–1 500. |

**Basic-Plan (10 $/Monat, 10 000 Requests):** Für dieses Projekt **deutlich überdimensioniert** – du bleibst fast immer unter 500–1 500 Requests/Monat. Das Limit ist also kein Entscheidungskriterium.

**Lohnt sich der Plan trotzdem?**  
- **Ja**, wenn du **stabile, ungefilterte** ADSBexchange-Daten für OE-III (oder andere Ziele) willst und adsb.fi/adsb.lol im Betrieb zu oft ausfallen oder filtern.  
- **Nein**, wenn du erst testest oder die kostenlosen Quellen (adsb.fi, adsb.lol, ggf. direkter ADSBX-Key) ausreichen. Ohne `ADSBEXCHANGE_RAPIDAPI_KEY` nutzt der Code automatisch die Fallbacks.

**Empfehlung:** Zuerst **ohne** RapidAPI-Key betreiben. OE-III wird nun zuerst per **kostenloser** Registration-Abfrage (adsb.fi, adsb.lol) und Regions-Scan (Wien, Ost-Mittelmeer, Golf) ermittelt; RapidAPI/ADSBX dienen als Verstärkung. Für noch bessere Trefferquote **OEIII_HEX** in `.env` setzen (ICAO-Hex der Maschine), falls bekannt.

---

## Observability (OpenTelemetry / Jaeger)

| Key / Env | Verwendung im Code | Beschreibung |
|-----------|---------------------|--------------|
| **OTEL_EXPORTER_OTLP_ENDPOINT** | `backend/agents/otel_callbacks.py`, `main.py` | Wenn gesetzt: Traces (LangChain/LangGraph: LLM, Tools, Chains) werden per OTLP (gRPC) an diesen Endpoint gesendet. Z. B. `http://localhost:4317` für lokales Jaeger. Kein API-Key nötig für Jaeger. |
| **OTEL_SERVICE_NAME** | `backend/agents/otel_callbacks.py` | Optional; Service-Name in Traces (Default: `digital-war-room`). |

**LangSmith** ist standardmäßig aus (`LANGCHAIN_TRACING_V2=false`). Für LangSmith: `LANGCHAIN_TRACING_V2=true` und `LANGCHAIN_API_KEY` setzen (siehe [LangSmith](https://smith.langchain.com/)).

---

## Wo die Keys eintragen

- **Lokal:** `backend/.env` (nicht committen). Vorlage: `backend/.env.example` (Keys leer/auskommentiert).  
- **Produktion:** Railway (Backend) → Variables; Vercel (Frontend) nur für `VITE_*` (z. B. `VITE_API_URL`, `VITE_SUPABASE_*`).

**Kurzfassung – Chokepoint & Food-Commodities:**  
- **Keine neuen Pflicht-Keys.** ALPHAVANTAGE_API_KEY (bereits Pflicht) deckt Öl + Wheat/Corn/Soy. FAO und World-Bank-Fertilizer laufen ohne Key.  
- **Optional für bessere Chokepoint-Daten:** `EIA_API_KEY` (kostenlos), `AISHUB_USERNAME` (kostenlos), `SPIRE_MARITIME_API_KEY` (falls schon für SIGINT), `MARINETRAFFIC_API_KEY` (kostenpflichtig). Ohne diese Keys nutzt der Chokepoint-Agent Baseline + News-Signale und setzt `data_quality` auf „estimated“ bzw. „baseline_only“.

Beispiel `backend/.env` (ohne echte Werte):

```env
# Pflicht (mind. eines für LLM)
ANTHROPIC_API_KEY=sk-ant-...
# oder: LLM_PROVIDER=openai  und  OPENAI_API_KEY=sk-...

# Pro Agent (siehe check_agents.py)
NEWS_API_KEY=...
NASA_FIRMS_KEY=...
ALPHAVANTAGE_API_KEY=...

# Optional – neue Agents
OTX_API_KEY=...
AGSI_API_KEY=...
# ACLED (OAuth – siehe acleddata.com/api-documentation/getting-started)
ACLED_EMAIL=deine@email.de
ACLED_PASSWORD=dein_myACLED_passwort

# Optional – Firecrawl (ACLED-Referenzseiten; ohne Key: Fallback auf httpx)
# FIRECRAWL_API_KEY=fc-...

# Optional – GEOINT: UCDP (Uppsala Conflict Data Program). Header: x-ucdp-access-token. Limit: 5.000 Requests/Tag.
# UCDP_API_TOKEN=...

# Optional – SIGINT: ADSBexchange via RapidAPI (Flugzeug-Tracking, z. B. OE-III). https://rapidapi.com/adsbx/api/adsbexchange-com1
# ADSBEXCHANGE_RAPIDAPI_KEY=...

# Optional – CHOKEPOINT / Maritime: Live-AIS für Tanker-Dichte (ohne Keys: Baseline + News-Signale)
# EIA_API_KEY=...                    # EIA – Persian Gulf Oil Export Baseline (kostenlos)
# AISHUB_USERNAME=...                 # AISHub – Community-AIS (kostenlos)
# MARINETRAFFIC_API_KEY=...           # MarineTraffic – Area-Queries (~15 $/Mo)
# SPIRE_MARITIME_API_KEY=...          # siehe SIGINT; wird auch von chokepoint_agent genutzt

# Optional – FININT: Gold, On-Chain-Wallets (TRACKED_ETH_ADDRESSES in finint_agent.py)
# METALS_API_KEY=...
# ETHEREUM_ETHERSCAN_API_KEY=...
```

**Energy/Food-Commodities:** FAO Food Price Index und World-Bank-Fertilizer (Urea/DAP) werden **ohne API-Key** per öffentlichem CSV bzw. World-Bank-API abgerufen. Für Öl und Getreide (Wheat, Corn, Soy) reicht **ALPHAVANTAGE_API_KEY** (bereits unter Pflicht gelistet).

**Etherscan Free Tier:** Max. 3 Requests/Sekunde (im Code durch Verzögerung zwischen Abfragen eingehalten), bis zu 100.000 Calls/Tag. **Attribution** ist vorgeschrieben – in der App z. B. „Data by Etherscan“ oder Link zu etherscan.io anzeigen. Die Antwort von `get_tracked_chain_wallets` enthält einen `_attribution`-Eintrag. Nur Community-Endpoints, ca. 90 % Multichain-Abdeckung.

Alle Key-Namen findest du auch per Suche im Repo: `os.getenv("KEY_NAME")` bzw. in `backend/scripts/check_agents.py` und `docs/DEPLOYMENT.md`.
