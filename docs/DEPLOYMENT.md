# Digital War Room – Checkliste Veröffentlichung

Schritte, um das Projekt live zu schalten (Frontend auf Vercel, Backend auf Railway).

---

## 1. Backend (Railway)

- [ ] **Projekt auf Railway deployen**  
  Repo verbinden oder `backend/` als Root setzen; Start-Command z. B.:  
  `uvicorn main:app --host 0.0.0.0 --port $PORT`  
  (Railway setzt `PORT` oft automatisch.)
- [ ] **Umgebungsvariablen in Railway setzen** (unter Variables):
  - **Pflicht für Analyse (LLM):**  
    Entweder `ANTHROPIC_API_KEY` (Standard) **oder** `LLM_PROVIDER=openai` + `OPENAI_API_KEY` (günstigere Alternative, z. B. GPT-4o-mini).
  - **Pro Agent (siehe `backend/scripts/check_agents.py`):**
    - `NEWS_API_KEY` (News-Agent)
    - `NASA_FIRMS_KEY` (GEOINT)
    - `ALPHAVANTAGE_API_KEY` (FININT, optional TECHINT)
  - **Optional:**  
    `POLYMARKET_BUILDER_API_KEY`, `ACLED_EMAIL` + `ACLED_PASSWORD` (ACLED OAuth für PROTEST/GEOINT/Heatmap; siehe [ACLED Getting started](https://acleddata.com/api-documentation/getting-started)), `SHODAN_API_KEY`, `CLOUDFLARE_RADAR_API_TOKEN`, `LIVEUAMAP_API_KEY` (GEOINT: Liveuamap Lebanon/Iran, kostenpflichtige API), `OTX_API_KEY` (CYBER: AlienVault OTX), `AGSI_API_KEY` (ENERGY: EU-Gasspeicher AGSI+).
  - **Observability (Tracing):** **OpenTelemetry (OTEL):** Setze `OTEL_EXPORTER_OTLP_ENDPOINT` (z. B. `http://localhost:4317` für Jaeger gRPC). Optional: `OTEL_SERVICE_NAME=digital-war-room`. Traces (LLM-, Agent-, Tool-Spans) gehen an den konfigurierten OTLP-Endpoint (z. B. **Jaeger**). Jaeger lokal: `docker run -d --name jaeger -p 16686:16686 -p 4317:4317 -p 4318:4318 jaegertracing/all-in-one:latest` – UI unter `http://localhost:16686`.
- **Kosten senken (LLM-API):**
  - **OpenAI statt Claude:** `LLM_PROVIDER=openai`, `OPENAI_API_KEY=sk-…`. Agents und Supervisor nutzen dann z. B. `gpt-4o-mini` (Standard); optional `OPENAI_AGENT_MODEL` / `OPENAI_SUPERVISOR_MODEL` setzen.
  - `AUTO_ANALYZE_INTERVAL_SEC` (Standard: 21600 = alle 6 Stunden; z. B. 3600 = stündlich, 600 = alle 10 Min).
  - **Supervisor standardmäßig nur Haiku:** Default ist `SUPERVISOR_MODEL=claude-haiku-4-5-20251001` und **`USE_SUPERVISOR_FALLBACK_MODEL=false`** (kein Sonnet-Fallback). Optional: `USE_SUPERVISOR_FALLBACK_MODEL=true` setzen – dann wird bei stark auseinanderliegenden Agent-Scores (Spannweite ≥ 50) Sonnet genutzt. Schwellwert: `SUPERVISOR_CONTRADICTION_RANGE_THRESHOLD=50` (default).
  - **`USE_RULE_BASED_AGENTS`** – Standard ist `true`: FININT, GEOINT, NEWS, SOCMINT, SIGINT laufen mit fester Tool-Kette (siehe `docs/AGENT-TOOL-CHAIN.md`), kein LLM in den Agents. Nur der Supervisor nutzt ein LLM. Zum Aktivieren von LLM pro Agent: `USE_RULE_BASED_AGENTS=false`.
  - **`USE_RULE_BASED_SUPERVISOR=true`** – Zusätzlich Supervisor ohne LLM: nur gewichteter Score, Threat-Stufen, Key Findings aus Agent-Daten. Kein LLM-Aufruf im Supervisor (minimale Kosten).
- **Grobe LLM-Kosten pro Analyse** (Stand grob 2025/26, nur Supervisor – Agents laufen standardmäßig regelbasiert; ca. 25k Input-, 1k Output-Tokens):
  - **Nur Haiku** (Standard, kein Sonnet): Default `USE_SUPERVISOR_FALLBACK_MODEL=false` → ~**0,03 USD** pro Lauf.
  - **Haiku + Fallback Sonnet bei Widersprüchen:** `USE_SUPERVISOR_FALLBACK_MODEL=true` – dann bei Score-Spannweite ≥ 50 Sonnet (~0,10 USD), sonst Haiku.
  - **Nur Claude Sonnet:** ~**0,08–0,12 USD** pro Lauf (z. B. `SUPERVISOR_MODEL=claude-sonnet-4-6`).
  - **OpenAI gpt-4o-mini** (`LLM_PROVIDER=openai`): ~**0,005 USD** (ca. 0,5 Cent) pro Lauf; bei Widersprüchen optional `OPENAI_SUPERVISOR_FALLBACK_MODEL=gpt-4o`.
  - **`USE_RULE_BASED_SUPERVISOR=true`:** **0 USD** (kein LLM)
- **Support the Mission:** Link zu Buy Me a Coffee (im Frontend hinterlegt); kein Backend nötig.
- [ ] **Backend-URL notieren**  
  Nach dem Deploy die öffentliche URL kopieren (z. B. `https://dein-service.up.railway.app`). Kein abschließendes `/`.

---

## 2. Frontend (Vercel)

- [ ] **Projekt mit Vercel verbinden**  
  Repo verbinden; **Root Directory** auf Projektroot lassen (nicht `backend/`). Build: `npm run build`, Output: `dist`.
- [ ] **Umgebungsvariablen in Vercel setzen** (Settings → Environment Variables, für Production):
  - **Pflicht:** `VITE_API_URL` = **Backend-URL von Railway** (z. B. `https://dein-service.up.railway.app`)
  - **Wichtig:** Werte 1:1 übernehmen, **keine Anführungszeichen** um den Key, **keine Leerzeichen** am Anfang/Ende.
- [ ] **Nach dem ersten Deploy:** Neudeploy auslösen (Redeploy), damit die Env-Vars im Build genutzt werden (Vite baut sie zur Build-Zeit ein).

---

## 3. Nach dem Go-Live prüfen

- [ ] **„Run Analysis“** im Dashboard: Request geht an `VITE_API_URL` (Railway); bei Fehlern siehe Browser-Netzwerk (z. B. CORS oder 502).
- [ ] **SPA-Routing:** Direktaufruf von `/app/dashboard`, `/app/monitoring` zeigt die richtige Seite (`vercel.json` Rewrites).
---

## 4. Eigene Domain (z. B. www.digital-war-room.com)

Um auf deine eigene Domain umzuschalten:

1. **Vercel – Domain hinzufügen**
   - Vercel Dashboard → dein Projekt → **Settings** → **Domains**
   - **Add** → `www.digital-war-room.com` (und optional `digital-war-room.com` für Weiterleitung)
   - Angezeigte DNS-Einträge bei deinem Domain-Anbieter eintragen (meist CNAME für `www` auf `cname.vercel-dns.com`, A-Record für Apex je nach Anbieter)

2. **Backend (Railway) – CORS**
   - Unter **Variables** setzen:  
     `CORS_ORIGINS` = `https://www.digital-war-room.com,https://digital-war-room.com`  
     (kommagetrennt, keine Leerzeichen um die URLs; mit `*` erlaubt das Backend alle Origins.)
   - Nach Änderung: Service neu starten bzw. Redeploy.

3. **Frontend-Env (Vercel)**  
   `VITE_API_URL` bleibt die Railway-Backend-URL; die App läuft unter der neuen Domain, die API-Calls gehen weiterhin an Railway.

---

## 5. Optional (weitere Hinweise)

- **Discoverability & SEO:** Nach Go-Live: GitHub Topics setzen, Repo-Website-URL auf `https://digital-war-room.com` stellen, Google Search Console und Bing Webmaster einrichten, Sitemap einreichen. Siehe **[docs/DISCOVERABILITY.md](DISCOVERABILITY.md)**.
- **Eigene Domain (Details):** Siehe Abschnitt 4 oben.
- **CORS:** Bei eigener Domain in Railway `CORS_ORIGINS` setzen (Abschnitt 4).
- **Backend-Health:** `GET https://deine-railway-url/health` sollte `{"status":"ok"}` liefern.
- **Analyse sofort auslösen (z. B. nach Neustart):**  
  `POST https://deine-railway-url/api/analyze/trigger?conflict=US-Iran`  
  Optional in Railway Variable `ANALYZE_TRIGGER_SECRET` setzen; dann Header `X-Trigger-Secret: <Wert>` mitschicken. Dauert 1–2 Min, danach Cache gefüllt.
- **Sensible Keys:** `.env` und `backend/.env` nicht committen; nur in Vercel/Railway setzen.
- **IAEA/OE-III Tracker:** `GET /api/iaea-tracker` – trackt das IAEO-Flugzeug (OE-III) via ADS-B, NOTAMs (Autorouter.aero), IAEA-Press (Grossi). **NOTAM:** Standard `NOTAM_API_URL=https://api.autorouter.aero/v1.0/notam` (GET mit `itemas=["EDDS","LOWW","OIIE"]`, `offset`, `limit`). Optional `NOTAM_API_KEY` falls Endpunkt Auth verlangt. Direktabfrage: `GET /api/notam?locations=EDDS,LOWW&limit=10&offset=0`.

---

## Kurzüberblick

| Komponente   | Wo              | Wichtig |
|-------------|-----------------|--------|
| Frontend    | Vercel          | **Pflicht:** `VITE_API_URL` = Railway-URL |
| Backend     | Railway         | `ANTHROPIC_API_KEY` oder `OPENAI_API_KEY` (bei `LLM_PROVIDER=openai`), optional Agent-Keys |
| SPA-Routing | Repo (`vercel.json`) | Bereits eingerichtet                 |
