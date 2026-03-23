import type { AgentMeta } from "@/lib/api";
import type { ConflictData } from "@/hooks/useConflictWebSocket";
import type { FindingConfidenceLevel } from "@/components/dashboard/FindingConfidenceBadge";
import { normalizeFindingConfidence } from "@/components/dashboard/FindingConfidenceBadge";

export type DataQualityLevel = "live" | "estimated" | "degraded";

/** Per-agent source-health + feed quality from analysis payload (_meta + CEO agent_data_confidence). */
export function getAgentConfidenceFromConflict(
  conflictData: ConflictData | null | undefined,
  backendKey: string,
): {
  scoreLevel: FindingConfidenceLevel | null;
  dataQuality: DataQualityLevel | null;
  tooltip: string;
} {
  if (!conflictData) {
    return { scoreLevel: null, dataQuality: null, tooltip: "" };
  }
  const raw = (conflictData as Record<string, unknown>)[backendKey];
  if (!raw || typeof raw !== "object") {
    return { scoreLevel: null, dataQuality: null, tooltip: "" };
  }
  const block = raw as Record<string, unknown>;
  const meta = block._meta as AgentMeta | undefined;

  let scoreLevel: FindingConfidenceLevel | null = null;
  const conf = meta?.confidence;
  if (conf && typeof conf === "object" && "level" in conf) {
    const lv = (conf as { level?: string }).level;
    if (lv) scoreLevel = normalizeFindingConfidence(lv);
  }

  let dataQuality: DataQualityLevel | null =
    (meta?.data_confidence as DataQualityLevel | undefined) ??
    (conflictData.agent_data_confidence?.[backendKey] as DataQualityLevel | undefined) ??
    null;
  if (backendKey === "chokepoint" && typeof block.data_confidence === "string") {
    const dq = block.data_confidence.toLowerCase();
    if (dq === "live" || dq === "estimated" || dq === "degraded") {
      dataQuality = dq;
    }
  }

  const parts: string[] = [];
  if (conf && typeof conf === "object") {
    const c = conf as { level?: string; sources_ok?: string[]; sources_missing?: string[] };
    if (c.level) parts.push(`Source health: ${c.level}`);
    if (c.sources_ok?.length) parts.push(`OK: ${c.sources_ok.join(", ")}`);
    if (c.sources_missing?.length) parts.push(`Missing: ${c.sources_missing.join(", ")}`);
  }
  if (dataQuality) parts.push(`Data quality: ${dataQuality}`);

  return {
    scoreLevel,
    dataQuality,
    tooltip: parts.join(" · "),
  };
}
