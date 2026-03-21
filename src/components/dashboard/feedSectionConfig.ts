/**
 * Intelligence Feed section and domain config for collapsible panels and domain grouping.
 * Section IDs are used for localStorage persistence (dwr-feed-sections, dwr-feed-domains).
 */

export const FEED_SECTIONS_STORAGE_KEY = "dwr-feed-sections";
/** Separate collapse prefs for small viewports (does not affect desktop `lg+`). */
export const FEED_SECTIONS_MOBILE_STORAGE_KEY = "dwr-feed-sections-mobile";
export const FEED_DOMAINS_STORAGE_KEY = "dwr-feed-domains";
export const FEED_VIEW_STORAGE_KEY = "dwr-feed-view";

/** Section IDs for the right panel (used for collapse persistence). */
export type FeedSectionId =
  | "briefing"
  | "signal-framework"
  | "predictive"
  | "compliance"
  | "chokepoint"
  | "global-impact"
  | "headlines"
  | "events-timeline"
  | "proximity"
  | "activity-connectivity";

/** Domain grouping: Security, Economic, Political, Information. */
export type FeedDomainId = "security" | "economic" | "political" | "information";

export interface FeedSectionConfig {
  id: FeedSectionId;
  defaultOpen: boolean;
  domain: FeedDomainId;
}

/** Panels open by default: Briefing, Signal Framework, Predictive, Compliance, ChokePoint. Rest collapsed. */
export const FEED_SECTION_CONFIG: Record<FeedSectionId, FeedSectionConfig> = {
  briefing: { id: "briefing", defaultOpen: true, domain: "information" },
  "signal-framework": { id: "signal-framework", defaultOpen: true, domain: "information" },
  predictive: { id: "predictive", defaultOpen: true, domain: "information" },
  compliance: { id: "compliance", defaultOpen: true, domain: "political" },
  chokepoint: { id: "chokepoint", defaultOpen: true, domain: "security" },
  "global-impact": { id: "global-impact", defaultOpen: false, domain: "economic" },
  headlines: { id: "headlines", defaultOpen: false, domain: "information" },
  "events-timeline": { id: "events-timeline", defaultOpen: false, domain: "information" },
  proximity: { id: "proximity", defaultOpen: false, domain: "security" },
  "activity-connectivity": { id: "activity-connectivity", defaultOpen: false, domain: "security" },
};

/** Domain labels and which section IDs belong to each. */
export const FEED_DOMAINS: Record<
  FeedDomainId,
  { label: string; sectionIds: FeedSectionId[]; defaultOpen: boolean }
> = {
  security: {
    label: "Security",
    sectionIds: ["chokepoint", "proximity", "activity-connectivity"],
    defaultOpen: true,
  },
  economic: {
    label: "Economic",
    sectionIds: ["global-impact"],
    defaultOpen: true,
  },
  political: {
    label: "Political",
    sectionIds: ["compliance"],
    defaultOpen: true,
  },
  information: {
    label: "Information",
    sectionIds: ["briefing", "signal-framework", "predictive", "headlines", "events-timeline"],
    defaultOpen: true,
  },
};

/** Which panel (section) maps to which domain. Used when rendering flat list with domain headers. */
export function getSectionDomain(sectionId: FeedSectionId): FeedDomainId {
  return FEED_SECTION_CONFIG[sectionId].domain;
}

export function getSectionDefaultOpen(sectionId: FeedSectionId): boolean {
  return FEED_SECTION_CONFIG[sectionId].defaultOpen;
}

/**
 * Mobile feed defaults: only briefing expanded so the stack stays scannable; other sections start collapsed.
 * Persisted separately from desktop (`FEED_SECTIONS_MOBILE_STORAGE_KEY`).
 */
export function getSectionDefaultOpenMobile(sectionId: FeedSectionId): boolean {
  return sectionId === "briefing";
}
