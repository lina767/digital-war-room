import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { Anchor, Droplets, Wheat, AlertTriangle, Shield } from "lucide-react";

interface ChokePointPanelProps {
  data: ConflictData | null;
}

const STATUS_COLORS: Record<string, string> = {
  OPEN: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  RESTRICTED: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  DISRUPTED: "bg-red-500/20 text-red-400 border-red-500/30",
};

const DQ_LABELS: Record<string, string> = {
  live_ais: "live",
  estimated: "est.",
  baseline_only: "baseline",
};

function riskColor(risk: number): string {
  if (risk >= 70) return "text-red-400";
  if (risk >= 40) return "text-amber-400";
  return "text-emerald-400";
}

function riskRingColor(risk: number): string {
  if (risk >= 70) return "stroke-red-400";
  if (risk >= 40) return "stroke-amber-400";
  return "stroke-emerald-400";
}

function RiskGauge({ value }: { value: number }) {
  const circumference = 2 * Math.PI * 40;
  const offset = circumference - (Math.min(value, 100) / 100) * circumference;
  return (
    <div className="relative w-24 h-24 mx-auto">
      <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
        <circle cx="50" cy="50" r="40" fill="none" strokeWidth="6"
          className="stroke-muted/30" />
        <circle cx="50" cy="50" r="40" fill="none" strokeWidth="6"
          className={riskRingColor(value)}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round" />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-2xl font-bold font-mono ${riskColor(value)}`}>
          {Math.round(value)}
        </span>
        <span className="text-[9px] text-muted-foreground uppercase tracking-wider">risk</span>
      </div>
    </div>
  );
}

function CommodityRow({ symbol, price, change }: { symbol: string; price?: string; change?: string }) {
  if (!price) return null;
  const isNeg = change?.startsWith("-");
  const changeColor = isNeg ? "text-red-400" : change?.startsWith("+") ? "text-emerald-400" : "text-muted-foreground";
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted-foreground font-mono">{symbol}</span>
      <span className="font-mono text-foreground">{price}</span>
      <span className={`font-mono ${changeColor}`}>{change || "0%"}</span>
    </div>
  );
}

export function ChokePointPanel({ data }: ChokePointPanelProps) {
  const cpData = data?.chokepoint;
  const chokepoints = cpData?.chokepoints ?? [];
  const score = cpData?.chokepoint_score ?? 0;

  const energy = data?.energy;
  const oilCommodities = energy?.commodities ?? [];
  const foodCommodities = energy?.food_commodities ?? [];
  const faoFpi = energy?.fao_fpi;
  const foodRisk = energy?.food_security_risk ?? 0;

  if (chokepoints.length === 0 && oilCommodities.length === 0 && foodCommodities.length === 0) {
    return null;
  }

  const maxRisk = chokepoints.length > 0
    ? Math.max(...chokepoints.map((c) => c.disruption_risk))
    : score;

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 border-b border-border bg-muted/30 flex items-center gap-1.5">
        <Anchor className="h-3.5 w-3.5 text-muted-foreground" />
        <h3 className="font-mono text-xs text-muted-foreground tracking-wider">CHOKEPOINT MONITOR</h3>
      </div>

      <div className="p-3 space-y-3">
        {/* Status badges row */}
        {chokepoints.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {chokepoints.map((cp) => (
              <div
                key={cp.name}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono border ${STATUS_COLORS[cp.status] || STATUS_COLORS.OPEN}`}
              >
                <span>{cp.name.replace("Strait of ", "").replace(" Canal", "")}</span>
                <span className="font-bold">{cp.status}</span>
                <span className="text-muted-foreground ml-0.5">
                  [{DQ_LABELS[cp.data_quality] || cp.data_quality}]
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Hero risk gauge */}
        <RiskGauge value={maxRisk} />

        {/* Two-column layout: Oil / Food */}
        <div className="grid grid-cols-2 gap-3">
          {/* Left: Oil / Energy */}
          <div className="space-y-2">
            <div className="flex items-center gap-1 mb-1">
              <Droplets className="h-3 w-3 text-blue-400" />
              <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">Oil / Energy</span>
            </div>
            {oilCommodities.map((c) => (
              <CommodityRow
                key={c.symbol}
                symbol={c.symbol ?? ""}
                price={c.price}
                change={c.change_pct}
              />
            ))}
            {chokepoints.length > 0 && (
              <div className="pt-1 space-y-1">
                {chokepoints.slice(0, 2).map((cp) => (
                  <div key={cp.name} className="flex justify-between text-[10px]">
                    <span className="text-muted-foreground truncate">{cp.name.split(" ").pop()}</span>
                    <span className="font-mono text-foreground">~{cp.oil_flow_estimate_mbd} mbd</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right: Food / Commodities */}
          <div className="space-y-2">
            <div className="flex items-center gap-1 mb-1">
              <Wheat className="h-3 w-3 text-amber-400" />
              <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">Food / Grain</span>
            </div>
            {foodCommodities.map((c) => (
              <CommodityRow
                key={c.symbol}
                symbol={c.symbol ?? ""}
                price={c.price}
                change={c.change_pct}
              />
            ))}
            {faoFpi?.index != null && (
              <div className="flex justify-between text-[10px] pt-1">
                <span className="text-muted-foreground">FAO FPI</span>
                <span className="font-mono text-foreground">
                  {faoFpi.index.toFixed(1)}
                  {faoFpi.yoy_change_pct != null && (
                    <span className={faoFpi.yoy_change_pct > 5 ? "text-red-400" : "text-muted-foreground"}>
                      {" "}({faoFpi.yoy_change_pct > 0 ? "+" : ""}{faoFpi.yoy_change_pct.toFixed(1)}% YoY)
                    </span>
                  )}
                </span>
              </div>
            )}
            {foodRisk > 0 && (
              <div className="flex justify-between text-[10px] pt-0.5">
                <span className="text-muted-foreground">Food Risk</span>
                <span className={`font-mono ${foodRisk >= 60 ? "text-red-400" : foodRisk >= 40 ? "text-amber-400" : "text-emerald-400"}`}>
                  {foodRisk.toFixed(0)}/100
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Footer: AIS anomalies + military vessels */}
        {chokepoints.length > 0 && (
          <div className="flex items-center gap-3 pt-1 border-t border-border/50 text-[10px] text-muted-foreground">
            {chokepoints.some((cp) => cp.ais_anomalies > 0) && (
              <div className="flex items-center gap-1">
                <AlertTriangle className="h-2.5 w-2.5 text-amber-400" />
                <span>
                  {chokepoints.reduce((s, cp) => s + cp.ais_anomalies, 0)} AIS anomalies
                </span>
              </div>
            )}
            {chokepoints.some((cp) => cp.military_vessels > 0) && (
              <div className="flex items-center gap-1">
                <Shield className="h-2.5 w-2.5 text-blue-400" />
                <span>
                  {chokepoints.reduce((s, cp) => s + cp.military_vessels, 0)} military vessels
                </span>
              </div>
            )}
            {chokepoints.some((cp) => cp.tanker_count > 0) && (
              <div className="flex items-center gap-1">
                <Anchor className="h-2.5 w-2.5" />
                <span>
                  {chokepoints.reduce((s, cp) => s + cp.tanker_count, 0)} tankers
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
