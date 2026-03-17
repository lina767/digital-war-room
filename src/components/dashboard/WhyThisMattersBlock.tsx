/**
 * Compact "Why this matters" block for alerts and findings.
 * Renders 2–3 sentence contextual explanation when provided by the backend.
 */
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

interface WhyThisMattersBlockProps {
  text: string;
  className?: string;
  /** When true, render as a small inline block; when false, as a subtle expandable or always-visible block. */
  compact?: boolean;
}

export function WhyThisMattersBlock({ text, className, compact = true }: WhyThisMattersBlockProps) {
  if (!text?.trim()) return null;

  return (
    <div
      className={cn(
        "flex gap-2 rounded-md border border-border/60 bg-muted/20 px-2.5 py-1.5",
        compact ? "text-[11px]" : "text-xs",
        className
      )}
      role="note"
      aria-label="Why this matters"
    >
      <Info className="h-3 w-3 text-muted-foreground flex-shrink-0 mt-0.5" />
      <p className="text-muted-foreground leading-relaxed min-w-0">
        {text}
      </p>
    </div>
  );
}
