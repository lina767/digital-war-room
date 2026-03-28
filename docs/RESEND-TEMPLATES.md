# Resend dashboard templates (Digital War Room)

Optional: send the double opt-in confirmation and/or the **single-layout** daily briefing through [Resend Templates](https://resend.com/docs/dashboard/templates/introduction) instead of HTML generated only in Python.

## Limits (Resend platform)

- **At most 20 variables** per template (dashboard + API).
- **Each string variable:** max **2000** characters ([Send Email](https://resend.com/docs/api-reference/emails/send-email)).
- **Reserved variable names** (do not define these in the template): `FIRST_NAME`, `LAST_NAME`, `EMAIL`, `RESEND_UNSUBSCRIBE_URL`, `contact`, `this`.
- Use **`{{{VAR}}}`** (triple mustache) in the template HTML when the value may contain HTML (e.g. `INFOGRAPHIC_IMG_HTML`).
- **Digest layout** (`NEWSLETTER_LAYOUT=digest`): not mapped to templates (too many fields). The backend keeps using programmatic HTML. You will see an info log if `RESEND_TEMPLATE_ID_DAILY` is set while layout is digest.

## Environment

| Variable | Purpose |
|----------|---------|
| `RESEND_TEMPLATE_ID_CONFIRM` | Published template id or alias for the confirmation email. If unset, Python uses `email_templates.confirmation_*`. |
| `RESEND_TEMPLATE_ID_DAILY` | Published template id or alias for the daily briefing (**single** layout). If unset, Python uses `newsletter_content_templates` HTML. |

`RESEND_API_KEY` and `NEWSLETTER_FROM` are still required.

## Confirmation template variables

Define these three variables in the Resend template:

| Key | Example |
|-----|---------|
| `CONFLICT` | `Iran` |
| `CONFIRM_LINK` | `https://your-frontend/newsletter/confirm?token=...` |
| `IS_REMINDER` | `yes` or `no` |

The API still sets **Subject** (`Confirm your...` / `Reminder: confirm...`) over the template default if you configure subject in code.

**Starter HTML (adjust branding):**

```html
<p>You're subscribing to the Daily Briefing for <strong>{{{CONFLICT}}}</strong>.</p>
<p><a href="{{{CONFIRM_LINK}}}">Confirm subscription</a></p>
<p style="color:#64748b;font-size:12px;">If you did not request this, ignore this email.</p>
```

## Daily briefing template variables (exactly 20)

The backend sends **all** of these keys on every send (empty string allowed for unused findings).

| Key | Content |
|-----|---------|
| `CONFLICT` | Conflict label |
| `DATE_STR` | `YYYY-MM-DD` (newsletter timezone) |
| `THREAT_LEVEL` | e.g. `HIGH`, `ELEVATED` |
| `ESCALATION_SCORE` | `0`–`100` as string |
| `BLUF_TEXT` | Executive summary (truncated if needed) |
| `FINDING_1` … `FINDING_5` | Finding text; context may be appended after ` — ` |
| `LINK_BLUF_CTA` | Tracked dashboard link (BLUF CTA) |
| `LINK_VIEW_FULL` | Tracked “view full briefing” link |
| `LINK_PUBLIC_FALLBACK` | Tracked public `/daily-briefing` link |
| `NL_UNSUB_LINK` | Unsubscribe URL (do **not** name a variable `UNSUBSCRIBE_URL`; it is reserved on Resend) |
| `LINK_FINDING_1` … `LINK_FINDING_5` | Per-finding deep links |
| `INFOGRAPHIC_IMG_HTML` | Either empty, or a short `<img src="cid:dwr-daily-infographic" ... />` snippet |

When `INFOGRAPHIC_IMG_HTML` is non-empty, the API attaches the generated image with **`content_id` `dwr-daily-infographic`** so the CID matches.

**Starter HTML fragment:**

```html
<h1 style="font-size:18px;">Daily Briefing — {{{CONFLICT}}} — {{{DATE_STR}}}</h1>
<p><strong>{{{THREAT_LEVEL}}}</strong> · Escalation {{{ESCALATION_SCORE}}}/100</p>
<p>{{{BLUF_TEXT}}}</p>
<p><a href="{{{LINK_BLUF_CTA}}}">Open dashboard</a> · <a href="{{{LINK_VIEW_FULL}}}">Full briefing</a> · <a href="{{{LINK_PUBLIC_FALLBACK}}}">Public page</a></p>
<div>{{{INFOGRAPHIC_IMG_HTML}}}</div>
<table role="presentation" width="100%">
  <tr><td><p>{{{FINDING_1}}}</p><p><a href="{{{LINK_FINDING_1}}}">Dashboard</a></p></td></tr>
  <!-- repeat FINDING_2 … 5 -->
</table>
<p><a href="{{{NL_UNSUB_LINK}}}">Unsubscribe</a></p>
```

Publish the template in the Resend UI before production sends.

## Code references

- Variable builders: `backend/services/resend_template_payloads.py`
- Send path: `backend/services/newsletter_sender.py` (`_send` with `template` + optional `attachments`)
