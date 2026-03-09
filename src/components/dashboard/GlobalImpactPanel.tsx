import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { Globe } from "lucide-react";

const GLOBAL_IMPACT_PREFIX = "global impact";

interface GlobalImpactPanelProps {
  data: ConflictData | null;
}

/** Filters key_findings that contain "Global impact" (e.g. oil/Hormuz/chokepoint). */
function getGlobalImpactFindings(keyFindings: string[]): string[] {
  return keyFindings.filter((f) => f.toLowerCase().includes(GLOBAL_IMPACT_PREFIX));
}

export function GlobalImpactPanel({ data }: GlobalImpactPanelProps) {
  const note = data?.energy?.global_impact_note ?? null;
  const keyFindings = data?.key_findings ?? [];
  const globalFindings = getGlobalImpactFindings(keyFindings);
  const hasNote = note && note.trim().length > 0;
  const hasFindings = globalFindings.length > 0;
  const hasContent = hasNote || hasFindings;

  if (!hasContent) return null;

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <div className="px-3 py-2 border-b border-border bg-muted/30 flex items-center gap-1.5">
        <Globe className="h-3.5 w-3.5 text-muted-foreground" />
        <h3 className="font-mono text-xs text-muted-foreground tracking-wider">GLOBAL IMPACT</h3>
      </div>
      <div className="p-3 space-y-2">
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
      </div>
    </div>
  );
}
