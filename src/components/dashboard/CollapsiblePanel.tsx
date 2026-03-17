import { useState, useEffect, useCallback } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FeedSectionId } from "./feedSectionConfig";
import { FEED_SECTIONS_STORAGE_KEY, getSectionDefaultOpen } from "./feedSectionConfig";

interface CollapsiblePanelProps {
  sectionId: FeedSectionId;
  title: string;
  /** Optional right-side content in the header (e.g. "2 min ago"). */
  headerRight?: React.ReactNode;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

function loadSectionState(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(FEED_SECTIONS_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Record<string, boolean>;
      if (typeof parsed === "object" && parsed !== null) return parsed;
    }
  } catch {
    // ignore
  }
  return {};
}

function saveSectionState(state: Record<string, boolean>) {
  try {
    localStorage.setItem(FEED_SECTIONS_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore
  }
}

export function CollapsiblePanel({
  sectionId,
  title,
  headerRight,
  icon,
  children,
  className,
}: CollapsiblePanelProps) {
  const defaultOpen = getSectionDefaultOpen(sectionId);
  const [open, setOpen] = useState(() => {
    const stored = loadSectionState()[sectionId];
    return typeof stored === "boolean" ? stored : defaultOpen;
  });

  useEffect(() => {
    const stored = loadSectionState();
    const next = { ...stored, [sectionId]: open };
    saveSectionState(next);
  }, [sectionId, open]);

  const toggle = useCallback(() => setOpen((o) => !o), []);

  const contentId = `collapse-content-${sectionId}`;

  return (
    <div className={cn("rounded-lg border border-border bg-card overflow-hidden transition-colors duration-200 hover:border-primary/20", className)}>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={contentId}
        className="w-full px-3 py-2 border-b border-border bg-muted/30 flex items-center justify-between gap-2 text-left hover:bg-muted/50 transition-colors min-w-0"
      >
        <div className="flex items-center gap-1.5 min-w-0">
          {icon}
          <span className="font-mono text-xs text-muted-foreground tracking-wider truncate">
            {title}
          </span>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {headerRight}
          {open ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          )}
        </div>
      </button>
      {open && (
        <div id={contentId} role="region" className="min-w-0">
          {children}
        </div>
      )}
    </div>
  );
}
