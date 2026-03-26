import { useState } from "react";
import { MapPin } from "lucide-react";
import { postComplianceRouteScreening, type RouteScreeningResult } from "@/lib/api";
import { CollapsibleSection } from "./CollapsibleSection";

export function RouteScreening() {
  const [routeLabel, setRouteLabel] = useState("");
  const [waypointsText, setWaypointsText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RouteScreeningResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!routeLabel.trim()) return;
    const lines = waypointsText.trim().split(/\n/).filter(Boolean);
    const waypoints = lines
      .slice(0, 20)
      .map((line) => {
        const parts = line.split(/[\t,;]+/).map((p) => p.trim());
        const label = parts[0] || "";
        const lat = parseFloat(parts[1] ?? "0");
        const lon = parseFloat(parts[2] ?? "0");
        const country_code = parts[3] ?? "";
        const port_type = parts[4] ?? "port";
        return { label, lat, lon, country_code, port_type };
      })
      .filter((wp) => !Number.isNaN(wp.lat) && !Number.isNaN(wp.lon));
    if (waypoints.length === 0) {
      setError("Add at least one waypoint (label, lat, lon per line).");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const data = await postComplianceRouteScreening({
        route_label: routeLabel.trim(),
        waypoints,
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <CollapsibleSection
      icon={<MapPin className="h-3 w-3 text-primary" />}
      label="ROUTE SCREENING"
      count={1}
      defaultOpen={false}
      sectionId="route-screening"
    >
      <form onSubmit={handleSubmit} className="space-y-2">
        <input
          type="text"
          placeholder="Route name (e.g. Bandar Abbas → Rotterdam)"
          value={routeLabel}
          onChange={(e) => setRouteLabel(e.target.value)}
          className="w-full rounded border border-border bg-background px-2 py-1 text-[11px]"
        />
        <textarea
          placeholder="One waypoint per line: label, lat, lon [, country_code, port_type]"
          value={waypointsText}
          onChange={(e) => setWaypointsText(e.target.value)}
          rows={3}
          className="w-full rounded border border-border bg-background px-2 py-1 text-[11px] font-mono resize-y"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded border border-border bg-primary/10 px-2 py-1 text-[11px] font-mono hover:bg-primary/20 disabled:opacity-50"
        >
          {loading ? "Screening…" : "Screen route"}
        </button>
      </form>
      {error && <p className="text-[11px] text-destructive">{error}</p>}
      {result && (
        <div className="space-y-1.5 mt-2">
          {result.touches_sanctions_zone && (
            <p className="text-[11px] font-semibold text-destructive">Route touches sanctions zone.</p>
          )}
          {result.zone_hits.length > 0 && (
            <div>
              <span className="text-[11px] text-muted-foreground">Zone hits:</span>
              {result.zone_hits.map((h, i) => (
                <p key={i} className="text-[11px] pl-2">
                  {h.waypoint} → <span className="font-mono">{h.zone_name}</span> ({h.zone_type})
                </p>
              ))}
            </div>
          )}
          {result.suspicious_hops.length > 0 && (
            <div>
              <span className="text-[11px] text-muted-foreground">Suspicious hops:</span>
              {result.suspicious_hops.map((h, i) => (
                <p key={i} className="text-[11px] pl-2">
                  {h.waypoint} ({h.country_code}): {h.hub_label} - {h.condition}
                </p>
              ))}
            </div>
          )}
          {!result.touches_sanctions_zone &&
            result.zone_hits.length === 0 &&
            result.suspicious_hops.length === 0 && (
              <p className="text-[11px] text-muted-foreground">No zone hits or intermediary flags.</p>
            )}
        </div>
      )}
    </CollapsibleSection>
  );
}

export { RouteScreening as RouteScreeningSection };
