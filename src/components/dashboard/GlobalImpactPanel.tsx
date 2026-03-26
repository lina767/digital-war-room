import type { ConflictData } from "@/types/conflict";
import { Globe } from "lucide-react";
import { IntelPanel } from "@/components/dashboard/IntelPanel";
import { AgentMetaFooter } from "@/components/dashboard/AgentMetaFooter";
import { DASHBOARD_PANEL_TOOLTIPS } from "@/lib/dashboardPanelCopy";

const GLOBAL_IMPACT_PREFIX = "global impact";

interface GlobalImpactPanelProps {
  data: ConflictData | null;
  embedded?: boolean;
}

/** Filters key_findings that contain "Global impact" (e.g. oil/Hormuz/chokepoint). */
function getGlobalImpactFindings(keyFindings: string[]): string[] {
  return keyFindings.filter((f) => f.toLowerCase().includes(GLOBAL_IMPACT_PREFIX));
}

export function GlobalImpactPanel({ data, embedded = false }: GlobalImpactPanelProps) {
  const note = data?.energy?.global_impact_note ?? null;
  const keyFindings = data?.key_findings ?? [];
  const globalFindings = getGlobalImpactFindings(keyFindings);
  const hasNote = note && note.trim().length > 0;
  const hasFindings = globalFindings.length > 0;
  const hasContent = hasNote || hasFindings;

  if (!hasContent) return null;

  return (
    <IntelPanel
      title="GLOBAL IMPACT"
      icon={<Globe className="h-3.5 w-3.5 text-muted-foreground" />}
      tooltipContent={DASHBOARD_PANEL_TOOLTIPS["GLOBAL IMPACT"]}
      embedded={embedded}
    >
      {hasNote && (
        <p className="text-xs leading-relaxed text-foreground">{note}</p>
      )}
      {hasFindings && (
        <ul className="space-y-1.5">
          {globalFindings.map((f, i) => (
            <li key={i} className="text-xs leading-relaxed flex gap-2">
              <span className="flex-shrink-0 h-1.5 w-1.5 rounded-full bg-primary mt-1.5" />
              <span>{f}</span>
            </li>
          ))}
        </ul>
      )}
      <AgentMetaFooter meta={data?.energy?._meta} />
    </IntelPanel>
  );
}
