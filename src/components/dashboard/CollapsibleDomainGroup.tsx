import { useState, useEffect, useCallback } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FeedDomainId } from "./feedSectionConfig";
import { FEED_DOMAINS_STORAGE_KEY, FEED_DOMAINS } from "./feedSectionConfig";

interface CollapsibleDomainGroupProps {
  domainId: FeedDomainId;
  children: React.ReactNode;
  className?: string;
}

function loadDomainState(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(FEED_DOMAINS_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Record<string, boolean>;
      if (typeof parsed === "object" && parsed !== null) return parsed;
    }
  } catch {
    // ignore
  }
  return {};
}

function saveDomainState(state: Record<string, boolean>) {
  try {
    localStorage.setItem(FEED_DOMAINS_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore
  }
}

export function CollapsibleDomainGroup({
  domainId,
  children,
  className,
}: CollapsibleDomainGroupProps) {
  const config = FEED_DOMAINS[domainId];
  const defaultOpen = config.defaultOpen;
  const [open, setOpen] = useState(() => {
    const stored = loadDomainState()[domainId];
    return typeof stored === "boolean" ? stored : defaultOpen;
  });

  useEffect(() => {
    const stored = loadDomainState();
    const next = { ...stored, [domainId]: open };
    saveDomainState(next);
  }, [domainId, open]);

  const toggle = useCallback(() => setOpen((o) => !o), []);

  const contentId = `domain-content-${domainId}`;

  return (
    <div className={cn("space-y-2", className)}>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={contentId}
        className="flex items-center gap-1.5 w-full text-left py-1.5 px-0 rounded-md hover:bg-muted/50 transition-colors"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
        )}
        <span className="font-mono text-[11px] font-medium text-foreground tracking-wider uppercase">
          {config.label}
        </span>
      </button>
      {open && (
        <div id={contentId} role="region" className="space-y-4 pl-1">
          {children}
        </div>
      )}
    </div>
  );
}
