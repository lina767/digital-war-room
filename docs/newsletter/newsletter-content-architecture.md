# Newsletter Content Architecture

This document defines a content-first structure for two newsletter modes:

- `single`: one daily report
- `digest-50`: up to 50 report links with equal weighting

The goal is fast triage: readers should understand "what matters" in one scan pass.

## Shared Principles

- Keep one dominant objective per email: click-through to full report pages.
- Put decision-useful text first, decorative elements second.
- Use one visual hierarchy only: headline, scanline metadata, short context, CTA.
- Keep copy short and factual; avoid repeated prose in long digest mode.
- Assume partial support in email clients; content must still read without advanced CSS.

## Shared Block Order

All variants follow this section order:

1. Hidden preheader
2. Masthead (publication name + date)
3. Title line
4. Day-at-a-glance (1 to 2 short sentences)
5. Content module (`single` hero or `digest` list)
6. Footer (why received + unsubscribe)

## Scanline Specification

Each report entry uses a single "scanline" so readers can parse item metadata quickly.

Canonical scanline format:

`REGION | PRIORITY | TOPIC_TAGS | UPDATED_TIME`

Rules:

- `REGION`: short geography label (for example `MENA`, `EU`, `Global`).
- `PRIORITY`: `High`, `Medium`, or `Low` (or equivalent normalized tier).
- `TOPIC_TAGS`: max 3 compact tags separated by `, `.
- `UPDATED_TIME`: localized, concise format (for example `09:10 UTC`).
- If a value is missing, omit that segment; never render placeholders like `N/A`.

## Variant: Single Daily Report

Structure:

1. Headline (report title)
2. Day-at-a-glance
3. Metadata scanline
4. Optional cover image
5. Primary CTA button (`Read full report`)
6. Secondary text link (`Open in browser`)

Copy limits:

- Title: 90 chars target, 120 hard max
- Day-at-a-glance: 220 chars target, 320 hard max
- Tags: max 3

Behavior:

- Keep one dominant CTA above the fold on mobile.
- Image is optional and never required for comprehension.

## Variant: Digest 50

Structure:

1. Digest title
2. One short orientation sentence
3. Repeating equal-weight report rows
4. Footer with preference and unsubscribe links

Row anatomy:

1. Report title (linked)
2. Scanline metadata (compact)
3. Optional one-line context (`max 120 chars`)
4. Text CTA (`Read report`)

Density rules:

- No featured item at top; all reports are equal.
- Keep vertical rhythm consistent across all rows.
- Use separators between rows for visual chunking.
- Every row must remain readable without images.

## Metadata Mapping

Input metadata fields should map as follows:

- `title` -> headline/row title
- `day_at_a_glance` -> summary block (single) or digest orientation line
- `region` -> scanline region segment
- `priority` -> scanline priority segment
- `topics[]` -> scanline tags (truncate to first 3)
- `updated_at` -> scanline time segment
- `report_url` -> title link + CTA link
- `image_url` -> optional single-mode cover image

## Truncation and Fallback Rules

- Long title: trim at word boundary and add `...`.
- Long tags: keep first 3 only.
- Missing image: remove image block entirely.
- Missing day-at-a-glance: use one neutral fallback sentence.
- Missing priority: hide priority segment (do not fabricate).

## Readability Targets

- First actionable link visible within initial viewport on 320px width.
- Readers should parse at least 5 digest rows without scrolling fatigue.
- Maximum one paragraph block before first CTA in single mode.
