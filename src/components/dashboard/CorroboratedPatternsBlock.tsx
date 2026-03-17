import { useState } from "react";
import { ChevronDown, ChevronRight, Link2 } from "lucide-react";
import { cn } from "@/lib/utils";

export interface CorroboratedPattern {
  pattern_id?: string;
  summary?: string;
  agent_ids?: string[];
  evidence?: Array<{ agent: string; snippet_or_ref?: string }>;
}

interface CorroboratedPatternsBlockProps {
  patterns: CorroboratedPattern[];
  className?: string;
}

function PatternCard({ pattern }: { pattern: CorroboratedPattern }) {
  const [expanded, setExpanded] = useState(false);
  const agents = pattern.agent_ids ?? [];
  const evidence = pattern.evidence ?? [];
  const n = agents.length || evidence.length;

  return (
    <div className="rounded-lg border border-border bg-card/60 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full px-3 py-2 flex items-center justify-between gap-2 text-left hover:bg-muted/30 transition-colors"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono bg-primary/20 text-primary border border-primary/30">
            <Link2 className="h-2.5 w-2.5" />
            Corroborated by {n} agent{n !== 1 ? "s" : ""}
          </span>
          {pattern.summary && (
            <span className="text-xs text-muted-foreground truncate">{pattern.summary}</span>
          )}
        </div>
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
        )}
      </button>
      {expanded && (evidence.length > 0 || agents.length > 0) && (
        <div className="px-3 pb-3 pt-0 border-t border-border/60 space-y-2">
          {pattern.summary && (
            <p className="text-xs text-muted-foreground leading-relaxed pt-2">{pattern.summary}</p>
          )}
          <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider">Chain of evidence</p>
          <ul className="space-y-1.5">
            {evidence.length > 0
              ? evidence.map((e, i) => (
                  <li key={i} className="text-xs flex gap-2">
                    <span className="font-mono text-primary flex-shrink-0">{e.agent}</span>
                    {e.snippet_or_ref && (
                      <span className="text-muted-foreground min-w-0">{e.snippet_or_ref}</span>
                    )}
                  </li>
                ))
              : agents.map((a, i) => (
                  <li key={i} className="text-xs font-mono text-muted-foreground">
                    {a}
                  </li>
                ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function CorroboratedPatternsBlock({ patterns, className }: CorroboratedPatternsBlockProps) {
  if (!patterns?.length) return null;

  return (
    <div className={cn("space-y-2", className)}>
      <h3 className="font-mono text-[11px] text-muted-foreground tracking-wider flex items-center gap-1.5">
        <Link2 className="h-3.5 w-3.5" />
        CORROBORATED PATTERNS
      </h3>
      <div className="space-y-2">
        {patterns.map((p, i) => (
          <PatternCard key={p.pattern_id ?? i} pattern={p} />
        ))}
      </div>
    </div>
  );
}
