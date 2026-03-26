import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { LISTS_COVERED_NOTE } from "@/lib/complianceCopy";

export function SanctionsListsSection({
  compliance,
}: {
  compliance: NonNullable<ConflictData["compliance"]>;
}) {
  const ofacTotal = compliance.ofac_sdn?.total_matches ?? 0;
  const euMentions = compliance.eu_sanctions?.keyword_mentions ?? 0;
  const ofacPrograms = compliance.ofac_sdn?.programs ?? [];
  const ofacError = compliance.ofac_sdn?.error;
  const euError = compliance.eu_sanctions?.error;

  if (ofacTotal === 0 && euMentions === 0 && !ofacError && !euError) return null;

  const sample = compliance.ofac_sdn?.sample ?? [];

  return (
    <div id="sanctions-lists" className="rounded-md border border-border/60 bg-background/50 px-3 py-2 space-y-1">
      <span className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider">
        Sanctions Lists (DIPLO Agent)
      </span>
      <div className="space-y-0.5">
        {ofacTotal > 0 && (
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[11px] text-muted-foreground">OFAC SDN entries</span>
            <span className="font-mono text-xs font-semibold text-foreground">{ofacTotal}</span>
          </div>
        )}
        {ofacError && ofacTotal === 0 && (
          <p className="text-[11px] text-orange-400">
            OFAC SDN fetch failed (large CSV download). Regime-level scoring still active.
          </p>
        )}
        {euMentions > 0 && (
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[11px] text-muted-foreground">EU sanctions mentions</span>
            <span className="font-mono text-xs font-semibold text-foreground">{euMentions}</span>
          </div>
        )}
        {euError && euMentions === 0 && (
          <p className="text-[11px] text-orange-400">EU sanctions fetch failed.</p>
        )}
      </div>
      {ofacPrograms.length > 0 && (
        <div className="mt-0.5">
          <span className="text-[11px] text-muted-foreground">Programs: </span>
          <span className="text-[11px] text-muted-foreground/80">
            {ofacPrograms
              .slice(0, 6)
              .map((p) => `${p.name} (${p.count})`)
              .join(", ")}
          </span>
        </div>
      )}
      {sample.length > 0 && (
        <p className="text-[11px] text-muted-foreground leading-snug">
          Sample: {sample.slice(0, 3).map((s) => s.name).filter(Boolean).join(" · ")}
        </p>
      )}
      <p className="text-[10px] text-muted-foreground/80 pt-0.5">{LISTS_COVERED_NOTE}</p>
    </div>
  );
}
