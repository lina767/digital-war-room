# Weekly Experiment Cadence (Newsletter)

Goal: improve decision value and readability without noisy, overlapping changes.

## Guardrails

- Run only **1-2 changes per week** in the newsletter.
- Keep one stable control variant each week.
- Do not change subject, BLUF, and finding order all at once.

## Weekly Loop

1. Pull KPI baseline snapshot from `GET /api/newsletter/kpi-baseline?days=14`.
2. Choose one hypothesis, e.g.:
   - Subject line framing
   - BLUF wording
   - Top finding ordering
   - CTA placement
3. Ship one variant for 7 days.
4. Review:
   - `newsletter_slot_click` by `utm_content`
   - `briefing_to_dashboard_click`
   - `return_24h_after_newsletter`
   - `ttv_avg_seconds`
5. Apply decision rule:
   - **Keep** if improvement is sustained for 2 consecutive sends.
   - **Kill** if it underperforms baseline for 2 consecutive sends.
   - **Iterate** only one parameter in the next week.

## Suggested Ops Template

- Week number
- Change tested
- Baseline metrics (last 14 days)
- Variant metrics (current week)
- Decision: keep / kill / iterate
- Next change
