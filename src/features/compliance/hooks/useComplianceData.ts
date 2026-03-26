import { useMemo } from "react";
import { DEFAULT_CONFLICT } from "@/lib/conflictDefaults";
import type { ConflictData } from "@/types/conflict";

/** Shared derived compliance / conflict context for sanctions search & document QA. */
export function useComplianceData(data: ConflictData | null) {
  const actorNames = useMemo(
    () => (data?.actors ?? []).map((a) => a.name).filter(Boolean),
    [data?.actors],
  );
  const canScreenActors = actorNames.length > 0;

  const buildDocumentQAContext = useMemo(() => {
    return function buildDocumentQAContext() {
      const c = data?.compliance;
      if (!c) return undefined;
      const sample = c.ofac_sdn?.sample ?? [];
      const ofacSample: string[] = sample
        .map((s: { name?: string; type?: string; program?: string }) => {
          const name = s.name?.trim();
          if (!name) return "";
          const type = s.type;
          const program = s.program;
          if (type || program) return `${name} (${[type, program].filter(Boolean).join(", ")})`;
          return name;
        })
        .filter(Boolean);
      const programs = c.ofac_sdn?.programs ?? [];
      const ofacProgramsSummary =
        programs.length > 0
          ? programs
              .slice(0, 12)
              .map((p: { name?: string; count?: number }) => `${p.name ?? "?"} (${p.count ?? 0})`)
              .join(", ")
          : undefined;
      const riskLevel = c.risk_score?.level;
      const drivers = c.risk_score?.drivers ?? [];
      const riskDriversSummary =
        drivers.length > 0 ? drivers.slice(0, 6).map((d) => `${d.factor}: ${d.detail}`).join("; ") : undefined;
      return {
        ofac_sample: ofacSample.length > 0 ? ofacSample : undefined,
        ofac_programs_summary: ofacProgramsSummary,
        risk_level: riskLevel ?? undefined,
        risk_drivers_summary: riskDriversSummary,
      };
    };
  }, [data?.compliance]);

  const conflictKey = data?.conflict ?? DEFAULT_CONFLICT;

  return {
    actorNames,
    canScreenActors,
    buildDocumentQAContext,
    conflictKey,
  };
}
