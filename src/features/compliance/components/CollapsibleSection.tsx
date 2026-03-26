import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

export function ZoneTypeBadge({ type }: { type: string }) {
  const cls =
    type === "sanctions"
      ? "bg-destructive/80 text-destructive-foreground"
      : type === "embargo"
        ? "bg-orange-500/80 text-black"
        : "bg-yellow-400/60 text-black";
  return (
    <span className={`px-1.5 py-0.5 rounded text-[11px] font-mono uppercase ${cls}`}>
      {type}
    </span>
  );
}

export function CollapsibleSection({
  icon,
  label,
  count,
  defaultOpen = true,
  sectionId,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  count: number;
  defaultOpen?: boolean;
  sectionId?: string;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(defaultOpen);
  const contentId = sectionId ?? `collapse-${label.replace(/\s+/g, "-").toLowerCase()}`;
  if (count === 0) return null;

  return (
    <div className="space-y-1.5" id={sectionId}>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-controls={contentId}
        className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground w-full"
      >
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {icon}
        <span>
          {label} ({count})
        </span>
      </button>
      {expanded && (
        <div id={contentId} className="space-y-1.5 pl-4" role="region">
          {children}
        </div>
      )}
    </div>
  );
}
