import { AlertTriangle } from "lucide-react";
import type { GeofencingAlert } from "@/types/conflict";
import { CollapsibleSection, ZoneTypeBadge } from "./shared";

export function GeofencingAlertsSection({ alerts }: { alerts: GeofencingAlert[] }) {
  return (
    <CollapsibleSection
      icon={<AlertTriangle className="h-3 w-3 text-orange-400" />}
      label="GEOFENCING ALERTS"
      count={alerts.length}
      defaultOpen={true}
      sectionId="geofencing-alerts"
    >
      {alerts.slice(0, 15).map((a, i) => (
        <div key={`${a.asset_id}-${a.zone_name}-${i}`} className="rounded border border-border bg-background/50 px-2.5 py-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold truncate">{a.asset_name}</span>
            <ZoneTypeBadge type={a.zone_type} />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground mt-1 min-w-0">
            <span>Zone</span>
            <span className="text-right font-mono truncate">{a.zone_name.replace(/_/g, " ")}</span>
            <span>Type</span>
            <span className="text-right">{a.asset_type}</span>
            <span>Position</span>
            <span className="text-right font-mono">
              {a.lat.toFixed(1)}° {a.lon.toFixed(1)}°
            </span>
            <span>Source</span>
            <span className="text-right">{a.source}</span>
            {a.first_seen_at != null && (
              <>
                <span>First seen</span>
                <span className="text-right font-mono text-[10px]">
                  {new Date(a.first_seen_at * 1000).toISOString().replace("T", " ").slice(0, 19)}Z
                </span>
              </>
            )}
            {a.last_seen_at != null && (
              <>
                <span>Last seen</span>
                <span className="text-right font-mono text-[10px]">
                  {new Date(a.last_seen_at * 1000).toISOString().replace("T", " ").slice(0, 19)}Z
                </span>
              </>
            )}
            {a.duration_hours != null && a.duration_hours >= 0 && (
              <>
                <span>Duration</span>
                <span className="text-right font-mono">{a.duration_hours}h</span>
              </>
            )}
          </div>
        </div>
      ))}
    </CollapsibleSection>
  );
}
