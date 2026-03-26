import { Shield, Info } from "lucide-react";
import { IntelPanel } from "@/components/dashboard/IntelPanel";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { DASHBOARD_PANEL_TOOLTIPS } from "@/lib/dashboardPanelCopy";
import {
  COMPLIANCE_DISCLAIMER,
  COMPLIANCE_INTRO_FULL,
  COMPLIANCE_INTRO_SHORT,
  COMPLIANCE_NO_ALERTS_TEXT,
} from "@/lib/complianceCopy";
import type { ConflictData } from "@/types/conflict";
import {
  AISAnomaliesSection,
  ComplianceZonesSection,
  DocumentManagementSection,
  GeofencingAlertsSection,
  RiskScoreDisplay,
  SanctionsListsSection,
} from "./compliance";
import { DocumentQASection, RouteScreeningSection, SanctionsSearchSection } from "@/features/compliance";

interface CompliancePanelProps {
  data: ConflictData | null;
  embedded?: boolean;
}

export function CompliancePanel({ data, embedded = false }: CompliancePanelProps) {
  const compliance = data?.compliance;
  const alerts = compliance?.geofencing_alerts ?? [];
  const anomalies = compliance?.ais_anomalies ?? [];
  const riskScore = compliance?.risk_score;
  const sigintSummary = compliance?.sigint_window_summary;
  const hasRealtimeSignals = alerts.length > 0 || anomalies.length > 0;

  const scrollToSection = (sectionId: string) => {
    document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <IntelPanel
      title="SANCTIONS COMPLIANCE"
      icon={<Shield className="h-3.5 w-3.5 text-muted-foreground" />}
      tooltipContent={DASHBOARD_PANEL_TOOLTIPS["SANCTIONS COMPLIANCE"]}
      embedded={embedded}
    >
      <TooltipProvider>
        <p className="text-[11px] text-muted-foreground flex items-start gap-1.5">
          <span>{COMPLIANCE_INTRO_SHORT}</span>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="shrink-0 cursor-help text-muted-foreground/80 hover:text-foreground" aria-label="More information">
                <Info className="h-3.5 w-3.5" />
              </span>
            </TooltipTrigger>
            <TooltipContent side="right" className="max-w-[320px] text-xs">
              {COMPLIANCE_INTRO_FULL}
            </TooltipContent>
          </Tooltip>
        </p>

        {riskScore && (
          <ErrorBoundary sectionLabel="Compliance Risk">
            <RiskScoreDisplay riskScore={riskScore} onDriverClick={scrollToSection} />
          </ErrorBoundary>
        )}

        {compliance && (
          <ErrorBoundary sectionLabel="Sanctions Lists">
            <SanctionsListsSection compliance={compliance} />
          </ErrorBoundary>
        )}

        <ErrorBoundary sectionLabel="Sanctions Search">
          <SanctionsSearchSection data={data} />
        </ErrorBoundary>

        <ErrorBoundary sectionLabel="Route Screening">
          <RouteScreeningSection />
        </ErrorBoundary>

        <ErrorBoundary sectionLabel="Zones">
          <ComplianceZonesSection />
        </ErrorBoundary>

        <ErrorBoundary sectionLabel="Document QA">
          <DocumentQASection data={data} />
        </ErrorBoundary>

        <ErrorBoundary sectionLabel="Document Management">
          <DocumentManagementSection />
        </ErrorBoundary>

        <div id="geofencing-alerts">
          <ErrorBoundary sectionLabel="Geofencing Alerts">
            <GeofencingAlertsSection alerts={alerts} />
          </ErrorBoundary>
        </div>

        <div id="ais-anomalies">
          <ErrorBoundary sectionLabel="AIS Anomalies">
            <AISAnomaliesSection anomalies={anomalies} />
          </ErrorBoundary>
        </div>

        {!hasRealtimeSignals && (
          <div className="space-y-0.5">
            <p className="text-[11px] text-muted-foreground">{COMPLIANCE_NO_ALERTS_TEXT}</p>
            {sigintSummary != null && (
              <p className="text-[11px] text-muted-foreground/90">
                This run: {sigintSummary.aircraft_count} aircraft, {sigintSummary.ships_count} ships in conflict region; none in sanctions zones.
              </p>
            )}
          </div>
        )}

        <p className="text-[11px] text-muted-foreground border-t border-border/50 pt-2">
          {compliance?.disclaimer ?? COMPLIANCE_DISCLAIMER}
        </p>
      </TooltipProvider>
    </IntelPanel>
  );
}
