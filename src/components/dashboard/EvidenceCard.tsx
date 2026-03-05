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

export function EvidenceCard({ evidence, className }: EvidenceCardProps) {
  const { facilityName, facilityType, distanceMeters, riskLabel, summary } = evidence;
  const badgeConfig = getRiskBadgeVariant(riskLabel);
  const distanceRounded = Math.round(distanceMeters);

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
      </CardHeader>
      <CardContent className="pt-0">
        <p className="text-sm text-muted-foreground leading-relaxed">
          {summary}
        </p>
      </CardContent>
    </Card>
  );
}
