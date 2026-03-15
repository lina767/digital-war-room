import { Plane, Ship, ChevronDown, ChevronRight, Radar, AlertTriangle, Shield } from "lucide-react";
import { useState } from "react";
import { IntelPanel } from "@/components/dashboard/IntelPanel";

interface Aircraft {
  flight?: string;
  type?: string;
  category?: string;
  lat?: number;
  lon?: number;
  source?: string;
}

interface ShipData {
  name?: string;
  type?: string;
  lat?: number;
  lon?: number;
  region?: string;
  source?: string;
}

interface TargetTrack {
  [key: string]: Record<string, unknown> | undefined;
}

interface FlightRadarProps {
  sigint?: {
    aircraft?: Aircraft[];
    ships?: ShipData[];
    sigint_score?: number;
    target_tracks?: TargetTrack;
    alerts?: string[];
  };
}

const CATEGORY_LABELS: Record<string, string> = {
  doomsday: "Doomsday / Nuclear C3",
  surveillance: "ISR / AWACS",
  tanker: "Tanker (Refuel)",
  fighter: "Fighter / Bomber",
  transport: "Transport",
  iranian_gov: "Iranian Gov / IRGC",
  military: "Military",
};

const CATEGORY_COLORS: Record<string, string> = {
  doomsday: "text-red-500",
  surveillance: "text-yellow-400",
  tanker: "text-blue-400",
  fighter: "text-red-400",
  transport: "text-emerald-400",
  iranian_gov: "text-orange-400",
  military: "text-primary",
};

const CATEGORY_BG: Record<string, string> = {
  doomsday: "bg-red-500/10 border-red-500/30",
  iranian_gov: "bg-orange-400/10 border-orange-400/30",
};

const CATEGORY_PRIORITY: Record<string, number> = {
  doomsday: 0,
  iranian_gov: 1,
  fighter: 2,
  surveillance: 3,
  tanker: 4,
  transport: 5,
  military: 6,
};

function groupBy<T>(arr: T[], key: (item: T) => string): Record<string, T[]> {
  const map: Record<string, T[]> = {};
  for (const item of arr) {
    const k = key(item);
    (map[k] ??= []).push(item);
  }
  return map;
}

