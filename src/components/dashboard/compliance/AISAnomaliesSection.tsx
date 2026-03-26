import { Radio } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { AISAnomaly } from "@/hooks/useConflictWebSocket";
import { CollapsibleSection } from "./shared";

export function AISAnomaliesSection({ anomalies }: { anomalies: AISAnomaly[] }) {
  return (
    <CollapsibleSection
      icon={<Radio className="h-3 w-3 text-red-400" />}
      label="AIS ANOMALIES"
      count={anomalies.length}
      defaultOpen={true}
      sectionId="ais-anomalies"
    >
      {anomalies.slice(0, 10).map((a, i) => (
        <div key={`${a.asset_id}-${a.anomaly_type}-${i}`} className="rounded border border-border bg-background/50 px-2.5 py-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold truncate">{a.asset_name}</span>
            <div className="flex items-center gap-1">
              <span className={`px-1.5 py-0.5 rounded text-[11px] font-mono ${a.anomaly_type === "spoofing" ? "bg-red-500/80 text-white" : "bg-purple-500/80 text-white"}`}>
                {a.anomaly_type === "spoofing" ? "SPOOF" : "DARK"}
              </span>
              <span className={`px-1.5 py-0.5 rounded text-[11px] font-mono ${a.severity === "HIGH" ? "bg-orange-500/80 text-black" : "bg-yellow-400/60 text-black"}`}>
                {a.severity}
              </span>
              {a.confidence && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-muted/80 text-muted-foreground cursor-help">
                      {a.confidence}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="left" className="max-w-[200px] text-xs">
                    Heuristic confidence: {a.confidence === "HIGH" ? "strong indicator" : "moderate indicator"}.
                  </TooltipContent>
                </Tooltip>
              )}
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground mt-1 leading-snug">{a.detail}</p>
          {a.zone_name && (
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Zone: <span className="font-mono">{a.zone_name.replace(/_/g, " ")}</span>
            </p>
          )}
          {(a.gap_hours != null || a.last_seen_at != null) && (
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[10px] text-muted-foreground">
              {a.gap_hours != null && (
                <span>
                  Gap: <span className="font-mono">{a.gap_hours}h</span>
                </span>
              )}
              {a.last_seen_at != null && (
                <span>
                  Last seen:{" "}
                  <span className="font-mono">
                    {new Date(a.last_seen_at * 1000).toISOString().replace("T", " ").slice(0, 19)}Z
                  </span>
                </span>
              )}
            </div>
          )}
        </div>
      ))}
    </CollapsibleSection>
  );
}
