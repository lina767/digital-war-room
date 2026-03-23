import { FindingCard } from "@/features/daily-briefing/components/FindingCard";
import type { Finding } from "@/features/daily-briefing/types/briefing.types";

interface KeyFindingsProps {
  findings: Finding[];
  expandedFindings: Set<string>;
  onToggleFinding: (id: string) => void;
}

export function KeyFindings({ findings, expandedFindings, onToggleFinding }: KeyFindingsProps) {
  return (
    <section id="briefing-developments" className="space-y-2">
      <h2 className="briefing-display text-2xl">Key Findings</h2>
      <div className="space-y-2">
        {findings.map((finding) => (
          <FindingCard
            key={finding.id}
            finding={finding}
            expanded={expandedFindings.has(finding.id)}
            onToggle={onToggleFinding}
          />
        ))}
      </div>
    </section>
  );
}
