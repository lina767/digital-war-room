export const INTEL_STORY_VERSION = 1 as const;

/** Trimmed dashboard snapshot for PDF/JSON/share (no full agent payloads). */
export interface IntelStorySnapshot {
  v: typeof INTEL_STORY_VERSION;
  conflict: string;
  exportedAt: string;
  threat_level?: string;
  escalation_score?: number;
  summary?: string;
  narrative_story?: string;
  key_findings?: string[];
  /** Optional short provenance */
  analysis_run_id?: string;
}
