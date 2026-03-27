# Newsletter QA Checklist

Use this checklist after generating HTML for `single` or `digest-50`, and after changes to infographic generation or `newsletter_link_builder.py`.

## A) Structure and Hierarchy (CTR-first)

- Preheader text exists and is meaningful.
- Masthead and date are present at top.
- **Above the fold:** BLUF (short) appears **before** the infographic image block.
- **Primary CTA** (open live dashboard) appears **immediately after** BLUF and **before** the infographic (mobile preview ~320px).
- Infographic block follows (inline image when available, or compact text fallback without layout break).
- `single`: 3–5 key-development blocks each have **two** tracked links: dashboard deep-link + public `/daily-briefing` fallback where the template provides both.
- `digest-50`: all rows use equal-weight structure (no featured top row); each row CTA is uniquely tracked (`digest_row_{n}`).
- Footer includes preferences and unsubscribe links.

## B) Scanability

- Metadata scanline appears in each item using compact format (where applicable).
- Scanline separators are clean (no duplicate `||` when values are missing).
- First actionable CTA appears early on mobile viewport (BLUF CTA before long body or image).
- Digest rows remain readable when repeated many times.

## C) Copy and Content

- All visible text is English.
- Day-at-a-glance / BLUF is concise (not full report body text).
- Titles are trimmed and not broken mid-word.
- Topic tags are capped (target max 3).
- Missing metadata does not show `N/A`, `null`, or placeholder artifacts.

## D) HTML, CSS, and Inline Assets

- Table-based layout is used for structure.
- No JavaScript in output.
- No unsupported CSS features (grid, fixed positioning, complex selectors).
- No external font dependencies.
- **Daily infographic:** When `NEWSLETTER_INFOGRAPHIC_ALWAYS` and image generation succeed, a **base64 inline** image is expected in `single` mode; verify `max-width`, borders, and `alt` text. If HTML exceeds `NEWSLETTER_MAX_HTML_BYTES`, confirm the send path **drops** the inline image and still delivers a valid mail with CTA + text fallback.
- **Image size:** Decoded image should stay within `NEWSLETTER_INFOGRAPHIC_MAX_IMAGE_BYTES` after server-side compression (log or inspect one sample send).

## E) Link, UTM, and Placeholder Integrity

- Required Resend/template placeholders remain exact (double braces unchanged) where still used.
- Unsubscribe link placeholder is present.
- **Every** user-facing newsletter link includes: `utm_source=newsletter`, `utm_medium=email`, `utm_campaign=daily-briefing-{YYYY-MM-DD}`, and a **unique** `utm_content` per slot (`bluf_primary_cta`, `infographic_cta`, `finding_1`…, `view_full_briefing`, `public_briefing_fallback`, `digest_row_{n}`).
- Dashboard links resolve to `/app/dashboard` with at least `conflict=`; finding links add `nl_agent=` when inference matches.
- Public fallback links resolve to `/daily-briefing` **without** requiring auth; `nl_section` scroll target works when present.
- No accidental placeholder renaming or casing changes.

## F) Rendering Checks

- Mobile check at ~320px width: no clipped text, BLUF CTA visible early.
- Desktop check around 680px content width: spacing and hierarchy stable.
- **Dark mode:** Infographic labels and key numbers remain readable in light and dark email previews (Gmail + Outlook-style tool when possible).
- Digest with many rows shows consistent row separators and spacing.

## G) Web Parity (Daily Briefing)

- `/daily-briefing` shows the **Daily infographic snapshot** section when `_newsletter_infographic_data_uri` is present on the payload; otherwise the text fallback appears in the same region (no large layout jump).

## H) Deliverability and Regression

- Double opt-in flow unchanged (confirm before daily send).
- **Baseline:** Capture delivery, bounce, complaint, open, and click rates before a major rollout; compare after by `utm_content`.
- Define rollback: if metrics regress beyond an agreed threshold, prefer text-heavy / no-inline-image mode (env or code path) and document the decision.
- Newsletter still sends when infographic generation fails (text fallback).

## I) Quick Failure Triage

If QA fails, apply this order:

1. Run the repair prompt from `docs/newsletter/gemini-prompt-pack.md` (if the issue is infographic content/contrast).
2. Re-validate placeholders, UTM query strings, and scanline formatting.
3. Remove fragile CSS until rendering is stable.
4. Re-test mobile first, then desktop; re-check HTML total size and clipping.
