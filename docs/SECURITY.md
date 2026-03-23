# Security & Authorization

Das Backend unterstützt **Multi-Tenancy** mit mandantenspezifischen Daten in PostgreSQL (Row Level Security über Session-Variablen), optional **JWT** (Supabase oder eigenes Secret) und **mandantenbezogene API-Schlüssel**. Ohne Token gilt der **Default-Tenant** (`DEFAULT_TENANT_ID`, siehe Migration `003_multi_tenancy.sql`). Zusätzlich bleiben **Rate Limits** und optional **`ANALYZE_TRIGGER_SECRET`** für den Trigger-Endpoint bestehen.

---

## 1. Rate Limiting

- **Umsetzung:** `slowapi` mit `Limiter(key_func=get_remote_address)` in `backend/middleware/rate_limit.py`.
- **Limits:**
  - `GET /api/analyze/stream`, `POST /api/analyze`, `GET /api/analyze/refresh`: **10/minute** pro Client-IP.
  - `POST /api/analyze/trigger`: **5/minute** pro Client-IP (zusätzlich optional `X-Trigger-Secret`).
- Bei Überschreitung: HTTP 429; Handler in `main.py` via `app.add_exception_handler(RateLimitExceeded, ...)`.

---

## 2. API-Keys (externe Dienste vs. DWR-API)

**Externe Dienste** (ACLED, GreyNoise, NewsAPI, …): Keys liegen in der Backend-`.env` (plattformweit).

**Digital-War-Room-API** (Mandanten): Owner/Admin können pro Tenant Schlüssel erzeugen (`POST /api/tenant/api-keys`). Format: `dwr_<hex>_<hex>`, Speicher nur als **SHA-256-Hash**; Klartext wird einmal zurückgegeben. Requests: Header `X-Api-Key` oder `Authorization: Bearer <key>`.

**Rotation:** Schlüssel in der DB widerrufen (`DELETE /api/tenant/api-keys/{id}`), neuen Key erzeugen.

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

## 6. Multi-Tenancy, RBAC und JWT

- **Schema:** Tabellen `tenants`, `tenant_memberships` (Rollen: `owner`, `admin`, `member`, `viewer`), `tenant_api_keys`; Spalte `tenant_id` auf `embeddings`, `quality_signals`, `ais_track_samples`. Migrationen: `backend/migrations/003_multi_tenancy.sql`, `004_newsletter_postgres.sql` (Newsletter-Tabellen unter Postgres).
- **RLS:** Pro Verbindung setzt das Backend `app.active_tenant_id` (siehe `services/db_tenant.py`), Policies auf den Daten-Tabellen filtern darauf.
- **JWT:** `SUPABASE_JWT_SECRET` oder `JWT_SECRET` (HS256), Claim `sub` = User-UUID. Optional `X-Tenant-Id`, wenn der User mehreren Mandanten angehört.
- **RBAC:** Rollen kommen aus `tenant_memberships`; API-Key-Clients erhalten synthetische Rolle `api_client`. Geschützte Routen prüfen `owner`/`admin` wo nötig.
- **Strenger Modus:** `MULTI_TENANCY_REQUIRE_AUTH=true` → Anfragen ohne gültiges JWT/API-Key erhalten 401 (außer öffentlich definierte Endpunkte).
- **Frontend:** `/app/login` speichert optional `dwr_supabase_access_token` oder `dwr_api_key` in `localStorage`; `src/lib/api.ts` hängt `getAuthHeaders()` an `fetchWithTimeout` an.

---

## 7. Newsletter (SQLite)

Lokal ohne zentrale DB: **SQLite** unter `data/newsletter.sqlite` mit `tenant_id` pro Zeile (eindeutig pro Mandant + E-Mail). Täglicher Versand nutzt weiterhin eine globale `newsletter_daily_lock`-Zeile pro UTC-Tag.

---

## Kurzüberblick

| Thema              | Stand / Empfehlung                                      |
|--------------------|---------------------------------------------------------|
| Rate Limiting      | ✅ slowapi, 10/min (Analyse), 5/min (Trigger)           |
| Plattform-API-Keys | 📋 Env (externe Dienste); Rotation über Provider       |
| Mandanten-API-Keys | ✅ Hash in DB; `X-Api-Key` / Bearer                     |
| CORS               | ✅ Konfigurierbar; in Prod explizite Origins setzen     |
| Input-Sanitization | ✅ `sanitize_conflict()` vor Agent-Dispatch              |
| Auth / Tenants     | ✅ JWT + API-Key + Default-Tenant; optional REQUIRE_AUTH |
| RBAC               | ✅ Rollen in `tenant_memberships`                        |
