export interface ConflictMarker {
  id: string;
  label: string;
  coordinates: [number, number];
  severity: "high" | "medium" | "low";
}

export interface ConflictLink {
  id: string;
  from: string;
  to: string;
  label: string;
}

/** For dropdown: id (storage), label (display), apiValue (backend analyze). Middle East focus only. */
export const CONFLICT_OPTIONS = [
  { id: "middle-east", label: "Middle East", apiValue: "Middle East" },
  { id: "red-sea", label: "Red Sea (Houthis)", apiValue: "Red Sea" },
  { id: "iran", label: "Iran", apiValue: "Iran" },
  { id: "lebanon", label: "Lebanon", apiValue: "Lebanon" },
] as const;

/** World overview map: only these markers are interactive (ME theater). */
export const conflicts: ConflictMarker[] = [
  { id: "middle-east", label: "Middle East", coordinates: [44, 31], severity: "high" },
  { id: "red-sea", label: "Red Sea", coordinates: [43, 12], severity: "high" },
  { id: "iran", label: "Iran", coordinates: [53, 32], severity: "high" },
  { id: "lebanon", label: "Lebanon", coordinates: [35.9, 33.9], severity: "high" },
];

export const conflictLinks: ConflictLink[] = [
  { id: "me-iran", from: "middle-east", to: "iran", label: "Regional arc" },
  { id: "me-red-sea", from: "middle-east", to: "red-sea", label: "Maritime flank" },
  { id: "me-lebanon", from: "middle-east", to: "lebanon", label: "Levant" },
  { id: "red-sea-iran", from: "red-sea", to: "iran", label: "Maritime pressure" },
  { id: "iran-lebanon", from: "iran", to: "lebanon", label: "Axis / proxy" },
];

export const severityColor: Record<string, string> = {
  high: "hsl(var(--threat))",
  medium: "hsl(var(--warning))",
  low: "hsl(var(--primary))",
};
