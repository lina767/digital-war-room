import type { RootCauseSuggestion } from "@/hooks/useConflictWebSocket";

export function RootCauseSuggestions({ items }: { items: RootCauseSuggestion[] }) {
  if (!items?.length) return null;
  return (
    <div className="mb-3 rounded-md border border-border/80 bg-muted/20 px-3 py-2.5">
      <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-2">Likely drivers (hypotheses)</p>
      <p className="text-[10px] text-muted-foreground/90 mb-2 leading-snug">
        Observable signals mapped to plausible causes – analytic hypotheses, not verified facts.
      </p>
      <ul className="space-y-2 list-none m-0 p-0">
        {items.map((item, i) => (
          <li key={i} className="text-xs leading-relaxed">
            <span className="font-medium text-foreground">{item.signal}</span>
            <span className="text-muted-foreground mx-1.5" aria-hidden>
              →
            </span>
            <span className="text-muted-foreground">{item.likely_cause}</span>
            {item.confidence ? (
              <span className="ml-1.5 text-[10px] font-mono text-muted-foreground/70">({item.confidence})</span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
