# Digital War Room – Checkliste Veröffentlichung

Schritte, um das Projekt live zu schalten (Frontend auf Vercel, Backend auf Railway, Auth/Datenbank Supabase).

---

## 1. Supabase (bereits eingerichtet)

- [ ] **Migrationen ausgeführt**  
  Im Supabase SQL Editor einmalig z. B. `supabase/migrations/004_full_setup_if_missing.sql` ausführen (Tabellen `profiles`, `user_settings`, `saved_analyses`, RLS, Trigger).
- [ ] **Auth Redirect URLs (wichtig für Login auf Vercel)**  
  Supabase erlaubt Redirects nur auf eingetragene URLs. Unter **Authentication → URL Configuration → Redirect URLs** die Produktions-URL eintragen, z. B.:
  - `https://digital-war-room.vercel.app`
  - `https://digital-war-room.vercel.app/**`
  Ohne diese Einträge funktioniert Login/Signup auf der Live-Seite nicht (nur localhost).
- [ ] **Site URL**  
  **Site URL** in derselben Sektion auf die finale Frontend-URL setzen, z. B. `https://digital-war-room.vercel.app`.

---

## 2. Backend (Railway)

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
    `POLYMARKET_BUILDER_API_KEY`, `ACLED_API_KEY`, `ACLED_EMAIL`, `SHODAN_API_KEY`, `CLOUDFLARE_RADAR_API_TOKEN`, `LIVEUAMAP_API_KEY` (GEOINT: Liveuamap Lebanon/Iran, kostenpflichtige API), `UCDP_API_TOKEN` (GEOINT: Uppsala Conflict Data Program), `SPIRE_MARITIME_API_KEY` (SIGINT: Spire Maritime AIS/Vessels), `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`
- **Kosten senken (LLM-API):**
  - **OpenAI statt Claude:** `LLM_PROVIDER=openai`, `OPENAI_API_KEY=sk-…`. Agents und Supervisor nutzen dann z. B. `gpt-4o-mini` (Standard); optional `OPENAI_AGENT_MODEL` / `OPENAI_SUPERVISOR_MODEL` setzen.
  - `AUTO_ANALYZE_INTERVAL_SEC` (Standard: 3600 = stündlich; 600 = alle 10 Min).
  - **Supervisor standardmäßig nur Haiku:** Default ist `SUPERVISOR_MODEL=claude-haiku-4-5-20251001` und **`USE_SUPERVISOR_FALLBACK_MODEL=false`** (kein Sonnet-Fallback). Optional: `USE_SUPERVISOR_FALLBACK_MODEL=true` setzen – dann wird bei stark auseinanderliegenden Agent-Scores (Spannweite ≥ 50) Sonnet genutzt. Schwellwert: `SUPERVISOR_CONTRADICTION_RANGE_THRESHOLD=50` (default).
  - **`USE_RULE_BASED_AGENTS`** – Standard ist `true`: FININT, GEOINT, NEWS, SOCMINT, SIGINT laufen mit fester Tool-Kette (siehe `docs/AGENT-TOOL-CHAIN.md`), kein LLM in den Agents. Nur der Supervisor nutzt ein LLM. Zum Aktivieren von LLM pro Agent: `USE_RULE_BASED_AGENTS=false`.
  - **`USE_RULE_BASED_SUPERVISOR=true`** – Zusätzlich Supervisor ohne LLM: nur gewichteter Score, Threat-Stufen, Key Findings aus Agent-Daten. Kein LLM-Aufruf im Supervisor (minimale Kosten).
- **Grobe LLM-Kosten pro Analyse** (Stand grob 2025/26, nur Supervisor – Agents laufen standardmäßig regelbasiert; ca. 25k Input-, 1k Output-Tokens):
  - **Nur Haiku** (Standard, kein Sonnet): Default `USE_SUPERVISOR_FALLBACK_MODEL=false` → ~**0,03 USD** pro Lauf.
  - **Haiku + Fallback Sonnet bei Widersprüchen:** `USE_SUPERVISOR_FALLBACK_MODEL=true` – dann bei Score-Spannweite ≥ 50 Sonnet (~0,10 USD), sonst Haiku.
  - **Nur Claude Sonnet:** ~**0,08–0,12 USD** pro Lauf (z. B. `SUPERVISOR_MODEL=claude-sonnet-4-6`).
  - **OpenAI gpt-4o-mini** (`LLM_PROVIDER=openai`): ~**0,005 USD** (ca. 0,5 Cent) pro Lauf; bei Widersprüchen optional `OPENAI_SUPERVISOR_FALLBACK_MODEL=gpt-4o`.
  - **`USE_RULE_BASED_SUPERVISOR=true`:** **0 USD** (kein LLM)
