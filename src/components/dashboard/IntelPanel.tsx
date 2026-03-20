import { Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

interface IntelPanelProps {
  title: string;
  icon?: React.ReactNode;
  headerRight?: React.ReactNode;
  /** Optional "What is this?" tooltip text; when set, an info icon is shown in the header. */
  tooltipContent?: string;
  /** When true, render content only without panel frame/header (for nested usage). */
  embedded?: boolean;
  children: React.ReactNode;
  className?: string;
}

export function IntelPanel({ title, icon, headerRight, tooltipContent, embedded, children, className }: IntelPanelProps) {
  if (embedded) {
    return <div className={cn("p-3 space-y-3 min-w-0", className)}>{children}</div>;
  }

  return (
    <div className={cn("rounded-lg border border-border bg-card overflow-hidden transition-colors duration-200 hover:border-primary/20", className)}>
      <div className="px-3 py-2 border-b border-border bg-muted/30 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          {icon}
          <h3 className="font-mono text-xs text-muted-foreground tracking-wider truncate">{title}</h3>
          {tooltipContent && (
            <TooltipProvider delayDuration={200}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="shrink-0 cursor-help text-muted-foreground/80 hover:text-foreground" aria-label="What is this?">
                    <Info className="h-3 w-3" />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="max-w-[280px] text-xs">
                  {tooltipContent}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
        {headerRight && <div className="flex items-center gap-1.5 flex-shrink-0">{headerRight}</div>}
      </div>
      <div className="p-3 space-y-3 min-w-0">{children}</div>
    </div>
  );
}

export function IntelPanelSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <div className="px-3 py-2 border-b border-border bg-muted/30">
        <div className="h-3 w-32 bg-muted/50 rounded animate-pulse" />
      </div>
      <div className="p-3 space-y-2.5">
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} className="h-3 rounded bg-muted/50 animate-pulse" style={{ width: `${85 - i * 15}%` }} />
        ))}
      </div>
    </div>
  );
}
