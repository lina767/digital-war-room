/**
 * Client-side investigation "case" pins (localStorage). No server persistence in MVP.
 */

export interface InvestigationPin {
  id: string;
  createdAt: string;
  updatedAt: string;
  conflict: string;
  title: string;
  notes: string;
  refUrl?: string;
}

const KEY = "dwr-investigation-pins-v1";

function safeParse(raw: string | null): InvestigationPin[] {
  if (!raw) return [];
  try {
    const p = JSON.parse(raw) as unknown;
    if (!Array.isArray(p)) return [];
    return p.filter(
      (x): x is InvestigationPin =>
        typeof x === "object" &&
        x !== null &&
        typeof (x as InvestigationPin).id === "string" &&
        typeof (x as InvestigationPin).title === "string",
    );
  } catch {
    return [];
  }
}

export function loadPins(): InvestigationPin[] {
  if (typeof window === "undefined") return [];
  return safeParse(localStorage.getItem(KEY));
}

export function savePins(pins: InvestigationPin[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(pins));
  } catch {
    // quota
  }
}

export function addPin(pin: Omit<InvestigationPin, "id" | "createdAt" | "updatedAt">): InvestigationPin {
  const now = new Date().toISOString();
  const id = `pin-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  const full: InvestigationPin = {
    ...pin,
    id,
    createdAt: now,
    updatedAt: now,
  };
  const pins = loadPins();
  pins.unshift(full);
  savePins(pins);
  return full;
}

export function updatePin(id: string, patch: Partial<Pick<InvestigationPin, "title" | "notes" | "conflict" | "refUrl">>): boolean {
  const pins = loadPins();
  const i = pins.findIndex((p) => p.id === id);
  if (i < 0) return false;
  pins[i] = {
    ...pins[i],
    ...patch,
    updatedAt: new Date().toISOString(),
  };
  savePins(pins);
  return true;
}

export function deletePin(id: string): void {
  savePins(loadPins().filter((p) => p.id !== id));
}

export function exportPinsJson(): string {
  return JSON.stringify(loadPins(), null, 2);
}
