# Proximity Analyzer

Correlates **strike data** (NASA FIRMS thermal anomalies) with **civilian infrastructure** (OpenStreetMap) to flag potential Human Shield scenarios.

**Requirements:** `NASA_FIRMS_KEY` must be set in `backend/.env` for thermal anomaly data. If missing, the agent and `GET /api/proximity/analyze` return empty evidence with `reason_empty: "no_strikes"` and an `error_message` (e.g. "NASA_FIRMS_KEY not set"). To verify the pipeline (FIRMS + Overpass), run: `node scripts/test-proximity.mjs`.

## Components

- **Backend:** `GET /api/proximity/analyze?region=...&days=3` – runs full proximity analysis server-side: fetches NASA FIRMS thermal anomalies, queries Overpass for schools/hospitals/government within 300 m, returns `{ evidence, region, days }` and optionally `reason_empty`, `error_message` when evidence is empty.
- **Frontend service:** `src/lib/proximityAnalyzerService.ts` – client-side fallback; the Dashboard uses the backend endpoint for the "Run" button and main analysis.
- **UI:** `src/components/dashboard/EvidenceCard.tsx` – displays facility name, distance to strike, risk badge (Red/Orange), and summary. When evidence is empty, the panel shows `reason_empty` (no_strikes / no_facilities_near_strikes / error) and `error_message` where applicable. A "Run" button triggers an on-demand analysis via `GET /api/proximity/analyze`.

## Risk labels

- **CRITICAL_PROXIMITY:** strike &lt; 50 m from facility.
- **HIGH_RISK:** strike &lt; 150 m.
- **PROBABLE_HUMAN_SHIELD:** same as above **and** a suspected military site (from optional GeoJSON) is within 100 m of the **same** civilian facility.
- **ELEVATED:** 150–300 m (informational).

## Usage

```ts
import { runProximityAnalysis } from "@/lib/proximityAnalyzerService";
import { EvidenceCard } from "@/components/dashboard/EvidenceCard";

const evidence = await runProximityAnalysis("iran", 3);
evidence.forEach((e) => {
  // render <EvidenceCard key={...} evidence={e} />
});
```

Optional: pass `militarySites` (GeoJSON FeatureCollection of points) as third argument to enable PROBABLE_HUMAN_SHIELD. Rate-limiting: ~1 Overpass request per second to avoid 429.
