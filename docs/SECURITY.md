# Security & Authorization

Das Backend nutzt **kein Supabase** und keine externe Auth-Datenbank. Auth ist optional (z. B. über `ANALYZE_TRIGGER_SECRET` für den Trigger-Endpoint). Die folgenden Maßnahmen sind umgesetzt bzw. empfohlen.

---

## 1. Rate Limiting

- **Umsetzung:** `slowapi` mit `Limiter(key_func=get_remote_address)` in `backend/middleware/rate_limit.py`.
- **Limits:**
  - `GET /api/analyze/stream`, `POST /api/analyze`, `GET /api/analyze/refresh`: **10/minute** pro Client-IP.
  - `POST /api/analyze/trigger`: **5/minute** pro Client-IP (zusätzlich optional `X-Trigger-Secret`).
- Bei Überschreitung: HTTP 429; Handler in `main.py` via `app.add_exception_handler(RateLimitExceeded, ...)`.

---

## 2. API-Key-Rotation (externe Services)

Es gibt **keine integrierte User-Auth** (kein Supabase). API-Keys für externe Dienste (ACLED, GreyNoise, NewsAPI, etc.) liegen in der Backend-`.env` bzw. in den Umgebungsvariablen von Railway/Vercel.

**Empfehlung – Rotation ohne Downtime:**

- **Railway (Backend):**  
  - Neue Keys in **Variables** eintragen (oder per CLI).  
  - Optional: **Environment Groups** nutzen und Keys dort rotieren; Redeploy/Neustart, damit die neue Umgebung aktiv wird.  
  - Alte Keys bei den Anbietern (ACLED, GreyNoise, etc.) erst deaktivieren, nachdem der neue Key im Backend läuft.

- **Vercel (Frontend):**  
  - Nur `VITE_*`-Variablen (z. B. `VITE_API_URL`). Rotation = neuen Wert setzen → **Redeploy**, damit der Build die neue URL nutzt.

- **Best Practice:**  
  - Keys regelmäßig rotieren (z. B. quartalsweise).  
  - Pro Dienst einen eigenen Key nutzen, um bei Kompromittierung nur einen Key zu wechseln.

---

## 3. CORS

- **Konfiguration:** `CORS_ORIGINS` in `backend/agents/config.py` (aus Env: `CORS_ORIGINS`, Default `*`).
- **Produktion:** `*` nur für lokale Entwicklung geeignet. In Produktion explizite Origins setzen, z. B.:
  - Railway Variables:  
    `CORS_ORIGINS=https://www.digital-war-room.com,https://digital-war-room.com`
  - Bei `ENVIRONMENT=production` und `*` loggt das Backend eine Warnung (siehe `main.py`).

---

## 4. Input-Sanitization

- **Konflikt-Parameter:** Alle Routen, die `conflict` (Query, Path, Body) annehmen, nutzen `utils.sanitize.sanitize_conflict()` vor Agent-Dispatch:
  - Erlaubt: Buchstaben, Ziffern, Leerzeichen, `-`, `/`, `,` (z. B. „Gaza/Israel“).
  - Max. Länge 80 Zeichen, keine Steuerzeichen/Null-Bytes.
  - Bei Verletzung: HTTP 400 mit `{"error": "...", "field": "conflict"}`.
- Betroffen: `/api/analyze/*`, `/api/conflict-events`, `/api/theater-events`, `/api/greynoise/{conflict}`, etc.

---

## 5. Trigger-Endpoint

- `POST /api/analyze/trigger` kann mit optionalem **Secret** geschützt werden:
  - Env: `ANALYZE_TRIGGER_SECRET`.
  - Header: `X-Trigger-Secret: <Wert>`.
  - Ist das Secret gesetzt und fehlt/falsch → 403.

---

## 6. RBAC / User-Tiers (ohne Supabase)

Aktuell gibt es **kein RBAC** und keine User-Tiers. Für spätere Erweiterung ohne Supabase:

- **Option A:** Eigenes kleines Auth-Modul (z. B. JWT mit eigenem Secret, User/Tier in DB oder Config).
- **Option B:** API-Gateway (z. B. Cloudflare Access, Kong) vor dem Backend; Tiers über API-Key-Header oder Gruppen.
- **Option C:** Rate-Limits pro Tier unterschiedlich setzen (z. B. `key_func` auf API-Key oder User-ID, wenn später vorhanden).

---

## Kurzüberblick

| Thema              | Stand / Empfehlung                                      |
|--------------------|---------------------------------------------------------|
| Rate Limiting      | ✅ slowapi, 10/min (Analyse), 5/min (Trigger)           |
| API-Key-Rotation   | 📋 Manuell über Railway/Vercel Env; Redeploy nach Wechsel |
| CORS               | ✅ Konfigurierbar; in Prod explizite Origins setzen     |
| Input-Sanitization | ✅ `sanitize_conflict()` vor Agent-Dispatch              |
| Auth               | Kein Supabase; optional Trigger-Secret, sonst keine User-Auth |
| RBAC / Tiers       | ❌ Noch nicht umgesetzt; Optionen oben                  |
