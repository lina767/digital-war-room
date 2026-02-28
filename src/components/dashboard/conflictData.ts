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

export const conflicts: ConflictMarker[] = [
  { id: "us-iran", label: "US–Iran", coordinates: [53, 32], severity: "high" },
  { id: "ukraine", label: "Ukraine", coordinates: [31, 49], severity: "high" },
  { id: "sudan", label: "Sudan", coordinates: [30, 15], severity: "high" },
  { id: "myanmar", label: "Myanmar", coordinates: [96, 20], severity: "medium" },
  { id: "taiwan-strait", label: "Taiwan Strait", coordinates: [120, 24], severity: "medium" },
  { id: "sahel", label: "Sahel Region", coordinates: [2, 15], severity: "medium" },
  { id: "ethiopia", label: "Ethiopia", coordinates: [40, 9], severity: "low" },
  { id: "syria", label: "Syria", coordinates: [38, 35], severity: "medium" },
  { id: "yemen", label: "Yemen", coordinates: [48, 15], severity: "high" },
  { id: "drc", label: "DRC", coordinates: [24, -3], severity: "low" },
  { id: "korea", label: "Korean Peninsula", coordinates: [127, 38], severity: "low" },
  { id: "israel-palestine", label: "Israel–Palestine", coordinates: [35, 31.5], severity: "high" },
];

export const conflictLinks: ConflictLink[] = [
  { id: "link-1", from: "us-iran", to: "israel-palestine", label: "Proxy conflict" },
  { id: "link-2", from: "israel-palestine", to: "syria", label: "Border tensions" },
  { id: "link-3", from: "syria", to: "us-iran", label: "Iranian influence" },
  { id: "link-4", from: "us-iran", to: "yemen", label: "Houthi support" },
  { id: "link-5", from: "yemen", to: "israel-palestine", label: "Houthi strikes" },
  { id: "link-6", from: "sudan", to: "ethiopia", label: "Border dispute" },
  { id: "link-7", from: "ethiopia", to: "drc", label: "Regional instability" },
  { id: "link-8", from: "sahel", to: "sudan", label: "Arms flow" },
  { id: "link-9", from: "taiwan-strait", to: "korea", label: "US alliance" },
  { id: "link-10", from: "myanmar", to: "taiwan-strait", label: "Regional pressure" },
];

export const severityColor: Record<string, string> = {
  high: "hsl(var(--threat))",
  medium: "hsl(var(--warning))",
  low: "hsl(var(--primary))",
};
