import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

export interface PatternFlag {
  id?: string;
  severity?: string;
  category?: string;
  title?: string;
  detail?: string;
}

interface PatternFlagsBannerProps {
  flags: PatternFlag[];
  className?: string;
}

export function PatternFlagsBanner({ flags, className }: PatternFlagsBannerProps) {
  if (!flags.length) return null;
  return (
    <div
      className={cn(
        "border-b border-warning/30 bg-warning/5 px-3 py-2 lg:py-1.5",
        className,
      )}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-start gap-2 min-w-0">
        <AlertTriangle className="h-4 w-4 text-warning shrink-0 mt-0.5" aria-hidden />
        <div className="min-w-0 flex-1 space-y-1.5">
          <p className="text-[10px] font-mono uppercase tracking-wider text-warning/90">Data pattern watch</p>
          <ul className="space-y-1.5">
            {flags.map((f, i) => (
              <li key={f.id ?? i} className="text-xs leading-snug">
                <span
                  className={cn(
                    "font-medium",
                    (f.severity ?? "").toLowerCase() === "high" ? "text-warning" : "text-foreground/90",
                  )}
                >
                  {f.title ?? "Pattern"}
                </span>
                {f.detail ? <span className="text-muted-foreground"> — {f.detail}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
