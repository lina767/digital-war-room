# Conflict Prioritization

This document defines how new theaters are added to Digital War Room and in which order.

## Core Theater Portfolio

The short-term core portfolio is:

- `Middle East`
- `Ukraine`
- `Red Sea and Horn of Africa`
- `Taiwan Strait`

These theaters are prioritized because they combine high escalation relevance with strong multi-stream data coverage.

## Readiness Score

Each conflict is evaluated on four dimensions (0-100):

- `Signal density` (frequency/volume of meaningful events)
- `Data quality` (source reliability and continuity)
- `User demand` (product and analyst demand)
- `Strategic impact` (regional/global consequences)

Weighted score formula:

`readiness = signalDensity*0.30 + dataQuality*0.25 + userDemand*0.20 + strategicImpact*0.25`

Implementation reference:

- `src/lib/conflictReadiness.ts`

## Rollout Phases

1. **Phase A**: Promote `Ukraine` to first-class selector + actor/ranking mappings.
2. **Phase B**: Add `Taiwan Strait` to core focus and tune conflict-specific ranking queries.
3. **Phase C**: Operationalize `Sahel` and `Sudan` as expansion cluster.
4. **Phase D**: Add tier-3 theaters only when tied to explicit use cases (compliance, supply chain, humanitarian).

## Inclusion Criteria

A new theater should be added when at least 3 of the following are met:

- High geopolitical or macroeconomic relevance
- Coverage in at least 6 of 12 intelligence streams
- Clear user demand / operational question
- Stable source quality without persistent hard paywalls or severe rate limits
