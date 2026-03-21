import { useState, useEffect, useCallback } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FeedSectionId } from "./feedSectionConfig";
import {
  FEED_SECTIONS_STORAGE_KEY,
  FEED_SECTIONS_MOBILE_STORAGE_KEY,
  getSectionDefaultOpen,
  getSectionDefaultOpenMobile,
} from "./feedSectionConfig";
import { useIsMobileLayout } from "@/hooks/useMediaQuery";

interface CollapsiblePanelProps {
  sectionId: FeedSectionId;
  title: string;
  /** Optional right-side content in the header (e.g. "2 min ago"). */
  headerRight?: React.ReactNode;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

function loadSectionState(isMobile: boolean): Record<string, boolean> {
  const key = isMobile ? FEED_SECTIONS_MOBILE_STORAGE_KEY : FEED_SECTIONS_STORAGE_KEY;
  try {
    const raw = localStorage.getItem(key);
    if (raw) {
      const parsed = JSON.parse(raw) as Record<string, boolean>;
      if (typeof parsed === "object" && parsed !== null) return parsed;
    }
  } catch {
    // ignore
  }
  return {};
}

function saveSectionState(isMobile: boolean, state: Record<string, boolean>) {
  const key = isMobile ? FEED_SECTIONS_MOBILE_STORAGE_KEY : FEED_SECTIONS_STORAGE_KEY;
  try {
    localStorage.setItem(key, JSON.stringify(state));
  } catch {
    // ignore
  }
}

function initialOpenForSection(sectionId: FeedSectionId): boolean {
  if (typeof window === "undefined") {
    return getSectionDefaultOpen(sectionId);
  }
  const mq = window.matchMedia("(max-width: 1023px)").matches;
  const stored = loadSectionState(mq)[sectionId];
  if (typeof stored === "boolean") return stored;
  return mq ? getSectionDefaultOpenMobile(sectionId) : getSectionDefaultOpen(sectionId);
}

export function CollapsiblePanel({
  sectionId,
  title,
  headerRight,
  icon,
  children,
  className,
}: CollapsiblePanelProps) {
  const isMobile = useIsMobileLayout();
  const [open, setOpen] = useState(() => initialOpenForSection(sectionId));

  useEffect(() => {
    const stored = loadSectionState(isMobile)[sectionId];
    if (typeof stored === "boolean") setOpen(stored);
    else setOpen(isMobile ? getSectionDefaultOpenMobile(sectionId) : getSectionDefaultOpen(sectionId));
  }, [isMobile, sectionId]);

  useEffect(() => {
    const stored = loadSectionState(isMobile);
    const next = { ...stored, [sectionId]: open };
    saveSectionState(isMobile, next);
  }, [sectionId, open, isMobile]);

  const toggle = useCallback(() => setOpen((o) => !o), []);

  const contentId = `collapse-content-${sectionId}`;

  return (
    <div className={cn("rounded-lg border border-border bg-card overflow-hidden transition-colors duration-200 hover:border-primary/20", className)}>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={contentId}
        className="w-full px-3 py-2 max-lg:min-h-11 max-lg:py-3 border-b border-border bg-muted/30 flex items-center justify-between gap-2 text-left hover:bg-muted/50 transition-colors min-w-0 touch-manipulation"
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