export function FlightRadar({ sigint }: FlightRadarProps) {
  const [showAircraft, setShowAircraft] = useState(false);
  const [showShips, setShowShips] = useState(false);
  const [showTargets, setShowTargets] = useState(false);

  const aircraft = (sigint?.aircraft ?? []).filter(
    (a): a is Aircraft => !!a && typeof a === "object" && !("error" in a),
  );
  const ships = (sigint?.ships ?? []).filter(
    (s): s is ShipData => !!s && typeof s === "object" && !("error" in s),
  );
  const targetTracks = sigint?.target_tracks ?? {};
  const targetEntries = Object.entries(targetTracks).filter(
    ([, v]) => v && typeof v === "object" && !("error" in v),
  );
  const alerts = sigint?.alerts ?? [];

  const acCount = aircraft.length;
  const shipCount = ships.length;
  const noData = acCount === 0 && shipCount === 0 && targetEntries.length === 0;

  const byCategory = groupBy(aircraft, (a) => a.category || "military");
  const byRegion = groupBy(ships, (s) => s.region || "Unknown");

  const hasDoomsday = (byCategory["doomsday"]?.length ?? 0) > 0;
  const hasIranianGov = (byCategory["iranian_gov"]?.length ?? 0) > 0;

  const sortedCategories = Object.entries(byCategory).sort(
    ([a], [b]) => (CATEGORY_PRIORITY[a] ?? 99) - (CATEGORY_PRIORITY[b] ?? 99),
  );

  return (
    <IntelPanel
      title="SIGINT TRACKER"
      icon={<Radar className="h-3.5 w-3.5 text-muted-foreground" />}
      headerRight={
        typeof sigint?.sigint_score === "number" ? (
          <span className="font-mono text-[11px] text-muted-foreground">
            Score {sigint.sigint_score.toFixed(0)}
          </span>
        ) : undefined
      }
    >
      {/* High-priority banner: doomsday planes */}
      {hasDoomsday && (
        <div className="flex items-center gap-2 px-2 py-1.5 rounded border bg-red-500/10 border-red-500/30 animate-pulse">
          <AlertTriangle className="h-3.5 w-3.5 text-red-500 shrink-0" />
          <span className="text-[11px] font-bold text-red-400">
            DOOMSDAY / NUCLEAR C3 AIRCRAFT DETECTED — {byCategory["doomsday"]!.map((a) => a.flight || "?").join(", ")}
          </span>
        </div>
      )}

      {/* High-priority banner: Iranian gov/IRGC */}
      {hasIranianGov && (
        <div className="flex items-center gap-2 px-2 py-1.5 rounded border bg-orange-400/10 border-orange-400/30">
          <Shield className="h-3.5 w-3.5 text-orange-400 shrink-0" />
          <span className="text-[11px] font-bold text-orange-300">
            IRANIAN GOV / IRGC AIRCRAFT — {byCategory["iranian_gov"]!.map((a) => a.flight || "?").join(", ")}
          </span>
        </div>
      )}

      {noData && (
        <p className="text-[11px] text-muted-foreground italic">No SIGINT data in current window.</p>
      )}

      {/* Aircraft summary */}
      {acCount > 0 && (
        <div className="space-y-1">
          <button
            type="button"
            onClick={() => setShowAircraft(!showAircraft)}
            className="flex items-center gap-1.5 w-full text-left rounded focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50"
          >
            {showAircraft ? <ChevronDown className="h-3 w-3 text-muted-foreground" /> : <ChevronRight className="h-3 w-3 text-muted-foreground" />}
            <Plane className="h-3.5 w-3.5 text-primary" />
            <span className="font-mono text-sm font-bold text-foreground">{acCount}</span>
            <span className="text-[11px] text-muted-foreground">military aircraft</span>
          </button>

          {/* Category breakdown (always visible, sorted by priority) */}
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 pl-5">
            {sortedCategories.map(([cat, items]) => (
              <span
                key={cat}
                className={`text-[11px] ${CATEGORY_BG[cat] ? `px-1 rounded border ${CATEGORY_BG[cat]}` : ""}`}
              >
                <span className={CATEGORY_COLORS[cat] || "text-muted-foreground"}>{items.length}</span>
                <span className="text-muted-foreground ml-0.5">{CATEGORY_LABELS[cat] || cat}</span>
              </span>
            ))}
          </div>

          {/* Detailed list */}
          {showAircraft && (
            <div className="pl-5 space-y-0.5 max-h-48 overflow-y-auto">
              {aircraft
                .sort((a, b) => (CATEGORY_PRIORITY[a.category || "military"] ?? 99) - (CATEGORY_PRIORITY[b.category || "military"] ?? 99))
                .slice(0, 30)
                .map((ac, i) => (
                  <div
                    key={`${ac.flight}-${i}`}
                    className={`flex items-center justify-between gap-2 text-[11px] ${
                      ac.category === "doomsday" ? "bg-red-500/5 rounded px-1" :
                      ac.category === "iranian_gov" ? "bg-orange-400/5 rounded px-1" : ""
                    }`}
                  >
                    <span className="font-mono text-foreground/90 truncate">
                      {ac.flight || "—"}
                    </span>
                    <span className="text-muted-foreground truncate text-right">
                      {ac.type || ""}
                      {ac.category && (
                        <span className={`ml-1 ${CATEGORY_COLORS[ac.category] || ""}`}>
                          ({CATEGORY_LABELS[ac.category] || ac.category})
                        </span>
                      )}
                    </span>
                  </div>
                ))}
              {acCount > 30 && (
                <p className="text-[11px] text-muted-foreground">+{acCount - 30} more</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Target aircraft tracking */}
      {targetEntries.length > 0 && (
        <div className="space-y-1">
          <button
            type="button"
            onClick={() => setShowTargets(!showTargets)}
            className="flex items-center gap-1.5 w-full text-left rounded focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50"
          >
            {showTargets ? <ChevronDown className="h-3 w-3 text-muted-foreground" /> : <ChevronRight className="h-3 w-3 text-muted-foreground" />}
            <Shield className="h-3.5 w-3.5 text-amber-400" />
            <span className="font-mono text-sm font-bold text-foreground">{targetEntries.length}</span>
            <span className="text-[11px] text-muted-foreground">tracked targets</span>
          </button>
          {showTargets && (
            <div className="pl-5 space-y-1 max-h-36 overflow-y-auto">
              {targetEntries.map(([name, data]) => {
                const d = data as Record<string, unknown>;
                const found = !!(d?.adsbx || d?.adsbexchange_rapidapi || d?.opensky || d?.fallback_sigint);
                return (
                  <div key={name} className="flex items-center justify-between text-[11px]">
                    <span className="font-mono text-foreground/90">{name}</span>
                    <span className={found ? "text-green-400" : "text-muted-foreground"}>
                      {found ? "ACTIVE" : "no signal"}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Ships summary */}
      {shipCount > 0 && (
        <div className="space-y-1">
          <button
            type="button"
            onClick={() => setShowShips(!showShips)}
            className="flex items-center gap-1.5 w-full text-left rounded focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50"
          >
            {showShips ? <ChevronDown className="h-3 w-3 text-muted-foreground" /> : <ChevronRight className="h-3 w-3 text-muted-foreground" />}
            <Ship className="h-3.5 w-3.5 text-blue-400" />
            <span className="font-mono text-sm font-bold text-foreground">{shipCount}</span>
            <span className="text-[11px] text-muted-foreground">warships tracked</span>
          </button>

          <div className="flex flex-wrap gap-x-3 gap-y-0.5 pl-5">
            {Object.entries(byRegion)
              .sort(([, a], [, b]) => b.length - a.length)
              .map(([region, items]) => (
                <span key={region} className="text-[11px]">
                  <span className="text-blue-400">{items.length}</span>
                  <span className="text-muted-foreground ml-0.5">{region}</span>
                </span>
              ))}
          </div>

          {showShips && (
            <div className="pl-5 space-y-0.5 max-h-36 overflow-y-auto">
              {ships.slice(0, 20).map((s, i) => (
                <div key={`${s.name}-${i}`} className="flex items-center justify-between gap-2 text-[11px]">
                  <span className="font-mono text-foreground/90 truncate">
                    {s.name || "—"}
                  </span>
                  <span className="text-muted-foreground truncate text-right">
                    {s.region || ""}
                  </span>
                </div>
              ))}
              {shipCount > 20 && (
                <p className="text-[11px] text-muted-foreground">+{shipCount - 20} more</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Alerts from backend */}
      {alerts.length > 0 && (
        <div className="space-y-0.5 pt-1 border-t border-border/40">
          {alerts.slice(0, 5).map((alert, i) => (
            <p key={i} className={`text-[11px] ${
              alert.includes("DOOMSDAY") || alert.includes("⚠") ? "text-red-400 font-medium" :
              alert.includes("🇮🇷") || alert.includes("Iranian") ? "text-orange-400 font-medium" :
              "text-muted-foreground"
            }`}>
              {alert}
            </p>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between pt-1 border-t border-border/40">
        <span className="text-[11px] text-muted-foreground">
          ADS-B (opendata.adsb.fi, ADSBexchange) · AIS (VesselFinder)
        </span>
      </div>
    </IntelPanel>
  );
}
