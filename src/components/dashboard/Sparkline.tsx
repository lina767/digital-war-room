/**
 * Minimal SVG sparkline for historical comparison (e.g. 7–30 day trend).
 * Renders when values array has at least 2 points.
 */
import { useMemo } from "react";
import { cn } from "@/lib/utils";

interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  className?: string;
  /** Optional label e.g. "Last 30 days" */
  label?: string;
}

export function Sparkline({ values, width = 64, height = 24, className, label }: SparklineProps) {
  const path = useMemo(() => {
    if (!values || values.length < 2) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const pad = 2;
    const w = width - pad * 2;
    const h = height - pad * 2;
    const step = w / (values.length - 1);
    const points = values.map((v, i) => {
      const x = pad + i * step;
      const y = pad + h - ((v - min) / range) * h;
      return `${x},${y}`;
    });
    return `M ${points.join(" L ")}`;
  }, [values, width, height]);

  if (!path) return null;

  return (
    <div className={cn("flex items-center gap-1.5", className)} title={label}>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="text-muted-foreground/80"
        aria-hidden
      >
        <path
          d={path}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {label && (
        <span className="text-[10px] text-muted-foreground font-mono">{label}</span>
      )}
    </div>
  );
}
