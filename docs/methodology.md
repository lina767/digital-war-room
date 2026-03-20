# Methodology

This page defines the scoring and interpretation model used by Digital War Room.

Interactive page: <https://digital-war-room.com/methodology>

## Composite escalation score

Each agent returns a normalized score in the range `[0, 100]`.

The composite score is computed as a weighted sum:

`S = Σ (w_i * s_i)`

Where:

- `s_i` is the score from agent `i`
- `w_i` is the weight for agent `i`
- `Σ w_i = 1` (or 100%)

The weighting emphasizes leading indicators such as signal/mobility and chokepoint stress while preserving broad coverage across narrative, cyber, energy, and political streams.

## Threat level mapping

Default rule-based thresholds:

- `CRITICAL`: `S >= 80`
- `HIGH`: `60 <= S < 80`
- `ELEVATED`: `40 <= S < 60`
- `LOW`: `20 <= S < 40`
- `MINIMAL`: `S < 20`

When enabled, supervisor synthesis can refine interpretation, but threshold mapping remains the deterministic baseline.

## Peak-weighted predictive block

For short-horizon escalation interpretation, a peak-weighted variant can increase influence of the highest-activity streams:

- compute average of top-3 stream scores
- blend with composite score
- use `max(composite, peakWeighted)` for conservative escalation sensitivity

This avoids underestimating escalation when several high-signal streams spike simultaneously.

## Narrative/Signal Framework

The Signal Framework compares narrative asymmetries (state-aligned vs exile/independent sources) and contributes qualitative outputs:

- synthesis probability
- source comparison table
- latency and credibility gap signals

This layer informs interpretation but is distinct from the numeric composite score.

Related pages:

- How It Works: <https://digital-war-room.com/how-it-works>
- Source Directory: <https://digital-war-room.com/sources>
- Documentation hub: <https://digital-war-room.com/docs/documentation>
