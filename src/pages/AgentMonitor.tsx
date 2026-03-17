import { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  getApiBase,
  getAgentsHealth,
  getAgentsHistory,
  getAnalyzeStatus,
  triggerRefreshAnalysis,
  type AgentsHealthResponse,
  type AnalysisRunSummary,
} from "@/lib/api";
import { AGENT_NAME_TO_KEY } from "@/components/dashboard/agentsConfig";
import { toast } from "sonner";
import { ArrowLeft, AlertTriangle, Activity, Clock, Database, History, Play, RefreshCw } from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
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

const DEFAULT_CONFLICT = "Iran";
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runAgainLoading, setRunAgainLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const fetchAll = useCallback(async () => {
    setError(null);
    try {
      const [statusRes, healthRes, historyRes] = await Promise.all([
        fetch(`${getApiBase()}/api/agents/status`).then((r) => (r.ok ? r.json() : null)),
        getAgentsHealth(),
        getAgentsHistory(30),
      ]);
      if (statusRes && typeof statusRes === "object") setStatus(statusRes as Record<string, AgentStatusEntry>);
      if (healthRes) setHealth(healthRes);
      if (historyRes?.runs) setHistory(historyRes.runs);
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
      const [statusRes, healthRes, historyRes] = await Promise.all([
        fetch(`${getApiBase()}/api/agents/status`).then((r) => (r.ok ? r.json() : null)),
        getAgentsHealth(),
        getAgentsHistory(30),
      ]);
      if (statusRes && typeof statusRes === "object") setStatus(statusRes as Record<string, AgentStatusEntry>);
      if (healthRes) setHealth(healthRes);
      if (historyRes?.runs) setHistory(historyRes.runs);
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

  if (loading && !status) {
    return (
      <div className="min-h-screen bg-background text-foreground p-6">
        <div className="max-w-6xl mx-auto flex items-center justify-center min-h-[200px]">
          <p className="text-muted-foreground">Loading monitoring data…</p>
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
                <ArrowLeft className="h-4 w-4" />
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
                <Play className="h-3.5 w-3.5" />
                {runAgainLoading ? "Running…" : "Run analysis again"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={refreshMonitor}
                disabled={refreshing || runAgainLoading}
                className="gap-1.5"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
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
