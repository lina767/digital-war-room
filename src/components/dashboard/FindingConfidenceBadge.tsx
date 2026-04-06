import { Badge } from "@/components/ui/badge";
import type { FindingConfidenceLevel } from "@/components/dashboard/findingConfidence";

const LABEL: Record<FindingConfidenceLevel, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

const VARIANT: Record<FindingConfidenceLevel, string> = {
  high: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  medium: "bg-amber-500/15 text-amber-200 border-amber-500/35",
  low: "bg-slate-500/20 text-slate-300 border-slate-500/40",
};

interface FindingConfidenceBadgeProps {
  level: FindingConfidenceLevel;
  className?: string;
}

/** Compact label for key-finding assessment confidence (not model logprobs). */
export function FindingConfidenceBadge({ level, className = "" }: FindingConfidenceBadgeProps) {
  return (
    <Badge
      variant="outline"
      className={`text-[9px] font-mono uppercase tracking-wide px-1.5 py-0 h-5 shrink-0 ${VARIANT[level]} ${className}`}
      title={`Confidence: ${LABEL[level]}`}
    >
      {LABEL[level]}
    </Badge>
  );
}
