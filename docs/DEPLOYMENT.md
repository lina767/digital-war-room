# Digital War Room – Checkliste Veröffentlichung

Schritte, um das Projekt live zu schalten (Frontend auf Vercel, Backend auf Railway, Auth/Datenbank Supabase).

---

## 1. Supabase (bereits eingerichtet)

- [ ] **Migrationen ausgeführt**  
  Im Supabase SQL Editor einmalig z. B. `supabase/migrations/004_full_setup_if_missing.sql` ausführen (Tabellen `profiles`, `user_settings`, `saved_analyses`, RLS, Trigger).
- [ ] **Auth Redirect URLs**  
  Unter **Authentication → URL Configuration** die Produktions-URL eintragen, z. B.  
  `https://deine-app.vercel.app`  
  sowie `https://deine-app.vercel.app/**` als Redirect-URLs, damit Login/Signup/Reset-Password nach dem Deployment funktionieren.
- [ ] **Site URL**  
  `Site URL` in Supabase auf die finale Frontend-URL setzen (z. B. `https://deine-app.vercel.app`).

---

## 2. Backend (Railway)

- [ ] **Projekt auf Railway deployen**  
  Repo verbinden oder `backend/` als Root setzen; Start-Command z. B.:  
  `uvicorn main:app --host 0.0.0.0 --port $PORT`  
  (Railway setzt `PORT` oft automatisch.)
- [ ] **Umgebungsvariablen in Railway setzen** (unter Variables):
  - **Pflicht für Analyse:**  
    `ANTHROPIC_API_KEY` (Supervisor/Claude)
  - **Pro Agent (siehe `backend/scripts/check_agents.py`):**
    - `NEWS_API_KEY` (News-Agent)
    - `NASA_FIRMS_KEY` (GEOINT)
    - `ALPHAVANTAGE_API_KEY` (FININT, optional TECHINT)
  - **Optional:**  
    `POLYMARKET_BUILDER_API_KEY`, `ACLED_API_KEY`, `ACLED_EMAIL`, `SHODAN_API_KEY`, `CLOUDFLARE_RADAR_API_TOKEN`, `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`
- [ ] **Backend-URL notieren**  
  Nach dem Deploy die öffentliche URL kopieren (z. B. `https://dein-service.up.railway.app`). Kein abschließendes `/`.

---

## 3. Frontend (Vercel)

- [ ] **Projekt mit Vercel verbinden**  
  Repo verbinden; **Root Directory** auf Projektroot lassen (nicht `backend/`). Build: `npm run build`, Output: `dist`.
- [ ] **Umgebungsvariablen in Vercel setzen** (Settings → Environment Variables, für Production):
  - `VITE_API_URL` = **Backend-URL von Railway** (z. B. `https://dein-service.up.railway.app`)
  - `VITE_SUPABASE_URL` = `https://nzhmnprqjldtoddabulu.supabase.co` (oder deine Supabase-URL)
  - `VITE_SUPABASE_ANON_KEY` = dein Supabase Anon Key
  - `VITE_SUPABASE_PUBLISHABLE_KEY` = derselbe Wert wie Anon Key (falls dein Client so konfiguriert ist)
  - Optional: `VITE_SUPABASE_PROJECT_ID` = `nzhmnprqjldtoddabulu`
- [ ] **Nach dem ersten Deploy:** Neudeploy auslösen (Redeploy), damit die neuen Env-Vars im Build genutzt werden (Vite baut sie zur Build-Zeit ein).

---

## 4. Nach dem Go-Live prüfen

- [ ] **Login/Signup** auf der Live-URL testen (Supabase Redirect URLs).
- [ ] **„Run Analysis“** im Dashboard: Request geht an `VITE_API_URL` (Railway); bei Fehlern siehe Browser-Netzwerk (z. B. CORS oder 502).
- [ ] **Profil & Einstellungen** (Namen, Konflikt, Favoriten): Speichern und Reload prüfen; bei Fehlern RLS/Migrationen in Supabase prüfen.
- [ ] **SPA-Routing:** Direktaufruf von `/login`, `/app/dashboard` zeigt die richtige Seite (dafür liegt `vercel.json` mit Rewrites im Repo).

---

## 5. Optional

- **Eigene Domain:** In Vercel Domain hinzufügen; in Supabase die neue Domain als Redirect/Site URL eintragen.
- **Backend-Health:** `GET https://deine-railway-url/health` sollte `{"status":"ok"}` liefern.
- **Sensible Keys:** `.env` und `backend/.env` nicht committen; nur in Vercel/Railway/Supabase setzen.

---

## Kurzüberblick

| Komponente   | Wo              | Wichtig |
|-------------|-----------------|--------|
| Frontend    | Vercel          | `VITE_API_URL` = Railway-URL, Supabase-Keys |
| Backend     | Railway         | `ANTHROPIC_API_KEY`, optional Agent-Keys   |
| Auth/DB     | Supabase        | Migrationen, Redirect/Site URL             |
| SPA-Routing | Repo (`vercel.json`) | Bereits eingerichtet                 |
