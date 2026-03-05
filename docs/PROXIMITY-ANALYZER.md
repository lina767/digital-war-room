# Proximity Analyzer

Correlates **strike data** (NASA FIRMS thermal anomalies) with **civilian infrastructure** (OpenStreetMap) to flag potential Human Shield scenarios.

## Components

- **Backend:** `GET /api/proximity/strikes?region=...&days=3` – returns NASA FIRMS VIIRS_SNPP_NRT thermal anomalies (strike triggers).
- **Frontend service:** `src/lib/proximityAnalyzerService.ts` – fetches strikes, queries Overpass API (schools, hospitals, places of worship, government offices within 300 m), correlates with **Turf.js** (haversine distance), returns evidence list.
- **UI:** `src/components/dashboard/EvidenceCard.tsx` – displays facility name, distance to strike, risk badge (Red/Orange), and summary.

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
