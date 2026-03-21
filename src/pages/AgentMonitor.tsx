import { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  getAgentsStatus,
  getAgentsHealth,
  getAgentsHistory,
  getAgentsMonitoring,
  getAnalyzeStatus,
  triggerRefreshAnalysis,
  type AgentsHealthResponse,
  type AgentsMonitoringResponse,
  type AnalysisRunSummary,
  type MonitoringErrorEntry,
} from "@/lib/api";
import { DEFAULT_CONFLICT } from "@/components/dashboard/conflictData";
import { AGENT_NAME_TO_KEY } from "@/components/dashboard/agentsConfig";
import { toast } from "sonner";
import {
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
  Layers,
  ScrollText,
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

function formatErrorTime(ts: number): string {
  try {
    return new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "short", timeStyle: "medium" });
  } catch {
    return "—";
  }
}

function formatRelativeTime(iso?: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const now = Date.now();
    const diff = (now - d.getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return "—";
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runAgainLoading, setRunAgainLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const fetchAll = useCallback(async () => {
    setError(null);
    try {
      const [statusRes, healthRes, historyRes, monRes] = await Promise.all([
        getAgentsStatus(),
        getAgentsHealth(),
        getAgentsHistory(30),
        getAgentsMonitoring(),
      ]);
      if (statusRes && typeof statusRes === "object") setStatus(statusRes as Record<string, AgentStatusEntry>);
      if (healthRes) setHealth(healthRes);
      if (historyRes?.runs) setHistory(historyRes.runs);
      if (monRes) setMonitoring(monRes);
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
      const [statusRes, healthRes, historyRes, monRes] = await Promise.all([
        getAgentsStatus(),
        getAgentsHealth(),
        getAgentsHistory(30),
        getAgentsMonitoring(),
      ]);
      if (statusRes && typeof statusRes === "object") setStatus(statusRes as Record<string, AgentStatusEntry>);
      if (healthRes) setHealth(healthRes);
      if (historyRes?.runs) setHistory(historyRes.runs);
      if (monRes) setMonitoring(monRes);
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
                        {monitoring.fallback.last_run.conflict}: {monitoring.fallback.last_run.count} agent(s) —{" "}
                        {monitoring.fallback.last_run.agents.join(", ") || "—"}
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
                    <p className="text-[11px] font-mono text-muted-foreground mb-1">Last run — tokens by tag</p>
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
                    <p className="text-[11px] font-mono text-muted-foreground mb-1">Month — tokens by tag</p>
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
                          {s.avg_latency_ms != null ? `${s.avg_latency_ms} ms` : "—"}
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
                          {s.last_error ?? "—"}
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
