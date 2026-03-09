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
| **AGSI_API_KEY** | `backend/agents/energy_agent.py` – EU-Gasspeicher (AGSI+) | [agsi.gie.eu/account](https://agsi.gie.eu/account) – Registrierung (kostenlos). Key nach Login in der API-Doku. |
| **ACLED_API_KEY** | `backend/agents/protest_agent.py`, `geoint_agent.py`, `api/routes.py` (Conflict-Events/Heatmap) | [acleddata.com/user/register](https://acleddata.com/user/register) – myACLED Account. API-Zugang über [developer.acleddata.com](https://developer.acleddata.com/). |
| **ACLED_EMAIL** | `backend/agents/protest_agent.py`, `geoint_agent.py` – wird teils von ACLED API verlangt | Deine bei ACLED registrierte E-Mail (gleiche wie beim ACLED-Account). |

**Ohne ACLED-API:** Auf der ACLED-Webseite gibt es öffentlich einsehbare Crisis-Live-Daten, z. B. **[Iran Crisis Live](https://acleddata.com/iran-crisis-live)** – tägliche Updates, Karten und Analysen zum Iran-Konflikt (täglich 10:30 EST / 15:30 CET). Für die Plattform-Heatmap und PROTEST-Events wird weiterhin ein API-Key benötigt; die Webseite eignet sich als manuelle Ergänzung.

**DIPLO** benötigt **keine** Keys (OFAC, EU-Liste, UN/ICJ-RSS sind öffentlich).

---

## Weitere optionale Keys (bestehende Agents)

| Key | Verwendung im Code | Bezugsquelle |
|-----|---------------------|--------------|
| **POLYMARKET_BUILDER_API_KEY** | `backend/agents/finint_agent.py` – Polymarket (höhere Limits) | [polymarket.com](https://polymarket.com/) – Builder/API-Zugang. |
| **SHODAN_API_KEY** | `backend/agents/techint_agent.py` – Shodan Host-Counts | [account.shodan.io](https://account.shodan.io/) – Registrierung, API Key im Dashboard. |
| **CLOUDFLARE_RADAR_API_TOKEN** | `backend/agents/techint_agent.py` – Outage-Annotations | [dash.cloudflare.com](https://dash.cloudflare.com/) → Radar / API. |
| **SPIRE_MARITIME_API_KEY** | `backend/agents/sigint_agent.py` – Spire Maritime (Schiffe/AIS) | [spire.com](https://spire.com/) – Maritime API. |
| **UCDP_API_TOKEN** | `backend/agents/geoint_agent.py` – Uppsala Conflict Data Program | Bei UCDP/API-Anbietern anfragen (z. B. [ucdp.uu.se](https://ucdp.uu.se/)). |
| **LIVEUAMAP_API_KEY** | GEOINT (Liveuamap, falls integriert) | Liveuamap – oft kostenpflichtig. |
| **NOTAM_API_KEY** | `backend/agents/iaea_tracker.py` – NOTAM (Autorouter.aero) | [autorouter.aero](https://www.autorouter.aero/) – falls der Endpunkt Auth verlangt. |

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
ACLED_API_KEY=...
ACLED_EMAIL=deine@email.de
```

Alle Key-Namen findest du auch per Suche im Repo: `os.getenv("KEY_NAME")` bzw. in `backend/scripts/check_agents.py` und `docs/DEPLOYMENT.md`.
