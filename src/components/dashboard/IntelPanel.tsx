import { cn } from "@/lib/utils";

interface IntelPanelProps {
  title: string;
  icon?: React.ReactNode;
  headerRight?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function IntelPanel({ title, icon, headerRight, children, className }: IntelPanelProps) {
  return (
    <div className={cn("rounded-lg border border-border bg-card overflow-hidden transition-colors duration-200 hover:border-primary/20", className)}>
      <div className="px-3 py-2 border-b border-border bg-muted/30 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          {icon}
          <h3 className="font-mono text-xs text-muted-foreground tracking-wider truncate">{title}</h3>
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
