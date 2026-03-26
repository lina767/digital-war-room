import { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  getAgentsStatus,
  getAgentsHealth,
  getAgentsHistory,
  getAgentsMonitoring,
  getAgentsOpsStatus,
  getAnalyzeStatus,
  triggerRefreshAnalysis,
  postGoogleTrendSnapshot,
  type AgentsHealthResponse,
  type AgentsMonitoringResponse,
  type AgentsOpsAgentRow,
  type AgentsOpsStatusResponse,
  type AnalysisRunSummary,
  type MonitoringErrorEntry,
} from "@/lib/api";
import { DEFAULT_CONFLICT } from "@/lib/conflictDefaults";
import { AGENT_NAME_TO_KEY } from "@/components/dashboard/agentsConfig";
import { toast } from "sonner";
import {
  Anchor,
  ArrowLeft,
  AlertTriangle,
  Activity,
  Clock,
  Database,
  History,
  Play,
  RefreshCw,
  ChevronDown,
  DollarSign,
  Eye,
  EyeOff,
  Layers,
  ScrollText,
  Search,
} from "lucide-react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { PageSkeleton } from "@/components/ui/skeleton";
import { SEO } from "@/components/SEO";
import { TITLE_AGENT_MONITOR, DESCRIPTION_AGENT_MONITOR } from "@/lib/seoCopy";

type AgentStatusEntry = {
  status: string;
  fetched_at?: string;
  duration_ms?: number;
  confidence?: { level?: string; sources_ok?: string[]; sources_missing?: string[] };
  data_freshness?: string;
  sources?: unknown[];
  fallback_used?: boolean;
  error_summary?: string | null;
};

type HormuzRiskLevel = "low" | "medium" | "high" | "critical";
type HormuzAmpel = "red" | "yellow" | "green";

type HormuzDailyEntry = {
  date: string;
  transitCount: number;
  tankerCount: number;
  incidents: number;
  warRiskPct: number;
  warRiskCover: boolean;
  riskLevel: HormuzRiskLevel;
  severeIncident: boolean;
};

type HormuzFormState = {
  date: string;
  transitCount: string;
  tankerCount: string;
  incidents: string;
  warRiskPct: string;
  warRiskCover: "yes" | "no";
  riskLevel: HormuzRiskLevel;
  severeIncident: "yes" | "no";
};

const HORMUZ_STORAGE_KEY = "dwr:hormuz-monitor:v1";
const DEFAULT_BASELINE_TRANSITS = 120;
const DEFAULT_BASELINE_ETA_WEEKS = 6;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function toIsoDateLocal(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function defaultHormuzForm(): HormuzFormState {
  return {
    date: toIsoDateLocal(new Date()),
    transitCount: "",
    tankerCount: "",
    incidents: "",
    warRiskPct: "",
    warRiskCover: "yes",
    riskLevel: "critical",
    severeIncident: "no",
  };
}

function parseFormToEntry(form: HormuzFormState): HormuzDailyEntry | null {
  const transitCount = Number(form.transitCount);
  const tankerCount = Number(form.tankerCount);
  const incidents = Number(form.incidents);
  const warRiskPct = Number(form.warRiskPct);
  if (!form.date) return null;
  if (![transitCount, tankerCount, incidents, warRiskPct].every(Number.isFinite)) return null;
  return {
    date: form.date,
    transitCount: Math.max(0, Math.round(transitCount)),
    tankerCount: Math.max(0, Math.round(tankerCount)),
    incidents: Math.max(0, Math.round(incidents)),
    warRiskPct: clamp(warRiskPct, 0, 500),
    warRiskCover: form.warRiskCover === "yes",
    riskLevel: form.riskLevel,
    severeIncident: form.severeIncident === "yes",
  };
}

function getHormuzAmpel(entry: HormuzDailyEntry, baselineTransits: number, entries: HormuzDailyEntry[]): HormuzAmpel {
  const baseline = Math.max(1, baselineTransits);
  const transitPct = (entry.transitCount / baseline) * 100;
  const sorted = [...entries].sort((a, b) => a.date.localeCompare(b.date));
  const lastFive = sorted.slice(-5);
  const incidentsDownFiveDays =
    lastFive.length >= 5 &&
    lastFive.every((v, idx, arr) => idx === 0 || v.incidents <= arr[idx - 1].incidents) &&
    lastFive[lastFive.length - 1].incidents < lastFive[0].incidents;

  if (entry.riskLevel === "critical" || transitPct < 20) return "red";
  if (transitPct > 60 && entry.riskLevel !== "critical" && entry.warRiskCover) {
    const lastSeven = sorted.slice(-7);
    const stableWeek =
      lastSeven.length >= 7 &&
      lastSeven.every((v) => (v.transitCount / baseline) * 100 > 60 && v.riskLevel !== "critical" && v.riskLevel !== "high");
    if (stableWeek) return "green";
  }
  if (transitPct >= 20 && transitPct <= 60 && incidentsDownFiveDays) return "yellow";
  return "red";
}

function computeEtaWeeks(entry: HormuzDailyEntry, entries: HormuzDailyEntry[]): number {
  let eta = DEFAULT_BASELINE_ETA_WEEKS;
  const sorted = [...entries].sort((a, b) => a.date.localeCompare(b.date));
  const lastThree = sorted.slice(-3);
  const improvingThreeDays =
    lastThree.length >= 3 &&
    lastThree.every((v, idx, arr) => idx === 0 || (v.transitCount >= arr[idx - 1].transitCount && v.incidents <= arr[idx - 1].incidents));
  if (improvingThreeDays) eta -= 1;
  if (entry.severeIncident) eta += 2;
  if (entry.riskLevel === "critical") eta = Math.max(4, eta);
  return clamp(eta, 1, 26);
}

function formatErrorTime(ts: number): string {
  try {
    return new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "short", timeStyle: "medium" });
  } catch {
    return "–";
  }
}

