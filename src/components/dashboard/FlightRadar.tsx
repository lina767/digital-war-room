import { Plane, Ship, ChevronDown, ChevronRight, Radar } from "lucide-react";
import { useState } from "react";

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

interface FlightRadarProps {
  sigint?: {
    aircraft?: Aircraft[];
    ships?: ShipData[];
    sigint_score?: number;
  };
}

const CATEGORY_LABELS: Record<string, string> = {
  surveillance: "Surveillance",
  tanker: "Tanker (refuel)",
  fighter: "Fighter/Bomber",
  transport: "Transport",
  military: "Military",
};

const CATEGORY_COLORS: Record<string, string> = {
  surveillance: "text-yellow-400",
  tanker: "text-blue-400",
  fighter: "text-red-400",
  transport: "text-emerald-400",
  military: "text-primary",
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

  const aircraft = (sigint?.aircraft ?? []).filter(
    (a): a is Aircraft => !!a && typeof a === "object" && !("error" in a),
  );
  const ships = (sigint?.ships ?? []).filter(
    (s): s is ShipData => !!s && typeof s === "object" && !("error" in s),
  );
  const acCount = aircraft.length;
  const shipCount = ships.length;
  const noData = acCount === 0 && shipCount === 0;

  const byCategory = groupBy(aircraft, (a) => a.category || "military");
  const byRegion = groupBy(ships, (s) => s.region || "Unknown");

  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="font-mono text-[10px] text-muted-foreground tracking-wider flex items-center gap-1.5">
          <Radar className="h-3 w-3" />
          SIGINT TRACKER
        </h3>
        {typeof sigint?.sigint_score === "number" && (
          <span className="font-mono text-[10px] text-muted-foreground">
            Score {sigint.sigint_score.toFixed(0)}
          </span>
        )}
      </div>

      {noData && (
        <p className="text-[10px] text-muted-foreground italic">No SIGINT data in current window.</p>
      )}

      {/* Aircraft summary */}
      {acCount > 0 && (
        <div className="space-y-1">
          <button
            type="button"
            onClick={() => setShowAircraft(!showAircraft)}
            className="flex items-center gap-1.5 w-full text-left"
          >
            {showAircraft ? <ChevronDown className="h-3 w-3 text-muted-foreground" /> : <ChevronRight className="h-3 w-3 text-muted-foreground" />}
            <Plane className="h-3.5 w-3.5 text-primary" />
            <span className="font-mono text-sm font-bold text-foreground">{acCount}</span>
            <span className="text-[10px] text-muted-foreground">military aircraft</span>
          </button>

          {/* Category breakdown (always visible) */}
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 pl-5">
            {Object.entries(byCategory)
              .sort(([, a], [, b]) => b.length - a.length)
              .map(([cat, items]) => (
                <span key={cat} className="text-[10px]">
                  <span className={CATEGORY_COLORS[cat] || "text-muted-foreground"}>{items.length}</span>
                  <span className="text-muted-foreground ml-0.5">{CATEGORY_LABELS[cat] || cat}</span>
                </span>
              ))}
          </div>

          {/* Detailed list */}
          {showAircraft && (
            <div className="pl-5 space-y-0.5 max-h-36 overflow-y-auto">
              {aircraft.slice(0, 20).map((ac, i) => (
                <div key={`${ac.flight}-${i}`} className="flex items-center justify-between gap-2 text-[10px]">
                  <span className="font-mono text-foreground/90 truncate">
                    {ac.flight || "—"}
                  </span>
                  <span className="text-muted-foreground truncate text-right">
                    {ac.type || ""}
                    {ac.category && <span className={`ml-1 ${CATEGORY_COLORS[ac.category] || ""}`}>({CATEGORY_LABELS[ac.category] || ac.category})</span>}
                  </span>
                </div>
              ))}
              {acCount > 20 && (
                <p className="text-[9px] text-muted-foreground">+{acCount - 20} more</p>
              )}
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
            className="flex items-center gap-1.5 w-full text-left"
          >
            {showShips ? <ChevronDown className="h-3 w-3 text-muted-foreground" /> : <ChevronRight className="h-3 w-3 text-muted-foreground" />}
            <Ship className="h-3.5 w-3.5 text-blue-400" />
            <span className="font-mono text-sm font-bold text-foreground">{shipCount}</span>
            <span className="text-[10px] text-muted-foreground">warships tracked</span>
          </button>

          {/* Region breakdown */}
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 pl-5">
            {Object.entries(byRegion)
              .sort(([, a], [, b]) => b.length - a.length)
              .map(([region, items]) => (
                <span key={region} className="text-[10px]">
                  <span className="text-blue-400">{items.length}</span>
                  <span className="text-muted-foreground ml-0.5">{region}</span>
                </span>
              ))}
          </div>

          {/* Detailed list */}
          {showShips && (
            <div className="pl-5 space-y-0.5 max-h-36 overflow-y-auto">
              {ships.slice(0, 20).map((s, i) => (
                <div key={`${s.name}-${i}`} className="flex items-center justify-between gap-2 text-[10px]">
                  <span className="font-mono text-foreground/90 truncate">
                    {s.name || "—"}
                  </span>
                  <span className="text-muted-foreground truncate text-right">
                    {s.region || ""}
                  </span>
                </div>
              ))}
              {shipCount > 20 && (
                <p className="text-[9px] text-muted-foreground">+{shipCount - 20} more</p>
              )}
            </div>
          )}
        </div>
      )}

      <div className="flex items-center justify-between pt-1 border-t border-border/40">
        <span className="text-[9px] text-muted-foreground">
          ADS-B (opendata.adsb.fi) · AIS (VesselFinder, Spire)
        </span>
      </div>
    </div>
  );
}
