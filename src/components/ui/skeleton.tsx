import * as React from "react";
import { cn } from "@/lib/utils";

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}

/** Full-page loading fallback: card-like skeleton stack instead of spinner */
function PageSkeleton() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background p-6" aria-busy="true" aria-label="Loading">
      <div className="flex w-full max-w-md flex-col gap-4">
        <Skeleton className="h-8 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="mt-4 h-24 w-full" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-4/5" />
      </div>
    </div>
  );
}

/** Inline text-placeholder skeleton (e.g. "Loading analysis…" replacement) */
function TextSkeleton({ lines = 2, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={cn("h-4", i === lines - 1 && lines > 1 ? "w-3/4" : "w-full")} />
      ))}
    </div>
  );
}

/** Map/panel loading overlay: skeleton tiles instead of spinner */
function MapLoadingSkeleton() {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-background/50 pointer-events-none p-4">
      <div className="grid grid-cols-3 gap-2 w-full max-w-xs">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="aspect-square rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-3 w-32" />
    </div>
  );
}

export { Skeleton, PageSkeleton, TextSkeleton, MapLoadingSkeleton };