function isAgentBlindOps(row: AgentsOpsAgentRow): boolean {
  const er = row.error_rate_24h;
  if (er != null && er >= 0.25) return true;
  if (row.last_run?.outcome === "failed") return true;
  return false;
}

function formatRelativeTime(iso?: string): string {
  if (!iso) return "–";
  try {
    const d = new Date(iso);
    const now = Date.now();
    const diff = (now - d.getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return "–";
  }
}

const POLL_INTERVAL_MS = 6000;
const RUN_AGAIN_TIMEOUT_MS = 150_000;

const AgentMonitor = () => {
  return (
    <>
      <SEO
        title={TITLE_AGENT_MONITOR}
        description={DESCRIPTION_AGENT_MONITOR}
        path="/app/monitoring"
        noindex
      />
      <AgentMonitorContent />
    </>
  );
};

function AgentMonitorContent() {
  const [status, setStatus] = useState<Record<string, AgentStatusEntry> | null>(null);
  const [health, setHealth] = useState<AgentsHealthResponse | null>(null);
  const [history, setHistory] = useState<AnalysisRunSummary[]>([]);
  const [monitoring, setMonitoring] = useState<AgentsMonitoringResponse | null>(null);
  const [opsStatus, setOpsStatus] = useState<AgentsOpsStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runAgainLoading, setRunAgainLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [googleSnapshotLoading, setGoogleSnapshotLoading] = useState(false);
  const [hormuzForm, setHormuzForm] = useState<HormuzFormState>(() => defaultHormuzForm());
  const [hormuzEntries, setHormuzEntries] = useState<HormuzDailyEntry[]>(() => {
    try {
      const raw = localStorage.getItem(HORMUZ_STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw) as HormuzDailyEntry[];
      if (!Array.isArray(parsed)) return [];
      return parsed
        .filter((e) => e && typeof e.date === "string")
        .sort((a, b) => b.date.localeCompare(a.date));
    } catch {
      return [];
    }
  });
  const [baselineTransits, setBaselineTransits] = useState<number>(DEFAULT_BASELINE_TRANSITS);

  const fetchAll = useCallback(async () => {
    setError(null);
    try {
      const [statusRes, healthRes, historyRes, monRes, opsRes] = await Promise.all([
        getAgentsStatus(),
        getAgentsHealth(),
        getAgentsHistory(30),
        getAgentsMonitoring(),
        getAgentsOpsStatus(),
      ]);
      if (statusRes && typeof statusRes === "object") setStatus(statusRes as Record<string, AgentStatusEntry>);
      if (healthRes) setHealth(healthRes);
      if (historyRes?.runs) setHistory(historyRes.runs);
      if (monRes) setMonitoring(monRes);
      if (opsRes) setOpsStatus(opsRes);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load monitoring data");
    } finally {
      setLoading(false);
    }
  }, []);

  const runAnalysisAgain = useCallback(async () => {
    setRunAgainLoading(true);
    setError(null);
    try {
      const statusBefore = await getAnalyzeStatus(DEFAULT_CONFLICT);
      const atBefore = statusBefore?.at;
      try {
        await triggerRefreshAnalysis(DEFAULT_CONFLICT);
      } catch (triggerErr) {
        const msg = triggerErr instanceof Error ? triggerErr.message : "Trigger failed";
        setError(msg);
        toast.error("Analysis could not be started", { description: msg });
        return;
      }
      toast.info("Analysis running…", { description: "Agent status will update when finished." });
      const deadline = Date.now() + RUN_AGAIN_TIMEOUT_MS;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        const st = await getAnalyzeStatus(DEFAULT_CONFLICT);
        if (st?.error) {
          setError(st.error);
          toast.error("Analysis failed", { description: st.error });
          break;
        }
        if (st?.cached && st?.at != null && st.at !== atBefore) {
          toast.success("Analysis complete", { description: "Agent status updated." });
          break;
        }
      }
      await fetchAll();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Run failed";
      setError(msg);
      toast.error("Error", { description: msg });
    } finally {
      setRunAgainLoading(false);
    }
  }, [fetchAll]);

  const refreshGoogleSerpSnapshot = useCallback(async () => {
    setGoogleSnapshotLoading(true);
    try {
      const res = await postGoogleTrendSnapshot(DEFAULT_CONFLICT);
      if (!res) {
        toast.error("Google snapshot failed", { description: "No response from backend." });
        return;
      }
      if (!res.ok) {
        toast.error("Google snapshot unavailable", { description: res.message || res.error || "Unknown error" });
      } else {
        toast.success("Google snapshot updated", { description: res.query?.slice(0, 80) });
      }
      await fetchAll();
    } catch (e) {
      toast.error("Google snapshot failed", { description: e instanceof Error ? e.message : "Error" });
    } finally {
      setGoogleSnapshotLoading(false);
    }
  }, [fetchAll]);

  const refreshMonitor = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const statusBefore = await getAnalyzeStatus(DEFAULT_CONFLICT);
      const atBefore = statusBefore?.at;
      try {
        await triggerRefreshAnalysis(DEFAULT_CONFLICT);
      } catch (triggerErr) {
        const msg = triggerErr instanceof Error ? triggerErr.message : "Trigger failed";
        setError(msg);
        toast.error("Refresh failed", { description: msg });
        return;
      }
      toast.info("Refreshing from backend…", { description: "Running analysis; monitor will update when done." });
      const deadline = Date.now() + RUN_AGAIN_TIMEOUT_MS;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        const st = await getAnalyzeStatus(DEFAULT_CONFLICT);
        if (st?.error) {
          setError(st.error);
          toast.error("Analysis failed", { description: st.error });
          break;
        }
        if (st?.cached && st?.at != null && st.at !== atBefore) {
          toast.success("Monitor updated", { description: "Agent and source data refreshed from backend." });
          break;
        }
      }
      const [statusRes, healthRes, historyRes, monRes, opsRes] = await Promise.all([
        getAgentsStatus(),
        getAgentsHealth(),
        getAgentsHistory(30),
        getAgentsMonitoring(),
        getAgentsOpsStatus(),
      ]);
      if (statusRes && typeof statusRes === "object") setStatus(statusRes as Record<string, AgentStatusEntry>);
      if (healthRes) setHealth(healthRes);
      if (historyRes?.runs) setHistory(historyRes.runs);
      if (monRes) setMonitoring(monRes);
      if (opsRes) setOpsStatus(opsRes);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to refresh");
      toast.error("Refresh failed", { description: e instanceof Error ? e.message : "Unknown error" });
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 60_000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  useEffect(() => {
    try {
      localStorage.setItem(HORMUZ_STORAGE_KEY, JSON.stringify(hormuzEntries));
    } catch {
      // ignore
    }
  }, [hormuzEntries]);

  const lastUpdated = useMemo(() => {
    if (!status) return null;
    let latest = 0;
    for (const e of Object.values(status)) {
      if (e?.fetched_at) {
        const t = new Date(e.fetched_at).getTime();
        if (t > latest) latest = t;
      }
    }
    return latest || null;
  }, [status]);

  const agentKeys = Object.keys(AGENT_NAME_TO_KEY);
  const statusEntries = status
    ? agentKeys.map((name) => ({ name, key: AGENT_NAME_TO_KEY[name], entry: status[AGENT_NAME_TO_KEY[name]] }))
    : [];
  const degradedSources = health?.sources?.filter((s) => s.status === "degraded" || s.status === "down") ?? [];
  const fallbackAgents = statusEntries.filter((e) => e.entry?.fallback_used);

  const fallbackRollup = useMemo(() => {
    const entries = Object.entries(monitoring?.fallback?.by_agent ?? {});
    return entries.sort((a, b) => b[1] - a[1]);
  }, [monitoring]);

  const dailySpendChart = useMemo(() => {
    const d = monitoring?.cost?.daily ?? [];
    return [...d].slice(0, 14).reverse().map((row) => ({
      label: row.day.length >= 10 ? row.day.slice(5) : row.day,
      spend: row.spend_usd,
    }));
  }, [monitoring]);

  const lastRunByAgent = useMemo(() => {
    const b = monitoring?.cost?.last_run?.by_agent ?? {};
    return Object.entries(b).sort((a, b) => b[1].in + b[1].out - (a[1].in + a[1].out));
  }, [monitoring]);

  const monthByAgent = useMemo(() => {
    const b = monitoring?.cost?.month_by_agent ?? {};
    return Object.entries(b).sort((a, b) => b[1].in + b[1].out - (a[1].in + a[1].out));
  }, [monitoring]);

  const latestHormuzEntry = hormuzEntries[0] ?? null;
  const latestAmpel = useMemo(() => {
    if (!latestHormuzEntry) return null;
    return getHormuzAmpel(latestHormuzEntry, baselineTransits, hormuzEntries);
  }, [latestHormuzEntry, baselineTransits, hormuzEntries]);
  const latestEtaWeeks = useMemo(() => {
    if (!latestHormuzEntry) return null;
    return computeEtaWeeks(latestHormuzEntry, hormuzEntries);
  }, [latestHormuzEntry, hormuzEntries]);

  function upsertHormuzEntry(entry: HormuzDailyEntry) {
    setHormuzEntries((prev) => {
      const next = [...prev.filter((e) => e.date !== entry.date), entry];
      next.sort((a, b) => b.date.localeCompare(a.date));
      return next;
    });
  }

  function handleSaveHormuzEntry() {
    const parsed = parseFormToEntry(hormuzForm);
    if (!parsed) {
      toast.error("Bitte alle Hormuz-Felder korrekt ausfüllen.");
      return;
    }
    upsertHormuzEntry(parsed);
    setHormuzForm((prev) => ({ ...defaultHormuzForm(), date: prev.date }));
    toast.success("Hormuz-Tageswert gespeichert.");
  }

  function deleteHormuzDate(date: string) {
    setHormuzEntries((prev) => prev.filter((e) => e.date !== date));
  }

  if (loading && !status) {
    return (
      <div className="min-h-screen bg-background text-foreground p-6">
        <div className="max-w-6xl mx-auto">
          <PageSkeleton />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground p-4 sm:p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link to="/app/dashboard">
              <Button variant="ghost" size="icon" aria-label="Back to dashboard">
                <ArrowLeft className="h-4 w-4" aria-hidden />
              </Button>
            </Link>
            <div>
              <h1 className="text-xl font-semibold font-mono tracking-tight">Agent & Source Monitor</h1>
              <p className="text-xs text-muted-foreground mt-0.5">Status and health of all agents and their data sources (from last analysis run).</p>
            </div>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {lastUpdated != null && (
              <span className="text-xs text-muted-foreground">
                Last updated: {formatRelativeTime(new Date(lastUpdated).toISOString())}
              </span>
            )}
            <div className="flex items-center gap-2">
              <Button
                variant="default"
                size="sm"
                onClick={runAnalysisAgain}
                disabled={runAgainLoading || refreshing}
                className="gap-1.5"
              >
                <Play className="h-3.5 w-3.5" aria-hidden />
                {runAgainLoading ? "Running…" : "Run analysis again"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={refreshMonitor}
                disabled={refreshing || runAgainLoading}
                className="gap-1.5"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} aria-hidden />
                {refreshing ? "Refreshing…" : "Refresh"}
              </Button>
            </div>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-2 text-destructive text-sm">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-mono flex items-center gap-2">
              <Anchor className="h-4 w-4" />
              Hormuz Closure Monitor
            </CardTitle>
            <p className="text-xs text-muted-foreground font-normal">
              Daily tracker for transit disruption, incidents, insurance and risk level. Ampel and ETA are calculated automatically from your entries.
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2">
              <Input
                type="date"
                value={hormuzForm.date}
                onChange={(e) => setHormuzForm((p) => ({ ...p, date: e.target.value }))}
                aria-label="Date"
              />
              <Input
                type="number"
                placeholder="Transits/24h"
                value={hormuzForm.transitCount}
                onChange={(e) => setHormuzForm((p) => ({ ...p, transitCount: e.target.value }))}
                aria-label="Transits per day"
              />
              <Input
                type="number"
                placeholder="Tanker/24h"
                value={hormuzForm.tankerCount}
                onChange={(e) => setHormuzForm((p) => ({ ...p, tankerCount: e.target.value }))}
                aria-label="Tankers per day"
              />
              <Input
                type="number"
                placeholder="Incidents/24h"
                value={hormuzForm.incidents}
                onChange={(e) => setHormuzForm((p) => ({ ...p, incidents: e.target.value }))}
                aria-label="Incidents per day"
              />
              <Input
                type="number"
                placeholder="War risk %"
                value={hormuzForm.warRiskPct}
                onChange={(e) => setHormuzForm((p) => ({ ...p, warRiskPct: e.target.value }))}
                aria-label="War risk premium percent"
              />
              <select
                value={hormuzForm.warRiskCover}
                onChange={(e) => setHormuzForm((p) => ({ ...p, warRiskCover: e.target.value as "yes" | "no" }))}
                className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
                aria-label="Insurance cover available"
              >
                <option value="yes">Cover: yes</option>
                <option value="no">Cover: no</option>
              </select>
              <select
                value={hormuzForm.riskLevel}
                onChange={(e) => setHormuzForm((p) => ({ ...p, riskLevel: e.target.value as HormuzRiskLevel }))}
                className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
                aria-label="Risk level"
              >
                <option value="low">Risk: low</option>
                <option value="medium">Risk: medium</option>
                <option value="high">Risk: high</option>
                <option value="critical">Risk: critical</option>
              </select>
              <select
                value={hormuzForm.severeIncident}
                onChange={(e) => setHormuzForm((p) => ({ ...p, severeIncident: e.target.value as "yes" | "no" }))}
                className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
                aria-label="Severe incident"
              >
                <option value="no">Severe: no</option>
                <option value="yes">Severe: yes</option>
              </select>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Input
                type="number"
                className="w-44"
                value={baselineTransits}
                onChange={(e) => setBaselineTransits(Math.max(1, Number(e.target.value) || DEFAULT_BASELINE_TRANSITS))}
                aria-label="Baseline daily transits"
              />
              <span className="text-xs text-muted-foreground">baseline transits/day</span>
              <Button size="sm" onClick={handleSaveHormuzEntry}>Save daily entry</Button>
              <Button size="sm" variant="outline" onClick={() => setHormuzForm(defaultHormuzForm())}>Reset form</Button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="rounded-md border border-border p-3">
                <p className="text-[11px] font-mono text-muted-foreground uppercase">Current Status</p>
                <p className="text-lg font-semibold mt-1">
                  {latestAmpel ? (
                    <Badge
                      variant={latestAmpel === "green" ? "secondary" : latestAmpel === "yellow" ? "outline" : "destructive"}
                      className="text-xs uppercase"
                    >
                      {latestAmpel}
                    </Badge>
                  ) : "–"}
                </p>
              </div>
              <div className="rounded-md border border-border p-3">
                <p className="text-[11px] font-mono text-muted-foreground uppercase">ETA Reopen</p>
                <p className="text-lg font-semibold mt-1">{latestEtaWeeks != null ? `${latestEtaWeeks} week(s)` : "–"}</p>
              </div>
              <div className="rounded-md border border-border p-3">
                <p className="text-[11px] font-mono text-muted-foreground uppercase">Latest Transit Share</p>
                <p className="text-lg font-semibold mt-1">
                  {latestHormuzEntry ? `${Math.round((latestHormuzEntry.transitCount / Math.max(1, baselineTransits)) * 100)}%` : "–"}
                </p>
              </div>
            </div>

            {hormuzEntries.length > 0 ? (
              <div className="overflow-x-auto rounded-md border border-border/60">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/30 text-left">
                      <th className="py-2 px-2 font-mono">Date</th>
                      <th className="py-2 px-2 font-mono text-right">Transits</th>
                      <th className="py-2 px-2 font-mono text-right">Tankers</th>
                      <th className="py-2 px-2 font-mono text-right">Incidents</th>
                      <th className="py-2 px-2 font-mono text-right">War risk</th>
                      <th className="py-2 px-2 font-mono">Risk</th>
                      <th className="py-2 px-2 font-mono text-right">ETA</th>
                      <th className="py-2 px-2 font-mono text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {hormuzEntries.map((row) => (
                      <tr key={row.date} className="border-b border-border/40">
                        <td className="py-1.5 px-2 font-mono">{row.date}</td>
                        <td className="py-1.5 px-2 text-right tabular-nums">{row.transitCount}</td>
                        <td className="py-1.5 px-2 text-right tabular-nums">{row.tankerCount}</td>
                        <td className="py-1.5 px-2 text-right tabular-nums">{row.incidents}</td>
                        <td className="py-1.5 px-2 text-right tabular-nums">{row.warRiskPct.toFixed(1)}%</td>
                        <td className="py-1.5 px-2 uppercase">{row.riskLevel}</td>
                        <td className="py-1.5 px-2 text-right tabular-nums">{computeEtaWeeks(row, hormuzEntries)}w</td>
                        <td className="py-1.5 px-2 text-right">
                          <Button size="sm" variant="ghost" onClick={() => deleteHormuzDate(row.date)}>Delete</Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">No Hormuz entries yet. Add the first daily datapoint above.</p>
            )}
          </CardContent>
        </Card>

        {/* Ops heartbeat: 24h error rate + last run (backend process memory) */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-mono flex items-center gap-2">
              <Activity className="h-4 w-4" />
              Ops heartbeat
            </CardTitle>
            <p className="text-xs text-muted-foreground font-normal">
              From structured <code className="text-[10px]">agent_heartbeat</code> logs per DAG run. Error rate uses
              the last 24h of in-memory runs (resets on deploy). Haiku quota is monthly token spend vs budget.
            </p>
            {opsStatus?.anthropic_haiku_global && (
              <p className="text-xs text-muted-foreground font-mono mt-1">
                Haiku month: ${opsStatus.anthropic_haiku_global.month_spent_usd?.toFixed(4) ?? "–"} / $
                {opsStatus.anthropic_haiku_global.month_budget_usd ?? "–"} · {opsStatus.anthropic_haiku_global.model ?? ""}
              </p>
            )}
          </CardHeader>
          <CardContent className="space-y-2">
            {opsStatus?.agents?.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse min-w-[720px]">
                  <thead>
                    <tr className="border-b border-border text-left">
                      <th className="py-1.5 pr-2 font-mono text-xs">Vision</th>
                      <th className="py-1.5 pr-2 font-mono text-xs">Agent</th>
                      <th className="py-1.5 pr-2 font-mono text-xs">24h err</th>
                      <th className="py-1.5 pr-2 font-mono text-xs">Last outcome</th>
                      <th className="py-1.5 pr-2 font-mono text-xs">Sources OK</th>
                      <th className="py-1.5 font-mono text-xs">Last run</th>
                    </tr>
                  </thead>
                  <tbody>
                    {opsStatus.agents.map((row) => {
                      const blind = isAgentBlindOps(row);
                      const er = row.error_rate_24h;
                      const src = row.last_run?.sources_ok_ratio;
                      return (
                        <tr key={row.agent} className="border-b border-border/40">
                          <td className="py-1.5 pr-2 align-middle" title={blind ? "Elevated failures or last run failed" : "OK"}>
                            {blind ? (
                              <EyeOff className="h-4 w-4 text-amber-500" aria-label="Likely blind or degraded" />
                            ) : (
                              <Eye className="h-4 w-4 text-emerald-600/80" aria-label="OK" />
                            )}
                          </td>
                          <td className="py-1.5 pr-2 font-mono text-xs">{row.agent}</td>
                          <td className="py-1.5 pr-2 tabular-nums text-xs">
                            {er != null ? `${(er * 100).toFixed(1)}% (${row.runs_24h_sample} runs)` : "–"}
                          </td>
                          <td className="py-1.5 pr-2 text-xs">
                            {row.last_run?.outcome ? (
                              <Badge variant={row.last_run.outcome === "failed" ? "destructive" : "secondary"} className="text-[10px]">
                                {row.last_run.outcome}
                              </Badge>
                            ) : (
                              "–"
                            )}
                          </td>
                          <td className="py-1.5 pr-2 tabular-nums text-xs">
                            {src != null && src !== undefined ? `${Math.round(src * 100)}%` : "–"}
                          </td>
                          <td className="py-1.5 text-xs text-muted-foreground">
                            {row.last_run?.at_iso
                              ? formatRelativeTime(row.last_run.at_iso)
                              : "–"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                No heartbeat data yet. Run at least one full analysis after deploy to populate this table.
              </p>
            )}
            {opsStatus?.quota_note && (
              <p className="text-[10px] text-muted-foreground pt-1 border-t border-border/50">{opsStatus.quota_note}</p>
            )}
          </CardContent>
        </Card>

        {/* Google web SERP snapshot (SerpAPI; separate MONITORING_GOOGLE_SERPAPI_* caps) */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-mono flex items-center gap-2">
              <Search className="h-4 w-4" />
              Google SERP snapshot (conflict query)
            </CardTitle>
            <p className="text-xs text-muted-foreground font-normal">
              “What does Google show now?” for the same ranking query as cross-encoder ranking (
              <code className="text-[10px]">RANKING_QUERY_*</code>). One SerpAPI search per refresh; caps:{" "}
              <code className="text-[10px]">MONITORING_GOOGLE_SERPAPI_HOURLY_CAP</code>,{" "}
              <code className="text-[10px]">MONITORING_GOOGLE_SERPAPI_MONTHLY_CAP</code> (separate from Pentagon).
            </p>
            {monitoring?.google_trend_serp?.quota && (
              <p className="text-[11px] text-muted-foreground font-mono mt-1">
                Quota (UTC): {monitoring.google_trend_serp.quota.hour_count ?? "–"}/
                {monitoring.google_trend_serp.quota.hourly_cap ?? "–"} this hour ·{" "}
                {monitoring.google_trend_serp.quota.month_count ?? "–"}/
                {monitoring.google_trend_serp.quota.monthly_cap ?? "–"} this month
              </p>
            )}
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={
                  googleSnapshotLoading || runAgainLoading || refreshing
                }
                className="gap-1.5"
                onClick={() => void refreshGoogleSerpSnapshot()}
              >
                <RefreshCw className={`h-3.5 w-3.5 ${googleSnapshotLoading ? "animate-spin" : ""}`} aria-hidden />
                {googleSnapshotLoading ? "Fetching…" : "Refresh Google snapshot"}
              </Button>
              <span className="text-xs text-muted-foreground">
                Conflict: <span className="font-mono">{DEFAULT_CONFLICT}</span>
              </span>
            </div>
            {monitoring?.google_trend_serp &&
              !monitoring.google_trend_serp.ok &&
              (monitoring.google_trend_serp.message || monitoring.google_trend_serp.error) && (
                <p className="text-sm text-destructive">
                  {monitoring.google_trend_serp.message || monitoring.google_trend_serp.error}
                </p>
              )}
            {monitoring?.google_trend_serp?.ok && monitoring.google_trend_serp.query && (
              <p className="text-xs text-muted-foreground">
                <span className="font-mono">Query:</span> {monitoring.google_trend_serp.query}
                {monitoring.google_trend_serp.fetched_at && (
                  <span className="ml-2">
                    · fetched {formatRelativeTime(monitoring.google_trend_serp.fetched_at)}
                  </span>
                )}
              </p>
            )}
            {monitoring?.google_trend_serp?.organic && monitoring.google_trend_serp.organic.length > 0 ? (
              <ul className="space-y-2 max-h-80 overflow-y-auto text-sm border border-border/60 rounded-md p-3">
                {monitoring.google_trend_serp.organic.map((row, i) => (
                  <li key={row.link || `${row.title}-${i}`} className="border-b border-border/40 pb-2 last:border-0 last:pb-0">
                    <div className="flex items-start gap-2">
                      <span className="text-[10px] font-mono text-muted-foreground tabular-nums w-5 shrink-0 pt-0.5">
                        {row.position ?? i + 1}
                      </span>
                      <div className="min-w-0">
                        {row.link ? (
                          <a
                            href={row.link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-medium text-primary hover:underline break-words"
                          >
                            {row.title || row.link}
                          </a>
                        ) : (
                          <span className="font-medium break-words">{row.title || "—"}</span>
                        )}
                        {row.snippet ? (
                          <p className="text-xs text-muted-foreground mt-0.5 leading-snug break-words">{row.snippet}</p>
                        ) : null}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            ) : monitoring?.google_trend_serp?.ok ? (
              <p className="text-xs text-muted-foreground">No organic results in the response.</p>
            ) : (
              <p className="text-xs text-muted-foreground">
                No snapshot yet. Set <code className="text-[10px]">SERPAPI_KEY</code> and refresh, or check caps /
                <code className="text-[10px]"> MONITORING_GOOGLE_SERP_ENABLED</code>.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Live alerts */}
        {(degradedSources.length > 0 || fallbackAgents.length > 0) && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-mono flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                Live alerts
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm space-y-2">
              {degradedSources.length > 0 && (
                <p>
                  <strong>Degraded/down sources:</strong>{" "}
                  {degradedSources.map((s) => `${s.source} (${s.agent})`).join(", ")}
                </p>
              )}
              {fallbackAgents.length > 0 && (
                <p>
                  <strong>Agents using fallback data:</strong>{" "}
                  {fallbackAgents.map((e) => e.name).join(", ")}
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Fallback usage (backup sources / degraded paths) */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-mono flex items-center gap-2">
              <Layers className="h-4 w-4" />
              Fallback usage (process lifetime)
            </CardTitle>
            <p className="text-xs text-muted-foreground font-normal">
              Counts when an agent marked <code className="text-[10px]">fallback_used</code> in telemetry (backup sources or rule-based fallbacks). Resets on server restart.
            </p>
          </CardHeader>
          <CardContent className="space-y-3">
            {monitoring?.fallback ? (
              <>
                <div className="flex flex-wrap gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground text-xs font-mono">Total events</span>
                    <p className="text-lg font-mono tabular-nums">{monitoring.fallback.total_events}</p>
                  </div>
                  {monitoring.fallback.last_run && (
                    <div>
                      <span className="text-muted-foreground text-xs font-mono">Last run</span>
                      <p className="text-xs">
                        {monitoring.fallback.last_run.conflict}: {monitoring.fallback.last_run.count} agent(s) –{" "}
                        {monitoring.fallback.last_run.agents.join(", ") || "–"}
                      </p>
                    </div>
                  )}
                </div>
                {fallbackRollup.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr className="border-b border-border text-left">
                          <th className="py-1.5 font-mono text-xs">Agent</th>
                          <th className="py-1.5 font-mono text-xs text-right">Fallback events</th>
                        </tr>
                      </thead>
                      <tbody>
                        {fallbackRollup.map(([agent, n]) => (
                          <tr key={agent} className="border-b border-border/40">
                            <td className="py-1 font-mono text-xs">{agent}</td>
                            <td className="py-1 text-right tabular-nums">{n}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">No fallback events recorded yet.</p>
                )}
              </>
            ) : (
              <p className="text-xs text-muted-foreground">Load monitoring data (refresh) to see fallback stats.</p>
            )}
          </CardContent>
        </Card>

        {/* Haiku cost & tokens */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-mono flex items-center gap-2">
              <DollarSign className="h-4 w-4" />
              Cost tracker (Claude Haiku)
            </CardTitle>
            <p className="text-xs text-muted-foreground font-normal">
              Token usage attributed by pipeline (news, cyber, diplo, etc.). Monthly budget from{" "}
              <code className="text-[10px]">HAIKU_MONTHLY_BUDGET</code>. Daily bars accumulate per analysis run.
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            {monitoring?.cost?.month_budget_usd != null ? (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                  <div>
                    <span className="text-muted-foreground text-[10px] font-mono uppercase">Month spend</span>
                    <p className="font-mono tabular-nums">
                      ${(monitoring.cost.month_spent_usd ?? 0).toFixed(4)} / ${monitoring.cost.month_budget_usd?.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <span className="text-muted-foreground text-[10px] font-mono uppercase">Month tokens</span>
                    <p className="font-mono text-xs tabular-nums">
                      in {(monitoring.cost.month_input_tokens ?? 0).toLocaleString()} · out{" "}
                      {(monitoring.cost.month_output_tokens ?? 0).toLocaleString()}
                    </p>
                  </div>
                  <div>
                    <span className="text-muted-foreground text-[10px] font-mono uppercase">Last run est.</span>
                    <p className="font-mono tabular-nums">
                      ${(monitoring.cost.last_run?.estimated_cost_usd ?? 0).toFixed(6)}
                    </p>
                  </div>
                  <div>
                    <span className="text-muted-foreground text-[10px] font-mono uppercase">Today (UTC)</span>
                    <p className="font-mono tabular-nums">
                      ${(monitoring.cost.today?.spend_usd ?? 0).toFixed(6)}
                    </p>
                  </div>
                </div>
                {lastRunByAgent.length > 0 && (
                  <div>
                    <p className="text-[11px] font-mono text-muted-foreground mb-1">Last run – tokens by tag</p>
                    <div className="overflow-x-auto max-h-40 overflow-y-auto rounded border border-border/60">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-border bg-muted/30">
                            <th className="text-left py-1 px-2 font-mono">Tag</th>
                            <th className="text-right py-1 px-2 font-mono">In</th>
                            <th className="text-right py-1 px-2 font-mono">Out</th>
                          </tr>
                        </thead>
                        <tbody>
                          {lastRunByAgent.map(([tag, io]) => (
                            <tr key={tag} className="border-b border-border/40">
                              <td className="py-1 px-2 font-mono">{tag}</td>
                              <td className="py-1 px-2 text-right tabular-nums">{io.in.toLocaleString()}</td>
                              <td className="py-1 px-2 text-right tabular-nums">{io.out.toLocaleString()}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
                {monthByAgent.length > 0 && (
                  <div>
                    <p className="text-[11px] font-mono text-muted-foreground mb-1">Month – tokens by tag</p>
                    <div className="overflow-x-auto max-h-36 overflow-y-auto rounded border border-border/60">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-border bg-muted/30">
                            <th className="text-left py-1 px-2 font-mono">Tag</th>
                            <th className="text-right py-1 px-2 font-mono">In</th>
                            <th className="text-right py-1 px-2 font-mono">Out</th>
                          </tr>
                        </thead>
                        <tbody>
                          {monthByAgent.map(([tag, io]) => (
                            <tr key={tag} className="border-b border-border/40">
                              <td className="py-1 px-2 font-mono">{tag}</td>
                              <td className="py-1 px-2 text-right tabular-nums">{io.in.toLocaleString()}</td>
                              <td className="py-1 px-2 text-right tabular-nums">{io.out.toLocaleString()}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
                {dailySpendChart.length > 0 ? (
                  <div className="h-[200px] w-full pt-2">
                    <p className="text-[11px] font-mono text-muted-foreground mb-2">Daily Haiku spend (UTC, recent)</p>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={dailySpendChart} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                        <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                        <YAxis tick={{ fontSize: 10 }} width={40} />
                        <Tooltip
                          formatter={(v: number) => [`$${v.toFixed(6)}`, "Spend"]}
                          labelFormatter={(l) => `Day ${l}`}
                        />
                        <Bar dataKey="spend" fill="hsl(var(--primary))" name="USD" radius={[2, 2, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">Daily spend appears after completed analysis runs.</p>
                )}
              </>
            ) : (
              <p className="text-xs text-muted-foreground">Cost metrics unavailable (backend offline or endpoint missing).</p>
            )}
          </CardContent>
        </Card>

        {/* Error log */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-mono flex items-center gap-2">
              <ScrollText className="h-4 w-4" />
              Error log
            </CardTitle>
            <p className="text-xs text-muted-foreground font-normal">
              Supervisor and agent-level errors from recent runs. Expand a row for full detail when available.
            </p>
          </CardHeader>
          <CardContent>
            {monitoring?.errors && monitoring.errors.length > 0 ? (
              <ul className="divide-y divide-border/60 max-h-[420px] overflow-y-auto">
                {monitoring.errors.map((err: MonitoringErrorEntry) => (
                  <li key={err.id} className="py-2 first:pt-0">
                    <Collapsible>
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0 flex-1 space-y-1">
                          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground font-mono">
                            <span>{formatErrorTime(err.ts)}</span>
                            {err.conflict && <span>· {err.conflict}</span>}
                            {err.agent && (
                              <Badge variant="secondary" className="text-[10px]">
                                {err.agent}
                              </Badge>
                            )}
                            {err.source && (
                              <span className="text-[10px] truncate max-w-[120px]" title={err.source}>
                                {err.source}
                              </span>
                            )}
                          </div>
                          <p className="text-sm leading-snug break-words">{err.message}</p>
                        </div>
                        <CollapsibleTrigger asChild>
                          <Button variant="outline" size="sm" className="h-8 gap-1 shrink-0 text-xs font-mono">
                            Detail
                            <ChevronDown className="h-3 w-3" />
                          </Button>
                        </CollapsibleTrigger>
                      </div>
                      <CollapsibleContent className="mt-2">
                        <pre className="text-[11px] leading-relaxed whitespace-pre-wrap break-words rounded-md border border-border bg-muted/30 p-3 font-mono max-h-64 overflow-y-auto">
                          {err.detail?.trim() || "No additional detail stored."}
                        </pre>
                      </CollapsibleContent>
                    </Collapsible>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">No errors recorded, or monitoring data not loaded.</p>
            )}
          </CardContent>
        </Card>

        {/* Agent status grid */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-mono flex items-center gap-2">
              <Activity className="h-4 w-4" />
              Agent status (last run)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
              {statusEntries.map(({ name, key, entry }) => {
                const s = entry?.status ?? "ok";
                const okCount = Array.isArray(entry?.sources)
                  ? (entry.sources as { status?: string }[]).filter((x) => x.status === "ok").length
                  : 0;
                const totalSources = Array.isArray(entry?.sources) ? entry.sources.length : 0;
                return (
                  <div
                    key={key}
                    className="rounded-lg border border-border bg-card p-3 text-sm space-y-1"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className={`inline-block w-2 h-2 rounded-full shrink-0 ${
                          s === "ok" ? "bg-emerald-500" : "bg-destructive"
                        }`}
                      />
                      <span className="font-mono text-xs truncate">{name}</span>
                    </div>
                    {entry?.duration_ms != null && (
                      <div className="flex items-center gap-1 text-muted-foreground text-xs">
                        <Clock className="h-3 w-3" />
                        {entry.duration_ms} ms
                      </div>
                    )}
                    {entry?.fetched_at && (
                      <div className="text-[11px] text-muted-foreground">
                        {formatRelativeTime(entry.fetched_at)}
                      </div>
                    )}
                    <div className="flex flex-wrap gap-1">
                      {entry?.confidence?.level && (
                        <Badge variant="secondary" className="text-[10px]">
                          {entry.confidence.level}
                        </Badge>
                      )}
                      {entry?.data_freshness && (
                        <Badge variant="outline" className="text-[10px]">
                          {entry.data_freshness}
                        </Badge>
                      )}
                      {entry?.fallback_used && (
                        <Badge variant="destructive" className="text-[10px]">
                          fallback
                        </Badge>
                      )}
                    </div>
                    {totalSources > 0 && (
                      <div className="text-[11px] text-muted-foreground">
                        {okCount}/{totalSources} sources ok
                      </div>
                    )}
                    {entry?.error_summary && (
                      <p className="text-[11px] text-destructive truncate" title={entry.error_summary}>
                        {entry.error_summary}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* Source health matrix */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-mono flex items-center gap-2">
              <Database className="h-4 w-4" />
              Source health matrix
            </CardTitle>
          </CardHeader>
          <CardContent>
            {health?.sources?.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-2 font-mono">Source</th>
                      <th className="text-left py-2 font-mono">Agent</th>
                      <th className="text-right py-2 font-mono">Availability</th>
                      <th className="text-right py-2 font-mono">Avg latency</th>
                      <th className="text-left py-2 font-mono">Status</th>
                      <th className="text-left py-2 font-mono">Last error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {health.sources.map((s, i) => (
                      <tr key={i} className="border-b border-border/50">
                        <td className="py-1.5 font-mono text-xs">{s.source}</td>
                        <td className="py-1.5 text-muted-foreground text-xs">{s.agent}</td>
                        <td className="py-1.5 text-right">{s.availability_pct}%</td>
                        <td className="py-1.5 text-right">
                          {s.avg_latency_ms != null ? `${s.avg_latency_ms} ms` : "–"}
                        </td>
                        <td className="py-1.5">
                          <Badge
                            variant={s.status === "ok" ? "secondary" : s.status === "down" ? "destructive" : "outline"}
                            className="text-[10px]"
                          >
                            {s.status}
                            {s.circuit_open ? " (circuit open)" : ""}
                          </Badge>
                        </td>
                        <td className="py-1.5 text-[11px] text-muted-foreground max-w-[200px] truncate" title={s.last_error ?? undefined}>
                          {s.last_error ?? "–"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-muted-foreground text-sm">No source data yet. Run an analysis to populate health.</p>
            )}
            {health?.summary && (
              <p className="text-xs text-muted-foreground mt-2">
                Summary: {health.summary.ok} ok, {health.summary.degraded} degraded, {health.summary.down} down
              </p>
            )}
          </CardContent>
        </Card>

        {/* Run history timeline */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-mono flex items-center gap-2">
              <History className="h-4 w-4" />
              Run history (last 30 runs)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {history.length > 0 ? (
              <div className="h-[240px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={[...history].reverse().map((r) => ({
                      at: r.at,
                      label: new Date(r.at * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }),
                      score: r.escalation_score ?? 0,
                    }))}
                    margin={{ top: 5, right: 10, left: 0, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis dataKey="label" tick={{ fontSize: 10 }} className="text-muted-foreground" />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} className="text-muted-foreground" />
                    <Tooltip
                      content={({ payload }) =>
                        payload?.[0] ? (
                          <div className="rounded bg-card border border-border px-2 py-1 text-xs">
                            Score: {payload[0].payload.score}
                            <br />
                            {new Date(payload[0].payload.at * 1000).toLocaleString()}
                          </div>
                        ) : null
                      }
                    />
                    <Legend />
                    <Line type="monotone" dataKey="score" stroke="hsl(var(--primary))" strokeWidth={1.5} dot={false} name="Escalation score" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-muted-foreground text-sm">No run history yet.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default AgentMonitor;
