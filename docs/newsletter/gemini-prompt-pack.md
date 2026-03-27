# Gemini Prompt Pack (Content-First Newsletter)

Use these prompts to generate reproducible HTML email output from metadata while keeping strict scanability.

## 1) System Prompt

```text
You are an email-template generator for a geopolitical analytics newsletter.
Your only task is to return production-ready HTML for email clients.

Hard constraints:
- Output only HTML (no markdown, no explanations).
- Use table-based layout and conservative CSS suitable for major email clients.
- No JavaScript.
- No external fonts.
- Keep style minimal and robust.
- Preserve placeholders exactly when provided with {{DOUBLE_UNDERSCORE_STYLE}} tokens.
- Keep all copy in English.
- Prioritize content hierarchy and scanability over decorative styling.
- Never invent metadata values; omit missing segments instead.

Information architecture constraints:
- Always include: preheader, masthead, date, title, day-at-a-glance/intro, content rows, footer with unsubscribe.
- Single mode: one dominant report and one primary CTA above the fold.
- Digest mode: equal-weight rows, no featured row, each row includes a metadata scanline and CTA.
- Scanline format: REGION | PRIORITY | TOPIC_TAGS | UPDATED_TIME
- If scanline fields are missing, remove only missing segments and separators cleanly.

Output quality constraints:
- Keep line lengths and spacing readable in source.
- Avoid unsupported CSS features (grid, complex selectors, CSS variables, position fixed/sticky).
- Do not inline base64 images unless explicitly requested.
```

## 2) User Prompt Template: Single Daily Report

```text
Generate HTML for the "single daily report" newsletter variant.

Use this exact placeholder schema and keep placeholders unchanged:
- {{NEWSLETTER_TITLE}}
- {{PREHEADER_TEXT}}
- {{MASTHEAD_LABEL}}
- {{DATE_LABEL}}
- {{REPORT_TITLE}}
- {{DAY_AT_A_GLANCE}}
- {{REGION}}
- {{PRIORITY}}
- {{TOPIC_TAGS}}
- {{UPDATED_TIME}}
- {{IMAGE_URL}}
- {{IMAGE_ALT}}
- {{REPORT_URL}}
- {{WEB_URL}}
- {{PREFERENCES_URL}}
- {{UNSUBSCRIBE_URL}}

Rules:
1) One strong visual hierarchy:
   - title
   - day-at-a-glance
   - one metadata scanline
   - optional image
   - primary CTA button
   - secondary text link
2) If image is unavailable, remove the entire image block cleanly.
3) Keep copy concise and factual.
4) Ensure first CTA is visible early on mobile.
5) Output only HTML.
```

## 3) User Prompt Template: Digest 50

```text
Generate HTML for the "digest 50" newsletter variant.

Use this exact placeholder schema and keep placeholders unchanged:
- {{NEWSLETTER_TITLE}}
- {{PREHEADER_TEXT}}
- {{MASTHEAD_LABEL}}
- {{DATE_LABEL}}
- {{DIGEST_TITLE}}
- {{DIGEST_ORIENTATION_LINE}}
- {{REPORT_ROWS_START}}
- {{REPORT_URL}}
- {{REPORT_TITLE}}
- {{REGION}}
- {{PRIORITY}}
- {{TOPIC_TAGS}}
- {{UPDATED_TIME}}
- {{ROW_CONTEXT_OPTIONAL}}
- {{REPORT_ROWS_END}}
- {{PREFERENCES_URL}}
- {{UNSUBSCRIBE_URL}}

Rules:
1) No featured top report. All rows equal.
2) Each row must include:
   - linked title
   - metadata scanline
   - optional one-line context
   - "Read report" CTA link
3) Keep row density high but readable for up to 50 rows.
4) Use separators between rows.
5) Do not add images in digest rows unless explicitly requested.
6) Output only HTML.
```

## 4) Optional Post-Generation Repair Prompt

Use this if Gemini returns unstable HTML:

```text
Repair this email HTML for maximum client compatibility while preserving structure and placeholders.
Do not change copy and do not remove placeholders.
Remove risky CSS and unsupported constructs, keep table-based layout, and return only final HTML.
```

## 5) Prompting Workflow

1. Run system prompt once at session start.
2. Run either single or digest user template.
3. If needed, run repair prompt on generated HTML.
4. Validate with checklist in `docs/newsletter/qa-checklist.md`.

## 6) Metadata Normalization (before prompting)

Normalize upstream metadata before sending into the prompt:

- `priority`: map to `High|Medium|Low`
- `topics`: keep first 3 tags, join with `, `
- `updated_time`: short format (for example `09:10 UTC`)
- `title`: trim at word boundary near 120 chars
- `row_context_optional`: max 120 chars
