import { useState } from "react";
import { IntelPanel, IntelPanelSkeleton } from "@/components/dashboard/IntelPanel";
import {
  Shield,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Wifi,
  Bug,
} from "lucide-react";
import { useGreynoiseThreats } from "@/hooks/useGreynoiseThreats";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import type { GreynoiseEmergingThreat, GreynoiseTrendPoint } from "@/lib/api";

interface GreyNoisePanelProps {
  conflict?: string;
}

const PRIORITY_COLORS: Record<string, string> = {
  high: "text-red-400",
  medium: "text-yellow-400",
  low: "text-muted-foreground",
};

const PRIORITY_BG: Record<string, string> = {
  high: "bg-red-500/10 border-red-500/30",
  medium: "bg-yellow-500/10 border-yellow-500/30",
  low: "bg-muted/30 border-border",
};

const CATEGORY_LABELS: Record<string, string> = {
  critical_infra: "ICS/SCADA",
  vpn_exploit: "VPN Exploit",
  apt_tooling: "APT Tooling",
  router_exploit: "Router Exploit",
  generic_scan: "Generic Scan",
  wiper_related: "Wiper/Destructive",
  ddos_botnet: "DDoS/Botnet",
  uncategorized: "Other",
};

function TrendIcon({ trend }: { trend: string }) {
  if (trend === "rising")
    return <ArrowUpRight className="h-3 w-3 text-red-400" />;
  if (trend === "falling")
    return <ArrowDownRight className="h-3 w-3 text-green-400" />;
  return <Minus className="h-3 w-3 text-muted-foreground" />;
}

