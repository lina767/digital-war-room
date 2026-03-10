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
| **GREYNOISE_API_KEY** | `backend/agents/cyber_agent.py` – GreyNoise GNQL Stats (Scan-Kontext: malicious scanners 7d) | [greynoise.io](https://www.greynoise.io/) → Account → API Key. Free Tier verfügbar. |
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
| **SPIRE_MARITIME_API_KEY** | `backend/agents/sigint_agent.py` – Spire Maritime (Schiffe/AIS) | [spire.com](https://spire.com/) – Maritime API. |
| **UCDP_API_TOKEN** | `backend/agents/geoint_agent.py` – Uppsala Conflict Data Program | Bei UCDP/API-Anbietern anfragen (z. B. [ucdp.uu.se](https://ucdp.uu.se/)). |
| **LIVEUAMAP_API_KEY** | GEOINT (Liveuamap, falls integriert) | Liveuamap – oft kostenpflichtig. |
| **NOTAM_API_KEY** | `backend/agents/iaea_tracker.py` – NOTAM (Autorouter.aero) | [autorouter.aero](https://www.autorouter.aero/) – falls der Endpunkt Auth verlangt. |
| **FIRECRAWL_API_KEY** | `backend/agents/acled_reference.py` – ACLED-Referenzseiten (robustes Scraping) | [firecrawl.dev](https://firecrawl.dev) – Free Plan: 500 Credits einmalig, 2 gleichzeitige Requests. Ohne Key: Fallback auf httpx. |

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

# Optional – FININT: Gold, On-Chain-Wallets (TRACKED_ETH_ADDRESSES in finint_agent.py)
# METALS_API_KEY=...
# ETHEREUM_ETHERSCAN_API_KEY=...
```

**Etherscan Free Tier:** Max. 3 Requests/Sekunde (im Code durch Verzögerung zwischen Abfragen eingehalten), bis zu 100.000 Calls/Tag. **Attribution** ist vorgeschrieben – in der App z. B. „Data by Etherscan“ oder Link zu etherscan.io anzeigen. Die Antwort von `get_tracked_chain_wallets` enthält einen `_attribution`-Eintrag. Nur Community-Endpoints, ca. 90 % Multichain-Abdeckung.

Alle Key-Namen findest du auch per Suche im Repo: `os.getenv("KEY_NAME")` bzw. in `backend/scripts/check_agents.py` und `docs/DEPLOYMENT.md`.
