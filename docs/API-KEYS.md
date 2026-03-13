# API-Keys – Übersicht & Bezugsquellen

Alle in der Digital-War-Room-Plattform verwendeten Umgebungsvariablen (API-Keys), wo sie im Code genutzt werden und **wo du die Keys bekommst**.

---

## Pflicht (für volle Analyse)

| Key | Verwendung im Code | Bezugsquelle |
|-----|---------------------|--------------|
| **ANTHROPIC_API_KEY** oder **OPENAI_API_KEY** | `backend/agents/llm_factory.py` – Supervisor (LLM-Synthese) | **Anthropic:** [console.anthropic.com](https://console.anthropic.com/) → API Keys. **OpenAI:** [platform.openai.com/api-keys](https://platform.openai.com/api-keys). |
| **NEWS_API_KEY** | `backend/agents/news_agent.py` | [newsapi.org/register](https://newsapi.org/register) – kostenloser Plan verfügbar. |
| **NASA_FIRMS_KEY** | `backend/agents/geoint_agent.py` (NASA FIRMS) | [firms.modaps.eosdis.nasa.gov](https://firms.modaps.eosdis.nasa.gov/) → „Request Key“ (kostenlos). |
| **ALPHAVANTAGE_API_KEY** | `backend/agents/finint_agent.py`, `energy_agent.py`, `techint_agent.py` | [alphavantage.co/support/#api-key](https://www.alphavantage.co/support/#api-key) – kostenloser Key. |

---

## Optional (neue Agents: CYBER, ENERGY, PROTEST, DIPLO)

| Key | Verwendung im Code | Bezugsquelle |
|-----|---------------------|--------------|
| **OTX_API_KEY** | `backend/agents/cyber_agent.py` – AlienVault OTX (Threat Intel) | [otx.alienvault.com](https://otx.alienvault.com/) → Sign Up → Einstellungen (Avatar) → API Key. Kostenlos. |
| **GREYNOISE_API_KEY** | `backend/agents/cyber_agent.py` (Scan-Kontext), `backend/agents/greynoise_agent.py` (Emerging Threats: GNQL Stats, CVE Lookup, Tags API) | [greynoise.io](https://www.greynoise.io/) → Account → API Key. VIP Researcher Community Access empfohlen für GNQL Stats + CVE-Endpunkte. Scheduler läuft alle 6h (konfigurierbar via `GREYNOISE_SCHEDULER_INTERVAL_SEC`). Konflikte: `GREYNOISE_CONFLICTS` (Default: `Iran,Gaza/Israel,Lebanon,Yemen,Middle East`). |
| **AGSI_API_KEY** | `backend/agents/energy_agent.py` – EU-Gasspeicher (AGSI+) | [agsi.gie.eu/account](https://agsi.gie.eu/account) – Registrierung (kostenlos). Key nach Login in der API-Doku. |
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
| **SPIRE_MARITIME_API_KEY** | `backend/agents/sigint_agent.py` – Spire Maritime (Schiffe/AIS) | [spire.com](https://spire.com/) – Maritime API. |
| **SPIRE_AIRSAFE_TOKEN** | `backend/agents/sigint_agent.py` – Spire Airsafe (Flugzeug-Tracking) | [api.airsafe.spire.com](https://api.airsafe.spire.com) – Bearer Token. Endpoint: `/v2/targets/stream` (Batch mit start/end). Alternativ: **SPIRE_API_KEY** falls ein Token für alle Spire-APIs. |
| **ADSBEXCHANGE_RAPIDAPI_KEY** | `backend/agents/sigint_agent.py` – ADSBexchange (Flugzeuge/Target-Tracking) via RapidAPI | [RapidAPI: ADSBexchange](https://rapidapi.com/adsbx/api/adsbexchange-com1) – Key nach Anmeldung. Alternativ: **RAPIDAPI_KEY** (falls nur eine RapidAPI-App). Host optional: **ADSBEXCHANGE_RAPIDAPI_HOST** (Default: `adsbexchange-com1.p.rapidapi.com`). **Mehrere Flugzeuge:** Ziele in `TARGET_AIRCRAFT` (Code) oder per Env: **TARGET_AIRCRAFT_EXTRA** = kommagetrennte Namen (z. B. `AF1,RAFSHADOW1`), pro Ziel optional **TARGET_&lt;NAME&gt;_HEX** = ICAO-Hex. **Kostenanalyse siehe unten.** |
| **UCDP_API_TOKEN** | `backend/agents/geoint_agent.py` – Uppsala Conflict Data Program (GED events) | Bei UCDP anfragen ([ucdp.uu.se](https://ucdp.uu.se/), [API-Doku](https://ucdp.uu.se/apidocs/)). Header: `x-ucdp-access-token`. **Limit:** 5.000 Requests/Tag (Mitternacht UTC); jeder paginierte Request zählt. |
| **LIVEUAMAP_API_KEY** | GEOINT (Liveuamap, falls integriert) | Liveuamap – oft kostenpflichtig. |
| **NOTAM_API_KEY** | `backend/agents/iaea_tracker.py` – NOTAM (Autorouter.aero) | [autorouter.aero](https://www.autorouter.aero/) – falls der Endpunkt Auth verlangt. |
| **FIRECRAWL_API_KEY** | `backend/agents/acled_reference.py` – ACLED-Referenzseiten (robustes Scraping) | [firecrawl.dev](https://firecrawl.dev) – Free Plan: 500 Credits einmalig, 2 gleichzeitige Requests. Ohne Key: Fallback auf httpx. |

---

## ADSBexchange RapidAPI – Kostenanalyse für dieses Projekt

| Faktor | Wert in diesem Projekt |
|--------|-------------------------|
| **Aufrufer** | Nur `get_target_aircraft("OE-III")` im SIGINT-Agent, pro Analyse-Lauf **1×** ausgeführt. |
| **Requests pro Lauf** | **1–2** (zuerst ICAO-Lookup, falls leer: ein Region-Call 35°N/25°E, 100 nm). |
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

- **Lokal:** `backend/.env` (nicht committen).  
- **Produktion:** Railway (Backend) → Variables; Vercel (Frontend) nur für `VITE_*` (z. B. `VITE_API_URL`, `VITE_SUPABASE_*`).

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

# Optional – FININT: Gold, On-Chain-Wallets (TRACKED_ETH_ADDRESSES in finint_agent.py)
# METALS_API_KEY=...
# ETHEREUM_ETHERSCAN_API_KEY=...
```

**Etherscan Free Tier:** Max. 3 Requests/Sekunde (im Code durch Verzögerung zwischen Abfragen eingehalten), bis zu 100.000 Calls/Tag. **Attribution** ist vorgeschrieben – in der App z. B. „Data by Etherscan“ oder Link zu etherscan.io anzeigen. Die Antwort von `get_tracked_chain_wallets` enthält einen `_attribution`-Eintrag. Nur Community-Endpoints, ca. 90 % Multichain-Abdeckung.

Alle Key-Namen findest du auch per Suche im Repo: `os.getenv("KEY_NAME")` bzw. in `backend/scripts/check_agents.py` und `docs/DEPLOYMENT.md`.