function ScoreSparkline({ data }: { data: GreynoiseTrendPoint[] }) {
  if (data.length < 2) return null;
  return (
    <div className="w-20 h-6">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="gnSparkGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
              <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="greynoise_score"
            stroke="hsl(var(--primary))"
            strokeWidth={1.5}
            fill="url(#gnSparkGrad)"
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function ThreatRow({ threat }: { threat: GreynoiseEmergingThreat }) {
  const cat = CATEGORY_LABELS[threat.category] || threat.category;
  return (
    <div className="flex items-center justify-between gap-2 text-[11px]">
      <div className="flex items-center gap-1.5 truncate min-w-0">
        <span
          className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${
            threat.priority === "high"
              ? "bg-red-400"
              : threat.priority === "medium"
                ? "bg-yellow-400"
                : "bg-muted-foreground/50"
          }`}
        />
        <span className="font-mono text-foreground/90 truncate">{threat.tag}</span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-muted-foreground">{cat}</span>
        <span
          className={`px-1 rounded text-[11px] border ${
            threat.direction === "inbound"
              ? "text-red-400 border-red-500/30 bg-red-500/10"
              : "text-blue-400 border-blue-500/30 bg-blue-500/10"
          }`}
        >
          {threat.direction === "inbound" ? "IN" : "OUT"}
        </span>
        {threat.cvss_score != null && (
          <span
            className={`font-mono ${
              threat.cvss_score >= 9
                ? "text-red-400"
                : threat.cvss_score >= 7
                  ? "text-yellow-400"
                  : "text-muted-foreground"
            }`}
          >
            {threat.cvss_score.toFixed(1)}
          </span>
        )}
        <span className="text-muted-foreground font-mono w-12 text-right">
          {threat.scan_volume.toLocaleString()}
        </span>
      </div>
    </div>
  );
}

export function GreyNoisePanel({ conflict = "Iran" }: GreyNoisePanelProps) {
  const { data, trendData, isLoading, error } = useGreynoiseThreats(conflict);
  const [showThreats, setShowThreats] = useState(false);

  if (isLoading && !data) {
    return <IntelPanelSkeleton lines={2} />;
  }

  if (error && !data) {
    return (
      <IntelPanel title="EMERGING CYBER THREATS" icon={<Shield className="h-3 w-3 text-muted-foreground" />}>
        <p className="text-[11px] text-muted-foreground italic">{error}</p>
      </IntelPanel>
    );
  }

  if (!data) return null;

  const threats = data.emerging_threats ?? [];
  const highThreats = threats.filter((t) => t.priority === "high");
  const hasHighInbound = threats.some(
    (t) => t.direction === "inbound" && t.priority === "high",
  );

  const byCategory: Record<string, number> = {};
  for (const t of threats) {
    const cat = t.category || "uncategorized";
    byCategory[cat] = (byCategory[cat] ?? 0) + 1;
  }

  return (
    <IntelPanel
      title="EMERGING CYBER THREATS"
      icon={<Shield className="h-3 w-3 text-muted-foreground" />}
      headerRight={
        <div className="flex items-center gap-2">
          <ScoreSparkline data={trendData} />
          <div className="flex items-center gap-1">
            <TrendIcon trend={data.trend} />
            <span className="font-mono text-[11px] text-muted-foreground">
              {data.greynoise_score.toFixed(0)}
            </span>
          </div>
        </div>
      }
    >
      {/* High-priority inbound banner */}
      {hasHighInbound && (
        <div className="flex items-center gap-2 px-2 py-1.5 rounded border bg-red-500/10 border-red-500/30">
          <AlertTriangle className="h-3.5 w-3.5 text-red-500 shrink-0" />
          <span className="text-[11px] font-bold text-red-400">
            HIGH-PRIORITY INBOUND SCANS —{" "}
            {threats
              .filter((t) => t.direction === "inbound" && t.priority === "high")
              .map((t) => t.tag)
              .slice(0, 3)
              .join(", ")}
          </span>
        </div>
      )}

      {/* Summary */}
      {data.summary && (
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          {data.summary}
        </p>
      )}

      {/* Counts */}
      <div className="flex items-center gap-4 text-[11px]">
        <span className="flex items-center gap-1">
          <Wifi className="h-3 w-3 text-blue-400" />
          <span className="font-mono font-bold text-foreground">
            {data.outbound_count.toLocaleString()}
          </span>
          <span className="text-muted-foreground">outbound</span>
        </span>
        <span className="flex items-center gap-1">
          <Bug className="h-3 w-3 text-red-400" />
          <span className="font-mono font-bold text-foreground">
            {data.inbound_count.toLocaleString()}
          </span>
          <span className="text-muted-foreground">inbound</span>
        </span>
      </div>

      {/* Category breakdown */}
      {Object.keys(byCategory).length > 0 && (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
          {Object.entries(byCategory)
            .sort(([, a], [, b]) => b - a)
            .map(([cat, count]) => (
              <span key={cat} className="text-[11px]">
                <span className="text-primary">{count}</span>
                <span className="text-muted-foreground ml-0.5">
                  {CATEGORY_LABELS[cat] || cat}
                </span>
              </span>
            ))}
        </div>
      )}

      {/* Expandable threat list */}
      {threats.length > 0 && (
        <div className="space-y-1">
          <button
            type="button"
            onClick={() => setShowThreats(!showThreats)}
            className="flex items-center gap-1.5 w-full text-left rounded focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50"
          >
            {showThreats ? (
              <ChevronDown className="h-3 w-3 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-3 w-3 text-muted-foreground" />
            )}
            <span className="font-mono text-sm font-bold text-foreground">
              {threats.length}
            </span>
            <span className="text-[11px] text-muted-foreground">
              emerging threat{threats.length !== 1 ? "s" : ""}
            </span>
            {highThreats.length > 0 && (
              <span className="text-[11px] text-red-400 font-medium">
                ({highThreats.length} high)
              </span>
            )}
          </button>

          {showThreats && (
            <div className="pl-5 space-y-0.5 max-h-48 overflow-y-auto">
              {threats
                .sort((a, b) => b.weight * b.scan_volume - a.weight * a.scan_volume)
                .slice(0, 25)
                .map((t, i) => (
                  <ThreatRow key={`${t.tag}-${t.direction}-${i}`} threat={t} />
                ))}
              {threats.length > 25 && (
                <p className="text-[11px] text-muted-foreground">
                  +{threats.length - 25} more
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Alerts */}
      {data.alerts.length > 0 && (
        <div className="space-y-0.5 pt-1 border-t border-border/40">
          {data.alerts.slice(0, 5).map((alert, i) => (
            <p
              key={i}
              className={`text-[11px] ${
                alert.includes("HIGH-PRIORITY") || alert.includes("Critical CVE")
                  ? "text-red-400 font-medium"
                  : alert.includes("ICS/SCADA")
                    ? "text-orange-400 font-medium"
                    : "text-muted-foreground"
              }`}
            >
              {alert}
            </p>
          ))}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-1 border-t border-border/40">
        <span className="text-[11px] text-muted-foreground">
          GreyNoise GNQL Stats · CVE Lookup · {data.fetched_at ? new Date(data.fetched_at).toLocaleTimeString() : ""}
        </span>
      </div>
    </IntelPanel>
  );
}
