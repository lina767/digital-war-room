/**
 * Quick test: backend /api/proximity/strikes + one Overpass call + distance check.
 * Run: node scripts/test-proximity.mjs
 * Requires: backend running (e.g. uvicorn), NASA_FIRMS_KEY in backend .env
 */
const API_BASE = process.env.VITE_API_URL || "http://127.0.0.1:8000";

async function main() {
  console.log("1. Fetching strikes from", API_BASE + "/api/proximity/strikes?region=middle_east&days=3");
  const strikeRes = await fetch(API_BASE + "/api/proximity/strikes?region=middle_east&days=3", {
    signal: AbortSignal.timeout(35000),
  });
  if (!strikeRes.ok) {
    console.error("Strikes failed:", strikeRes.status, await strikeRes.text());
    process.exit(1);
  }
  const strikeData = await strikeRes.json();
  const strikes = strikeData.strikes || [];
  console.log("   Strikes count:", strikes.length);

  if (strikes.length === 0) {
    console.log("   No strikes in region (or NASA_FIRMS_KEY missing). Skipping Overpass.");
    process.exit(0);
  }

  const first = strikes[0];
  const lat = first.lat;
  const lon = first.lon;
  console.log("2. Querying Overpass for first strike", lat.toFixed(4), lon.toFixed(4));
  const query = `
[out:json][timeout:25];
(
  node(around:300,${lat},${lon})["amenity"~"school|hospital|place_of_worship"];
  way(around:300,${lat},${lon})["amenity"~"school|hospital|place_of_worship"];
  node(around:300,${lat},${lon})["office"="government"];
  way(around:300,${lat},${lon})["office"="government"];
);
out body center;
`.trim();
  const overpassRes = await fetch("https://overpass-api.de/api/interpreter", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "data=" + encodeURIComponent(query),
    signal: AbortSignal.timeout(30000),
  });
  if (!overpassRes.ok) {
    console.error("Overpass failed:", overpassRes.status, await overpassRes.text());
    process.exit(1);
  }
  const overpassJson = await overpassRes.json();
  const elements = overpassJson.elements || [];
  console.log("   Facilities in 300m:", elements.length);

  if (elements.length > 0) {
    const el = elements[0];
    let flon = el.lon, flat = el.lat;
    if (el.center) {
      flat = el.center.lat;
      flon = el.center.lon;
    }
    const name = (el.tags && (el.tags.name || el.tags["name:en"])) || "Unnamed";
    // Haversine approx for test (simplified)
    const R = 6371000; // m
    const dLat = ((flat - lat) * Math.PI) / 180;
    const dLon = ((flon - lon) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos((lat * Math.PI) / 180) * Math.cos((flat * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
    const dist = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    console.log("   Nearest facility:", name, "| distance ~", Math.round(dist), "m");
  }
  console.log("OK – Proximity pipeline (strikes + Overpass) works.");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
