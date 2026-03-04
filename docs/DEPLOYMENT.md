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
  - `VITE_SUPABASE_URL` = `https://nzhmnprqjldtoddabulu.supabase.co` (exakt, zu deinem Supabase-Projekt)
  - `VITE_SUPABASE_ANON_KEY` = **Anon Key (public)** aus Supabase: Project Settings → API → `anon` `public`
  - `VITE_SUPABASE_PUBLISHABLE_KEY` = **denselben Wert** wie `VITE_SUPABASE_ANON_KEY`
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
- **Sensible Keys:** `.env` und `backend/.env` nicht committen; nur in Vercel/Railway/Supabase setzen.

---

## Kurzüberblick

| Komponente   | Wo              | Wichtig |
|-------------|-----------------|--------|
| Frontend    | Vercel          | `VITE_API_URL` = Railway-URL, Supabase-Keys |
| Backend     | Railway         | `ANTHROPIC_API_KEY`, optional Agent-Keys   |
| Auth/DB     | Supabase        | Migrationen, Redirect/Site URL             |
| SPA-Routing | Repo (`vercel.json`) | Bereits eingerichtet                 |
