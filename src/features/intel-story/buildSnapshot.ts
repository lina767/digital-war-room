import type { ConflictData } from "@/types/conflict";
import { INTEL_STORY_VERSION, type IntelStorySnapshot } from "./types";

export function buildIntelStorySnapshot(
  conflict: string,
  data: ConflictData | null,
  opts?: { exportedAt?: Date },
): IntelStorySnapshot {
  const exportedAt = (opts?.exportedAt ?? new Date()).toISOString();
  if (!data) {
    return {
      v: INTEL_STORY_VERSION,
      conflict,
      exportedAt,
    };
  }
  return {
    v: INTEL_STORY_VERSION,
    conflict: data.conflict ?? conflict,
    exportedAt,
    threat_level: typeof data.threat_level === "string" ? data.threat_level : undefined,
    escalation_score: typeof data.escalation_score === "number" ? data.escalation_score : undefined,
    summary: typeof data.summary === "string" ? data.summary : undefined,
    narrative_story: typeof data.narrative_story === "string" ? data.narrative_story : undefined,
    key_findings: Array.isArray(data.key_findings) ? data.key_findings.filter((x): x is string => typeof x === "string") : undefined,
    analysis_run_id: typeof data.analysis_run_id === "string" ? data.analysis_run_id : undefined,
  };
}
