# Daily Briefing Newsletter – Spec

Newsletter feature: subscribers receive a daily email with the current Daily Briefing (executive summary, key developments, link to the web view). All frontend and email copy in **English**.

---

## Decisions

| Topic | Choice |
|-------|--------|
| **Double opt-in** | Yes. Send confirmation email; only confirmed subscribers receive the daily mail. |
| **Email provider** | **Resend** (env: `RESEND_API_KEY`, `NEWSLETTER_FROM`). |
| **Send time** | **Fixed local time** (default **10:00** in **Europe/Berlin**, i.e. CET/CEST). At that time: **run an extra analysis** for the configured conflict(s), then send the newsletter with that **fresh** result („morning briefing“ with up-to-date data). Config: `NEWSLETTER_SEND_TIMEZONE`, `NEWSLETTER_SEND_HOUR`, `NEWSLETTER_SEND_MINUTE`; legacy `NEWSLETTER_SEND_UTC_HOUR` fixes a UTC hour instead. |

---

## 1. Subscriber store

- **Backend:** SQLite (MVP) or Postgres if `DATABASE_URL` is set.
- **Table** `newsletter_subscribers`: `id`, `email` (unique), `conflict` (default e.g. `Iran`), `subscribed_at`, `unsubscribe_token` (UUID), `confirm_token` (UUID), `confirmed_at` (nullable). Only rows with `confirmed_at` set are included in the daily send.
- **Module** e.g. `backend/services/newsletter_store.py`: `add_subscriber(email, conflict)` → returns `confirm_token`; `confirm_subscription(confirm_token)`; `remove_by_unsubscribe_token(token)`; `list_confirmed_subscribers(conflict=None)`.

---

## 2. Email sending (Resend)