- **Support the Mission (Stripe-hosted Checkout):**
  - **Backend (Railway):** `STRIPE_SECRET_KEY` (Secret Key aus [Stripe Dashboard](https://dashboard.stripe.com/apikeys)). Preis entweder per **`STRIPE_PRICE_ID`** oder **`STRIPE_PRODUCT_ID`** (Product-ID – es wird der Standard- bzw. erster Preis verwendet). Optional: `FRONTEND_URL` für success/cancel-URLs (Standard: `http://localhost:5173`; in Produktion z. B. `https://digital-war-room.vercel.app`). Kunde wird zur Stripe-Checkout-Seite weitergeleitet und nach Zahlung zurück zu deiner Seite.
  - **Frontend (Vercel):** Kein Stripe-Publishable-Key nötig; der Button ruft nur das Backend auf und leitet auf Stripe weiter.
- [ ] **Backend-URL notieren**  
  Nach dem Deploy die öffentliche URL kopieren (z. B. `https://dein-service.up.railway.app`). Kein abschließendes `/`.

---

## 3. Frontend (Vercel)

- [ ] **Projekt mit Vercel verbinden**  
  Repo verbinden; **Root Directory** auf Projektroot lassen (nicht `backend/`). Build: `npm run build`, Output: `dist`.
- [ ] **Umgebungsvariablen in Vercel setzen** (Settings → Environment Variables, für Production):
  - `VITE_API_URL` = **Backend-URL von Railway** (z. B. `https://dein-service.up.railway.app`)
  - `VITE_SUPABASE_URL` = `https://nzhmnprqjldtoddabulu.supabase.co` (exakt, zu deinem Supabase-Projekt)
  - `VITE_SUPABASE_ANON_KEY` = **Anon Key (public)** aus Supabase: Project Settings → API → `anon` `public`
  - `VITE_SUPABASE_PUBLISHABLE_KEY` = **denselben Wert** wie `VITE_SUPABASE_ANON_KEY`
  - **Support the Mission (Stripe):** Optional. Für die Stripe-Weiterleitung reicht das Backend; `VITE_STRIPE_PUBLISHABLE_KEY` ist nicht erforderlich.
  - **Wichtig:** Werte 1:1 aus der lokalen `.env` übernehmen, **keine Anführungszeichen** um den Key, **keine Leerzeichen** am Anfang/Ende.
- [ ] **Nach dem ersten Deploy:** Neudeploy auslösen (Redeploy), damit die neuen Env-Vars im Build genutzt werden (Vite baut sie zur Build-Zeit ein).

---

## 4. Nach dem Go-Live prüfen

- [ ] **Login/Signup** auf der Live-URL testen (Supabase Redirect URLs).
- [ ] **„Run Analysis“** im Dashboard: Request geht an `VITE_API_URL` (Railway); bei Fehlern siehe Browser-Netzwerk (z. B. CORS oder 502).
- [ ] **Profil & Einstellungen** (Namen, Konflikt, Favoriten): Speichern und Reload prüfen; bei Fehlern RLS/Migrationen in Supabase prüfen.
- [ ] **SPA-Routing:** Direktaufruf von `/login`, `/app/dashboard` zeigt die richtige Seite (dafür liegt `vercel.json` mit Rewrites im Repo).

---

## 5. Fehlerbehebung

- **„Invalid API key“ (Supabase)**  
  Der Anon Key in Vercel stimmt nicht mit dem Supabase-Projekt überein oder ist falsch eingetragen.
  1. Supabase Dashboard → **Project Settings** (Zahnrad) → **API** → unter **Project API keys** den **anon** **public** Key kopieren.
  2. In Vercel → **Settings** → **Environment Variables**: `VITE_SUPABASE_ANON_KEY` und `VITE_SUPABASE_PUBLISHABLE_KEY` auf genau diesen Wert setzen (nur den Key, keine Anführungszeichen).
  3. **Redeploy** auslösen (Deployments → … → Redeploy). Nach Änderung von Env-Vars ist ein neuer Build nötig.

---

## 6. Optional

- **Eigene Domain:** In Vercel Domain hinzufügen; in Supabase die neue Domain als Redirect/Site URL eintragen.
- **Backend-Health:** `GET https://deine-railway-url/health` sollte `{"status":"ok"}` liefern.
- **Analyse sofort auslösen (z. B. nach Neustart):**  
  `POST https://deine-railway-url/api/analyze/trigger?conflict=US-Iran`  
  Optional in Railway Variable `ANALYZE_TRIGGER_SECRET` setzen; dann Header `X-Trigger-Secret: <Wert>` mitschicken. Dauert 1–2 Min, danach Cache gefüllt.
- **Sensible Keys:** `.env` und `backend/.env` nicht committen; nur in Vercel/Railway/Supabase setzen.
- **IAEA/OE-III Tracker:** `GET /api/iaea-tracker` – trackt das IAEO-Flugzeug (OE-III) via ADS-B, NOTAMs (Autorouter.aero), IAEA-Press (Grossi). **NOTAM:** Standard `NOTAM_API_URL=https://api.autorouter.aero/v1.0/notam` (GET mit `itemas=["EDDS","LOWW","OIIE"]`, `offset`, `limit`). Optional `NOTAM_API_KEY` falls Endpunkt Auth verlangt. Direktabfrage: `GET /api/notam?locations=EDDS,LOWW&limit=10&offset=0`.

---

## Kurzüberblick

| Komponente   | Wo              | Wichtig |
|-------------|-----------------|--------|
| Frontend    | Vercel          | `VITE_API_URL` = Railway-URL, Supabase-Keys |
| Backend     | Railway         | `ANTHROPIC_API_KEY` oder `OPENAI_API_KEY` (bei `LLM_PROVIDER=openai`), optional Agent-Keys |
| Auth/DB     | Supabase        | Migrationen, Redirect/Site URL             |
| SPA-Routing | Repo (`vercel.json`) | Bereits eingerichtet                 |
