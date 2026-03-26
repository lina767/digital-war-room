# Analytics Consent Policy (DWR)

## Decision

Analytics in DWR is consent-based. Tracking is disabled until the user explicitly opts in.

## Scope

- Frontend custom analytics events (including mobile event tracking).
- Page-level analytics component initialization.

## Behavior

- Default state: no analytics collection.
- On opt-in: analytics enabled and consent timestamp stored in local storage.
- On opt-out: analytics disabled and further tracking suppressed.

## Implementation references

- `src/components/AnalyticsConsentBanner.tsx`
- `src/lib/analyticsConsent.ts`
- `src/lib/mobileAnalytics.ts`
- `src/App.tsx`

## Review

Any changes to analytics provider usage or event taxonomy must update this document and the privacy notice.