- **Env:** `RESEND_API_KEY`, `NEWSLETTER_FROM` (e.g. `briefing@notifications.yourdomain.com`). If not set, newsletter routes and cron job no-op / log and return.
- **Sender domain:** Prefer a **subdomain** for the From address (e.g. `notifications.yourdomain.com` or `mail.yourdomain.com`) for [reputation isolation and sending-purpose transparency](https://resend.com/docs/knowledge-base/is-it-better-to-send-emails-from-a-subdomain-or-the-root-domain). Avoid lookalike domains (e.g. `yourdomain-mail.com`).

### Resend Templates (optional)

Instead of rendering all HTML in Python, you can send through **published** [Resend Templates](https://resend.com/docs/dashboard/templates/introduction):

- Set **`RESEND_TEMPLATE_ID_CONFIRM`** for the double opt-in message (variables: `CONFLICT`, `CONFIRM_LINK`, `IS_REMINDER`).
- Set **`RESEND_TEMPLATE_ID_DAILY`** for the **single** daily layout (`NEWSLETTER_LAYOUT=single`). The backend supplies **20** template variables (max per Resend) plus an optional **inline image** attachment with `content_id` `dwr-daily-infographic` when an infographic is generated. **Digest** layout (`digest`) is not template-mapped; programmatic HTML is used.

Resend limits string variables to **2000** characters each. Full variable list and starter HTML: [docs/RESEND-TEMPLATES.md](RESEND-TEMPLATES.md).

### Which subdomain to use and does it need to “exist”?

- **What to enter in Resend:** Add a subdomain of a domain you own, e.g. `notifications.yourdomain.com` or `mail.yourdomain.com`. In the Resend dashboard: [Domains](https://resend.com/domains) → Add domain → enter that subdomain (or the root domain if you prefer).
- **Does the subdomain need to exist as a website?** No. It does **not** need a website, A record, or hosting. You only need to add the **DNS records Resend shows you** (SPF and DKIM) at your DNS provider for that (sub)domain. Resend uses those records to verify you control the domain and to sign/authorize outgoing mail. No A/AAAA record is required.
- **Steps:** (1) In Resend, add the domain (e.g. `notifications.yourdomain.com`). (2) Resend displays the required TXT (and optionally MX) records. (3) Create those records in your DNS (where you manage your domain). (4) Click “Verify” in Resend. (5) Set `NEWSLETTER_FROM` to an address on that domain, e.g. `briefing@notifications.yourdomain.com`.
- **Reference:** [Resend – Managing domains](https://resend.com/docs/dashboard/domains/introduction) (SPF, DKIM, verification).
- **Module** `backend/services/newsletter_sender.py`:
  - `send_confirmation_email(email: str, conflict: str, confirm_token: str)` – one-time link to `.../newsletter/confirm?token=...`.
  - `send_daily_briefing(email: str, conflict: str, briefing_data: dict, unsubscribe_token: str)` – subject e.g. `Daily Briefing – [Conflict] – [Date]`; body is **CTR-first** (see §9): short BLUF + primary CTA, daily infographic when generation succeeds, 3–5 key developments with per-item dashboard deep-links and tracked public fallback, footer with unsubscribe link `.../newsletter/unsubscribe?token=...`.
- All copy in **English**.

---

## 3. Double opt-in flow

1. User submits email (and optional conflict) → **POST /api/newsletter/subscribe**. Store row with `confirmed_at = NULL`, generate `confirm_token`. In parallel, upsert Resend Contact with `unsubscribed=true` (pending state).
2. Send **confirmation email** via Resend with link to frontend `/newsletter/confirm?token=...`. Frontend calls **GET /api/newsletter/confirm?token=...** (or POST); backend sets `confirmed_at = now()`.
3. On successful confirm, Resend Contact is updated to `unsubscribed=false`.
4. Only subscribers with `confirmed_at` set receive the daily briefing.

### Resend Contacts (Broadcasts / segments)

The backend uses the **Resend Contacts API** (`POST /contacts`, `PATCH /contacts/{email}`) so contacts are available for **Broadcasts** and subscription state is mirrored (`unsubscribed=true` pending/unsubscribed, `false` confirmed). Optional env **`RESEND_NEWSLETTER_SEGMENT_ID`** (or comma-separated **`RESEND_NEWSLETTER_SEGMENT_IDS`**) attaches the contact to that **segment** (Resend replaced legacy “Audiences” with Contacts + Segments; see [Create Contact](https://resend.com/docs/api-reference/contacts/create-contact)). On unsubscribe, the app sets Resend Contact back to **`unsubscribed=true`** when sync is enabled. Set **`RESEND_CONTACTS_SYNC=false`** to disable Contact API calls only.

---

## 4. Daily send: fixed time + extra analysis

- **Fixed time:** default **10:00** in **Europe/Berlin** (`NEWSLETTER_SEND_TIMEZONE`, `NEWSLETTER_SEND_HOUR`, `NEWSLETTER_SEND_MINUTE`). Optional legacy: **`NEWSLETTER_SEND_UTC_HOUR`** (if set in env) uses a fixed UTC hour instead.
- **Sequence each day at that time:**
  1. **Trigger a full analysis** for the conflict(s) that have confirmed subscribers (e.g. `AUTO_ANALYZE_CONFLICT` or list of conflicts with subscribers). Use existing `analyze_conflict(conflict)`; wait for completion and update cache (same as periodic analysis).
  2. **Send newsletters:** For each conflict that was just analyzed, load cached result, get `list_confirmed_subscribers(conflict)`, render and send one email per subscriber via Resend (with unsubscribe token).
- **Implementation options:**
  - **A) Background task in lifespan** (like `run_periodic_analysis` in `main.py`): asyncio task that sleeps until next 06:00 UTC, then runs analysis → send; loop.
  - **B) Protected cron endpoint** `POST /api/newsletter/send-daily` (e.g. `X-Newsletter-Secret` / `NEWSLETTER_CRON_SECRET`), called by external cron at the same local time (e.g. 10:00 Europe/Berlin); endpoint triggers analysis then send. Prefer **B** if you use external cron (e.g. Railway/Render cron, GitHub Actions); otherwise **A** keeps everything in-process.

---

## 5. API (summary)

| Method | Path | Purpose |
|--------|------|--------|
| POST | `/api/newsletter/subscribe` | Body: `{ email, conflict? }`. Create unconfirmed subscriber; send confirmation email. |
| GET | `/api/newsletter/confirm?token=...` | Set `confirmed_at`; show success page. |
| GET | `/api/newsletter/unsubscribe?token=...` | Remove or deactivate subscriber; show “You have been unsubscribed.” |
| POST | `/api/newsletter/send-daily` | (Optional) Cron: run analysis for configured conflict(s), then send daily emails. Protected by `NEWSLETTER_CRON_SECRET`. |
| GET | `/api/newsletter/status` | Ops: SQLite counts (confirmed/pending), DB path. Same secret header when `NEWSLETTER_CRON_SECRET` is set. |
| POST | `/api/newsletter/track` | Lightweight KPI event ingest from web app (`ttv_recorded`, `briefing_to_dashboard_click`, `newsletter_slot_click`, `return_24h_after_newsletter`). |
| GET | `/api/newsletter/feedback?kind=useful|not_useful` | One-click email feedback link; stores event and redirects to `/daily-briefing`. |
| GET | `/api/newsletter/kpi-baseline?days=14` | Protected KPI baseline snapshot for ops review (counts, TTV average, slot clicks by campaign/content). |
| POST | `/api/newsletter/sync-from-resend` | Import/mirror: list Resend contacts for a segment (`GET /contacts?segment_id=`) into SQLite (confirmed vs remove if unsubscribed). Body: optional `segment_id`; defaults to env segment/audience. Same secret. |
| POST | `/api/webhooks/resend` | Resend webhooks (bounces/complaints). Set `RESEND_WEBHOOK_SECRET` (Svix signing secret). |

---

## 6. Frontend (English)

- **Subscribe form:** Email input, optional conflict dropdown; button “Subscribe to daily briefing”. On submit → POST subscribe → toast “Please check your inbox to confirm your subscription.”
- **Confirm page** (`/newsletter/confirm?token=...`): Call confirm API; show “You’re subscribed. You’ll receive the daily briefing by email.”
- **Unsubscribe page** (`/newsletter/unsubscribe?token=...`): Call unsubscribe API; show “You have been unsubscribed.”
- Optional **/newsletter** page: Short explanation + subscribe form; link to privacy.

---

## 7. Env and docs

- **.env.example:** `RESEND_API_KEY`, `NEWSLETTER_FROM`, `FRONTEND_URL`, optional `RESEND_NEWSLETTER_SEGMENT_ID` / `RESEND_NEWSLETTER_SEGMENT_IDS`, `RESEND_CONTACTS_SYNC`, `NEWSLETTER_CRON_SECRET`, optional `NEWSLETTER_SEND_TIMEZONE` / `NEWSLETTER_SEND_HOUR` / `NEWSLETTER_SEND_MINUTE` (or legacy `NEWSLETTER_SEND_UTC_HOUR`).
- **Infographic / size (daily default):** `NEWSLETTER_INFOGRAPHIC_ALWAYS` (default `true` — generate for every daily send; set `false` to fall back to weekly-only flags), `NEWSLETTER_INFOGRAPHIC_IMAGE_ENABLED`, `NEWSLETTER_INFOGRAPHIC_MODEL`, `NEWSLETTER_INFOGRAPHIC_TIMEOUT_SEC`, `NEWSLETTER_INFOGRAPHIC_MAX_IMAGE_BYTES` (decoded image cap before send; JPEG recompress), `NEWSLETTER_MAX_HTML_BYTES` (if full HTML exceeds this after render, inline image is dropped and the mail is re-rendered with a text/link fallback to reduce Gmail clipping). Legacy: `NEWSLETTER_WEEKLY_INFOGRAPHIC_ENABLED` / `NEWSLETTER_WEEKLY_INFOGRAPHIC_WEEKDAY` apply only when `NEWSLETTER_INFOGRAPHIC_ALWAYS=false`.

### Troubleshooting: „Keine Mail heute“

| Ursache | Was prüfen |
|--------|------------|
| **Zeitzone** | Standard: **10:00 Ortszeit** **`Europe/Berlin`** (CET/CEST). Alternativ: `NEWSLETTER_SEND_UTC_HOUR` setzen → feste UTC-Stunde (Legacy). |
| **Double opt-in** | Nur Zeilen mit gesetztem `confirmed_at` in SQLite bekommen Mail. Nach Subscribe **Bestätigungslink** in der E-Mail klicken. |
| **Deploy / Neustart** | In-process Scheduler wartet bis zur **nächsten** vollen Stunde UTC – wenn der Server **nach** dieser Zeit startet, ist der Lauf für **diesen** Tag versäumt (nächster Lauf: Folgetag), sofern kein externes Cron `POST /api/newsletter/send-daily` triggert. |
| **Ephemeral Disk (z. B. Railway)** | Ohne Volume geht **`NEWSLETTER_DB_PATH`** (SQLite) bei Deploy verloren → Abonnenten/Lock weg. Volume mounten und `NEWSLETTER_DB_PATH` auf persistenten Pfad setzen. |
| **Dedupe / Retry** | Wenn der Lauf **0** Mails sendet (z. B. `analyze_conflict` Timeout für alle Konflikte), wird der Tages-Lock **nicht** als abgeschlossen markiert und gelöscht, damit **Cron/Retry** am selben UTC-Tag noch greifen kann. |
| **Resend** | `RESEND_API_KEY`, `NEWSLETTER_FROM` (verifizierte Domain); Resend-Dashboard auf Bounces/Logs prüfen. |

- **Scheduling (avoid double daily send):** Either use the **in-process** scheduler (default when Resend is configured) **or** only **external cron** on `POST /api/newsletter/send-daily`. If you use cron only, set **`NEWSLETTER_IN_PROCESS_SCHEDULER=false`** so the app does not also run the 06:00 UTC loop in `main.py`.
- **Dedupe:** **`NEWSLETTER_DAILY_DEDUPE`** (default `true`) uses a SQLite row per UTC day; the day is marked **completed only after at least one briefing email was sent**, so a failed run (0 sends) does not block retries the same UTC day.
- **Send tuning:** `NEWSLETTER_SEND_PARALLELISM` (default `5`), `NEWSLETTER_SEND_MAX_RETRIES`, `NEWSLETTER_SEND_BACKOFF_BASE` for Resend 429/5xx retries.
- **Bounces / complaints:** Configure a Resend webhook pointing to **`POST /api/webhooks/resend`** and set **`RESEND_WEBHOOK_SECRET`** to the Svix signing secret from the webhook details page. Hard bounces and complaints remove the subscriber locally and sync Resend Contacts when enabled.
- **API-KEYS.md / DEPLOYMENT.md:** Resend setup; cron (if used) at 06:00 UTC calling `POST /api/newsletter/send-daily`.
- **Privacy page:** Short “Newsletter” section (EN): what we store (email, conflict), purpose (daily briefing), unsubscribe, controller.

---

## 8. Implementation order

1. Subscriber store (SQLite or Postgres) + `newsletter_store.py`.
2. Resend integration: `newsletter_sender.py` (confirmation + daily mail).
3. Routes: subscribe, confirm, unsubscribe; optional send-daily.
4. Daily job: fixed-time run (asyncio task or cron) → analysis then send.
5. Frontend: subscribe form, confirm page, unsubscribe page (all English).
6. Env, docs, privacy text.

---

## 9. CTR-first layout, daily infographic, and link tracking

### Email hierarchy (single layout)

1. **BLUF** — 2–3 short sentences (executive lead).
2. **Primary CTA** — Opens the live dashboard in the right conflict context (`utm_content=bluf_primary_cta`).
3. **Infographic** — One inline image (base64) when Gemini generation succeeds; alt text and spacing fixed for clients; on failure or oversize, a compact text block replaces the image without breaking the table layout.
4. **Key developments** — 3–5 blocks; each has its own **dashboard** deep-link (`utm_content=finding_1` … `finding_5`) with `conflict` and optional `nl_agent` (inferred from finding text) so the app can open the agents panel on the matching row. A **public** tracked link to `/daily-briefing` is provided for cold/unauthenticated readers.
5. **Footer** — Preferences / unsubscribe unchanged; other links use the same UTM scheme where applicable.

### Digest layout

- Equal-weight rows; each row CTA uses `utm_content=digest_row_{n}` and points at `/daily-briefing` with `nl_section` for scroll targeting.

### UTM contract (all newsletter links)

| Parameter | Value |
|-----------|--------|
| `utm_source` | `newsletter` |
| `utm_medium` | `email` |
| `utm_campaign` | `daily-briefing-{YYYY-MM-DD}` (calendar date in **`NEWSLETTER_SEND_TIMEZONE`**, default Europe/Berlin, at send time) |
| `utm_content` | `bluf_primary_cta`, `infographic_cta`, `view_full_briefing`, `finding_1`…`finding_5`, `public_briefing_fallback`, or `digest_row_{n}` |

Implementation: `backend/services/newsletter_link_builder.py` (`build_newsletter_link_bundle`, `build_tracked_url`, `digest_row_url`). Templates and `newsletter_sender.py` must not hand-roll query strings for these CTAs.

### KPI baseline contract (first 8 weeks)

- **TTV**: measured as seconds from `/daily-briefing` load until first meaningful interaction (`ttv_recorded`).
- **Briefing -> Dashboard CTR**: measured by `briefing_to_dashboard_click`.
- **Newsletter slot CTR**: measured by `newsletter_slot_click`, grouped by `utm_campaign` and `utm_content`.
- **24h return**: measured by `return_24h_after_newsletter` when a user returns within 24h of a newsletter-origin session.
- Query baseline with `GET /api/newsletter/kpi-baseline?days=14` (same secret header if configured).

### Same infographic on the web Daily Briefing

- After analysis, the API attaches `_newsletter_infographic_data_uri` on the cached briefing payload when generation succeeds (`attach_daily_infographic_to_briefing` in `newsletter_sender.py`, invoked from newsletter/analysis routes before `set_cache`).
- The public page **`/daily-briefing`** (`DailyBriefingPage.tsx`) renders section `#briefing-infographic` when that field is present; otherwise a short fallback message keeps layout stable.
- Dashboard entry from email: **`/app/dashboard`** with `conflict` and optional `nl_agent` query params (handled in `Dashboard.tsx`).

### Deliverability and QA operations

- **Size gate:** Keep decoded inline image under `NEWSLETTER_INFOGRAPHIC_MAX_IMAGE_BYTES` (default aligns with ~80 KB target after compression); keep total HTML under `NEWSLETTER_MAX_HTML_BYTES` or strip the inline image automatically.
- **Dark mode:** Verify infographic legibility in light and dark email previews (Gmail / Outlook-style) before major template or prompt changes.
- **Metrics:** Record baseline delivery, bounce, complaint, open, and click rates before rollout; after rollout compare by `utm_content` to validate per-slot engagement; define thresholds to switch to a more text-heavy fallback if metrics regress.
