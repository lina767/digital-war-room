import type { ThreatLevel } from "@/features/daily-briefing/types/briefing.types";

export function threatLevelColor(level: ThreatLevel): string {
  switch (level) {
    case "CRITICAL":
      return "var(--threat-critical)";
    case "HIGH":
      return "var(--threat-high)";
    case "ELEVATED":
      return "var(--threat-elevated)";
    case "LOW":
      return "var(--threat-low)";
    case "MINIMAL":
    default:
      return "var(--threat-minimal)";
  }
}

export function threatLevelClass(level: ThreatLevel): string {
  switch (level) {
    case "CRITICAL":
      return "db-threat-critical";
    case "HIGH":
      return "db-threat-high";
    case "ELEVATED":
      return "db-threat-elevated";
    case "LOW":
      return "db-threat-low";
    case "MINIMAL":
    default:
      return "db-threat-minimal";
  }
}
