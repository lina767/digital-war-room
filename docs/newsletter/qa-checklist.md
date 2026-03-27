# Newsletter QA Checklist

Use this checklist after generating HTML for `single` or `digest-50`.

## A) Structure and Hierarchy

- Preheader text exists and is meaningful.
- Masthead and date are present at top.
- `single`: title, day-at-a-glance, scanline, CTA appear in that order.
- `digest-50`: all rows use equal-weight structure (no featured top row).
- Footer includes preferences and unsubscribe links.

## B) Scanability

- Metadata scanline appears in each item using compact format.
- Scanline separators are clean (no duplicate `||` when values are missing).
- First actionable CTA appears early on mobile viewport.
- No long paragraph blocks before first CTA.
- Digest rows remain readable when repeated 50 times.

## C) Copy and Content

- All visible text is English.
- Day-at-a-glance is concise (not full report body text).
- Titles are trimmed and not broken mid-word.
- Topic tags are capped (target max 3).
- Missing metadata does not show `N/A`, `null`, or placeholder artifacts.

## D) HTML and CSS Safety

- Table-based layout is used for structure.
- No JavaScript in output.
- No unsupported CSS features (grid, fixed positioning, complex selectors).
- No external font dependencies.
- Base64 image embeds are absent unless explicitly requested.

## E) Link and Placeholder Integrity

- Required placeholders remain exact (double braces unchanged).
- CTA links point to correct placeholders (`{{REPORT_URL}}`, etc.).
- Unsubscribe link placeholder is present.
- No accidental placeholder renaming or casing changes.

## F) Rendering Checks

- Mobile check at ~320px width: no clipped text, CTA visible early.
- Desktop check around 680px content width: spacing and hierarchy stable.
- Image-optional behavior works (`single` mode with/without image).
- Digest with 50 rows shows consistent row separators and spacing.
- Test render in at least Gmail + Outlook-compatible preview tool when possible.

## G) Quick Failure Triage

If QA fails, apply this order:

1. Run the repair prompt from `docs/newsletter/gemini-prompt-pack.md`.
2. Re-validate placeholders and scanline formatting.
3. Remove fragile CSS until rendering is stable.
4. Re-test mobile first, then desktop.
