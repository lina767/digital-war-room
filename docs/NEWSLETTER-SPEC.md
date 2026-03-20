# Daily Briefing Newsletter – Spec

Newsletter feature: subscribers receive a daily email with the current Daily Briefing (executive summary, key developments, link to the web view). All frontend and email copy in **English**.

---

## Decisions

| Topic | Choice |
|-------|--------|
| **Double opt-in** | Yes. Send confirmation email; only confirmed subscribers receive the daily mail. |
| **Email provider** | **Resend** (env: `RESEND_API_KEY`, `NEWSLETTER_FROM`). |
| **Send time** | **Fixed time** (e.g. 06:00 UTC). At that time: **run an extra analysis** for the configured conflict(s), then send the newsletter with that **fresh** result („morning briefing“ with up-to-date data). |

---

## 1. Subscriber store

- **Backend:** SQLite (MVP) or Postgres if `DATABASE_URL` is set.
- **Table** `newsletter_subscribers`: `id`, `email` (unique), `conflict` (default e.g. `Iran`), `subscribed_at`, `unsubscribe_token` (UUID), `confirm_token` (UUID), `confirmed_at` (nullable). Only rows with `confirmed_at` set are included in the daily send.
- **Module** e.g. `backend/services/newsletter_store.py`: `add_subscriber(email, conflict)` → returns `confirm_token`; `confirm_subscription(confirm_token)`; `remove_by_unsubscribe_token(token)`; `list_confirmed_subscribers(conflict=None)`.

---

## 2. Email sending (Resend)

- **Env:** `RESEND_API_KEY`, `NEWSLETTER_FROM` (e.g. `briefing@notifications.yourdomain.com`). If not set, newsletter routes and cron job no-op / log and return.
- **Sender domain:** Prefer a **subdomain** for the From address (e.g. `notifications.yourdomain.com` or `mail.yourdomain.com`) for [reputation isolation and sending-purpose transparency](https://resend.com/docs/knowledge-base/is-it-better-to-send-emails-from-a-subdomain-or-the-root-domain). Avoid lookalike domains (e.g. `yourdomain-mail.com`).

### Which subdomain to use and does it need to “exist”?

- **What to enter in Resend:** Add a subdomain of a domain you own, e.g. `notifications.yourdomain.com` or `mail.yourdomain.com`. In the Resend dashboard: [Domains](https://resend.com/domains) → Add domain → enter that subdomain (or the root domain if you prefer).
- **Does the subdomain need to exist as a website?** No. It does **not** need a website, A record, or hosting. You only need to add the **DNS records Resend shows you** (SPF and DKIM) at your DNS provider for that (sub)domain. Resend uses those records to verify you control the domain and to sign/authorize outgoing mail. No A/AAAA record is required.
- **Steps:** (1) In Resend, add the domain (e.g. `notifications.yourdomain.com`). (2) Resend displays the required TXT (and optionally MX) records. (3) Create those records in your DNS (where you manage your domain). (4) Click “Verify” in Resend. (5) Set `NEWSLETTER_FROM` to an address on that domain, e.g. `briefing@notifications.yourdomain.com`.
- **Reference:** [Resend – Managing domains](https://resend.com/docs/dashboard/domains/introduction) (SPF, DKIM, verification).
- **Module** `backend/services/newsletter_sender.py`:
  - `send_confirmation_email(email: str, conflict: str, confirm_token: str)` – one-time link to `.../newsletter/confirm?token=...`.
  - `send_daily_briefing(email: str, conflict: str, briefing_data: dict, unsubscribe_token: str)` – subject e.g. `Daily Briefing – [Conflict] – [Date]`; body: summary, key findings (e.g. first 10), link to `/daily-briefing?conflict=...`, footer with unsubscribe link `.../newsletter/unsubscribe?token=...`.
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

- **Fixed time:** e.g. **06:00 UTC** (configurable via env `NEWSLETTER_SEND_UTC_HOUR`, default `6`).
- **Sequence each day at that time:**
  1. **Trigger a full analysis** for the conflict(s) that have confirmed subscribers (e.g. `AUTO_ANALYZE_CONFLICT` or list of conflicts with subscribers). Use existing `analyze_conflict(conflict)`; wait for completion and update cache (same as periodic analysis).
  2. **Send newsletters:** For each conflict that was just analyzed, load cached result, get `list_confirmed_subscribers(conflict)`, render and send one email per subscriber via Resend (with unsubscribe token).
- **Implementation options:**
  - **A) Background task in lifespan** (like `run_periodic_analysis` in `main.py`): asyncio task that sleeps until next 06:00 UTC, then runs analysis → send; loop.
  - **B) Protected cron endpoint** `POST /api/newsletter/send-daily` (e.g. `X-Newsletter-Secret` / `NEWSLETTER_CRON_SECRET`), called by external cron at 06:00 UTC; endpoint triggers analysis then send. Prefer **B** if you use external cron (e.g. Railway/Render cron, GitHub Actions); otherwise **A** keeps everything in-process.

---

## 5. API (summary)

| Method | Path | Purpose |
|--------|------|--------|
| POST | `/api/newsletter/subscribe` | Body: `{ email, conflict? }`. Create unconfirmed subscriber; send confirmation email. |
| GET | `/api/newsletter/confirm?token=...` | Set `confirmed_at`; show success page. |
| GET | `/api/newsletter/unsubscribe?token=...` | Remove or deactivate subscriber; show “You have been unsubscribed.” |
| POST | `/api/newsletter/send-daily` | (Optional) Cron: run analysis for configured conflict(s), then send daily emails. Protected by `NEWSLETTER_CRON_SECRET`. |

---

## 6. Frontend (English)

- **Subscribe form:** Email input, optional conflict dropdown; button “Subscribe to daily briefing”. On submit → POST subscribe → toast “Please check your inbox to confirm your subscription.”
- **Confirm page** (`/newsletter/confirm?token=...`): Call confirm API; show “You’re subscribed. You’ll receive the daily briefing by email.”
- **Unsubscribe page** (`/newsletter/unsubscribe?token=...`): Call unsubscribe API; show “You have been unsubscribed.”
- Optional **/newsletter** page: Short explanation + subscribe form; link to privacy.

---

## 7. Env and docs

- **.env.example:** `RESEND_API_KEY`, `NEWSLETTER_FROM`, `FRONTEND_URL`, optional `RESEND_NEWSLETTER_SEGMENT_ID` / `RESEND_NEWSLETTER_SEGMENT_IDS`, `RESEND_CONTACTS_SYNC`, `NEWSLETTER_CRON_SECRET`, `NEWSLETTER_SEND_UTC_HOUR=6`.
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
