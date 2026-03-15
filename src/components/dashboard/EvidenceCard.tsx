/**
 * EvidenceCard – Displays one Proximity Analyzer evidence item:
 * civilian facility name, distance to strike, risk badge, and AI-style summary.
 */
import * as React from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ProximityEvidence, RiskLabel } from "@/lib/proximityAnalyzerService";

export interface EvidenceCardProps {
  evidence: ProximityEvidence;
  className?: string;
}

function getRiskBadgeVariant(label: RiskLabel): { variant: "destructive" | "secondary"; className?: string } {
  switch (label) {
    case "CRITICAL_PROXIMITY":
    case "PROBABLE_HUMAN_SHIELD":
      return { variant: "destructive" };
    case "HIGH_RISK":
      return { variant: "secondary", className: "bg-orange-500/90 text-white border-orange-600 hover:bg-orange-600/90" };
    case "ELEVATED":
    default:
      return { variant: "secondary" };
  }
}

function getRiskLabelDisplay(label: RiskLabel): string {
  switch (label) {
    case "CRITICAL_PROXIMITY":
      return "Critical proximity";
    case "HIGH_RISK":
      return "High risk";
    case "PROBABLE_HUMAN_SHIELD":
      return "Probable human shield";
    case "ELEVATED":
    default:
      return "Elevated";
  }
}

function CoordLink({ lat, lon, label }: { lat: number; lon: number; label: string }) {
  const url = `https://www.google.com/maps?q=${lat},${lon}`;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="font-mono text-[11px] text-primary hover:underline"
      title="Open in Google Maps"
    >
      {label}: {lat.toFixed(4)}°, {lon.toFixed(4)}°
    </a>
  );
}

export function EvidenceCard({ evidence, className }: EvidenceCardProps) {
  const { facilityName, facilityType, distanceMeters, riskLabel, summary, strikeLat, strikeLon, facilityLat, facilityLon, strikeAcquired } = evidence;
  const badgeConfig = getRiskBadgeVariant(riskLabel);
  const distanceRounded = Math.round(distanceMeters);
  const hasCoords = typeof strikeLat === "number" && typeof strikeLon === "number";

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-base font-semibold leading-tight text-foreground">
            {facilityName}
          </h4>
          <Badge
            variant={badgeConfig.variant}
            className={badgeConfig.className}
            title={riskLabel}
          >
            {getRiskLabelDisplay(riskLabel)}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          {facilityType}
          {" · "}
          <span className="font-mono font-medium text-foreground/90">
            {distanceRounded} m
          </span>
          {" to strike"}
        </p>
        {strikeAcquired && (
          <p className="text-[10px] text-muted-foreground/80 mt-0.5">
            Strike acquired: {strikeAcquired}
          </p>
        )}
        {hasCoords && (
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[11px]">
            <CoordLink lat={strikeLat} lon={strikeLon} label="Strike" />
            {typeof facilityLat === "number" && typeof facilityLon === "number" && (
              <CoordLink lat={facilityLat} lon={facilityLon} label="Facility" />
            )}
          </div>
        )}
      </CardHeader>
      <CardContent className="pt-0">
        <p className="text-sm text-muted-foreground leading-relaxed">
          {summary}
        </p>
      </CardContent>
    </Card>
  );
}
