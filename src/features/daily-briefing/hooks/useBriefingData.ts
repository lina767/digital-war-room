import { useEffect, useMemo, useReducer } from "react";
import { DEFAULT_CONFLICT } from "@/lib/conflictDefaults";
import type { ConflictData, PredictiveLevel } from "@/types/conflict";
import { useConflictWebSocket } from "@/hooks/useConflictWebSocket";
import { formatTimeAgo } from "@/lib/utils";
import { AGENT_ORDER } from "@/features/daily-briefing/constants/agents";
import type {
  AgentDataBlock,
  AgentId,
  AgentStatus,
  BriefingAction,
  BriefingState,
  ChokepointStatus,
  DailyBriefingData,
  EscalationSignal,
  Finding,
  Scenario,
  ThreatLevel,
} from "@/features/daily-briefing/types/briefing.types";
import { normalizeConfidence } from "@/features/daily-briefing/utils/confidenceLabel";

const INITIAL_STATE: BriefingState = {
  data: null,
  connectionStatus: "connecting",
  expandedAgents: new Set<AgentId>(),
  expandedFindings: new Set<string>(),
  lastUpdated: null,
  isExporting: false,
  isLoading: true,
  error: null,
  fromCache: false,
};

function reducer(state: BriefingState, action: BriefingAction): BriefingState {
  switch (action.type) {
    case "LOAD_START":
      return { ...state, isLoading: true, error: null };
    case "DATA_RECEIVED":
      return {
        ...state,
        data: action.payload.data,
        fromCache: action.payload.fromCache,
        isLoading: false,
        error: null,
        lastUpdated: action.payload.data.generatedAt,
      };
    case "LOAD_ERROR":
      return { ...state, isLoading: false, error: action.payload };
    case "CONNECTION_STATUS":
      return { ...state, connectionStatus: action.payload };
    case "TOGGLE_AGENT": {
      const next = new Set(state.expandedAgents);
      if (next.has(action.payload)) next.delete(action.payload);
      else next.add(action.payload);
      return { ...state, expandedAgents: next };
    }
    case "TOGGLE_FINDING": {
      const next = new Set(state.expandedFindings);
      if (next.has(action.payload)) next.delete(action.payload);
      else next.add(action.payload);
      return { ...state, expandedFindings: next };
    }
    case "EXPORT_START":
      return { ...state, isExporting: true };
    case "EXPORT_COMPLETE":
      return { ...state, isExporting: false };
    default:
      return state;
  }
}

function parseThreatLevel(value: string | null | undefined): ThreatLevel {
  const v = (value ?? "").toUpperCase();
  if (v === "CRITICAL" || v === "HIGH" || v === "ELEVATED" || v === "LOW" || v === "MINIMAL") return v;
  return "ELEVATED";
}

function parsePrice(raw: unknown, label: string): { label: string; value: number; changePct: number } | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as { price?: string | number; change_pct?: string | number };
  const value = Number(r.price ?? 0);
  const changePct = Number(String(r.change_pct ?? "0").replace("%", ""));
  if (!Number.isFinite(value)) return null;
  return { label, value, changePct: Number.isFinite(changePct) ? changePct : 0 };
}

function toScenarioType(description: string): Scenario["type"] {
  const d = description.toLowerCase();
  if (d.includes("de-escal")) return "DE_ESCALATION";
  if (d.includes("status quo")) return "STATUS_QUO";
  if (d.includes("wildcard")) return "WILDCARD";
  return "ESCALATION";
}

function levelToWeight(level: PredictiveLevel | undefined): number {
  switch (level) {
    case "CRITICAL":
      return 92;
    case "HIGH":
      return 78;
    case "MEDIUM":
      return 55;
    case "LOW":
      return 38;
    default:
      return 50;
  }
}

function buildPredictiveOutlook(conflict: ConflictData, escalationScore: number): DailyBriefingData["predictiveOutlook"] {
  const baseline = conflict.predictive?.baseline_escalation;
  const esc = conflict.predictive?.escalation?.[0];

  let trajectory: DailyBriefingData["predictiveOutlook"]["trajectory"] = "STABLE";
  if (baseline?.vs_baseline === "higher") trajectory = "ESCALATING";
  else if (baseline?.vs_baseline === "lower") trajectory = "DE_ESCALATING";
  else if (baseline?.vs_baseline === "similar") {
    if (escalationScore >= 65) trajectory = "ESCALATING";
    else if (escalationScore <= 35) trajectory = "DE_ESCALATING";
    else trajectory = "STABLE";
  } else {
    if (escalationScore >= 65) trajectory = "ESCALATING";
    else if (escalationScore <= 35) trajectory = "DE_ESCALATING";
  }

  const signals: EscalationSignal[] = [];
  const push = (label: string, weight: number, agent: AgentId) => {
    if (!label.trim()) return;
    signals.push({ label: label.slice(0, 120), weight: Math.min(100, Math.max(0, Math.round(weight))), agent });
  };

  push("Composite escalation score", escalationScore, "NEWS");
  baseline?.drivers?.slice(0, 2).forEach((d, i) => {
    push(d, escalationScore * (0.88 - i * 0.08), "SIGINT");
  });
  if (esc?.horizon && esc.level) {
    push(`Predicted stress (${esc.horizon})`, levelToWeight(esc.level), "FININT");
  }
  const maxCpRisk = Math.max(
    0,
    ...(conflict.chokepoint?.chokepoints ?? []).map((c) => Number(c.disruption_risk ?? 0)),
  );
  if (maxCpRisk > 35) {
    push("Chokepoint disruption risk", Math.round(maxCpRisk), "CHOKEPOINT");
  }
  const newsScore = conflict.news?.news_score;
  if (typeof newsScore === "number" && Number.isFinite(newsScore)) {
    push("News stream intensity", Math.min(100, Math.round(newsScore)), "NEWS");
  }
  conflict.pattern_flags?.slice(0, 2).forEach((pf, i) => {
    const title = (pf.title ?? pf.detail ?? "").trim();
    if (title) push(title, Math.min(100, escalationScore + 5 + i * 3), "SIGINT");
  });

  return { trajectory, signals: signals.slice(0, 5) };
}

function agentScore(conflict: ConflictData, agent: AgentId): number | null {
  const map: Partial<Record<AgentId, number | undefined>> = {
    FININT: Number((conflict.finint as { finint_score?: number } | undefined)?.finint_score ?? NaN),
    SIGINT: conflict.sigint?.sigint_score,
    GEOINT: conflict.geoint?.geoint_score,
    CYBER: conflict.cyber?.cyber_score,
    ENERGY: conflict.energy?.energy_score,
    PROTEST: conflict.protest?.protest_score,
    DIPLO: conflict.diplo?.diplo_score,
    PROXIMITY: conflict.proximity?.proximity_score,
    CHOKEPOINT: conflict.chokepoint?.chokepoint_score,
  };
  const v = map[agent];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function inferAgentStatus(conflict: ConflictData, agent: AgentId): AgentStatus["status"] {
  const degraded = conflict.degraded_agents?.includes(agent.toLowerCase()) || false;
  if (degraded) return "timeout";
  const score = agentScore(conflict, agent);
  if (score == null) return "disabled";
  return "success";
}

function toSourceTier(confidence: string | undefined): "A" | "B" | "C" | "D" {
  const c = (confidence ?? "").toLowerCase();
  if (c === "live") return "A";
  if (c === "estimated") return "B";
  if (c === "degraded") return "C";
  return "D";
}

function buildAgentBlock(conflict: ConflictData, agent: AgentId, generatedAt: Date): AgentDataBlock {
  const key = agent.toLowerCase();
  const raw = (conflict as Record<string, unknown>)[key];
  const status: AgentStatus = {
    agent,
    status: inferAgentStatus(conflict, agent),
    score: agentScore(conflict, agent),
    lastUpdated: generatedAt,
    latencyMs: undefined,
    error: undefined,
  };
  const findings: Finding[] = [];
  const meta = (raw && typeof raw === "object" ? (raw as { _meta?: { duration_ms?: number; agent?: string } })._meta : null) ?? null;
  return {
    status: { ...status, latencyMs: meta?.duration_ms ?? undefined },
    findings,
    rawData: raw ?? {},
    metadata: {
      model: "claude-sonnet-supervisor",
      tokensUsed: 0,
      latencyMs: meta?.duration_ms ?? 0,
      sources: [
        {
          name: `${agent} pipeline`,
          tier: toSourceTier(conflict.agent_data_confidence?.[agent.toLowerCase()]),
        },
      ],
    },
  };
}

function toDailyBriefingData(conflict: ConflictData, generatedAt: Date): DailyBriefingData {
  const escalationRounded = Math.round(Number(conflict.escalation_score ?? 0));
  const keyFindings: Finding[] = (conflict.key_findings ?? []).slice(0, 8).map((item, idx) => {
    const text = String(item ?? "");
    const confidence = normalizeConfidence(conflict.key_findings_confidence?.[idx]);
    const context = conflict.key_findings_context?.[idx];
    return {
      id: `finding-${idx + 1}`,
      agent: "NEWS",
      type: "Supervisor synthesis",
      title: text.split(".")[0] || `Finding ${idx + 1}`,
      body: context || text,
      confidence,
      sourceTier: "B",
      timestamp: generatedAt,
      rawData: { index: idx },
      sourceUrls: [],
    };
  });

  const scenarios: Scenario[] = (conflict.scenarios ?? []).slice(0, 4).map((s, idx) => ({
    id: `scenario-${idx + 1}`,
    type: toScenarioType(s.description),
    probability: Math.round((s.probability ?? 0) * 100),
    description: s.description,
    keyDrivers: [
      { agent: "SIGINT", reason: "Movement and pattern deviation" },
      { agent: "NEWS", reason: "Headline and narrative momentum" },
    ],
    timeHorizon: idx === 0 ? "24h" : "72h",
  }));

  const chokepoints: ChokepointStatus[] = (conflict.chokepoint?.chokepoints ?? []).slice(0, 3).map((c) => ({
    name: c.name,
    status: c.status === "OPEN" ? "NORMAL" : c.status === "RESTRICTED" ? "RESTRICTED" : "HOSTILE",
    trafficChangePct: Number(c.brent_impact_pct ?? 0),
    disruptionScore: Math.round(c.disruption_risk ?? 0),
  }));

  const agents = AGENT_ORDER.reduce<Record<AgentId, AgentDataBlock>>((acc, agent) => {
    acc[agent] = buildAgentBlock(conflict, agent, generatedAt);
    return acc;
  }, {} as Record<AgentId, AgentDataBlock>);

  const rawUri = (conflict as { _newsletter_infographic_data_uri?: string })._newsletter_infographic_data_uri;
  const infographicUri =
    typeof rawUri === "string" && rawUri.startsWith("data:image/") ? rawUri : null;

  return {
    conflict: conflict.conflict || DEFAULT_CONFLICT,
    threatLevel: parseThreatLevel(conflict.threat_level),
    escalationScore: escalationRounded,
    bluf: conflict.summary ?? "No executive summary available.",
    newsletterInfographicDataUri: infographicUri,
    keyFindings,
    scenarios,
    predictiveOutlook: buildPredictiveOutlook(conflict, escalationRounded),
    agents,
    market: {
      brent: parsePrice(conflict.finint?.brent, "Brent"),
      wti: parsePrice((conflict.energy?.commodities ?? []).find((c) => c.symbol === "WTI"), "WTI"),
      gold: parsePrice((conflict.energy?.commodities ?? []).find((c) => c.symbol === "XAUUSD"), "Gold"),
      defenseStocks: [],
      polymarket: (conflict.finint?.polymarket ?? []).slice(0, 1).map((p) => ({
        question: p.question ?? "Conflict escalation",
        yesProbability: Math.round(Number(p.probability ?? 0)),
      })),
    },
    chokepoints,
    globalImpactNote: conflict.energy?.global_impact_note ?? null,
    generatedAt,
    version: "v2.4.1",
  };
}

export function useBriefingData(conflict = DEFAULT_CONFLICT) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const ws = useConflictWebSocket({ conflict, enabled: true });

  const mappedBriefing = useMemo(() => {
    if (!ws.data) return null;
    const generatedAt = ws.lastUpdated ?? new Date();
    return toDailyBriefingData(ws.data, generatedAt);
  }, [ws.data, ws.lastUpdated]);

  useEffect(() => {
    dispatch({ type: "CONNECTION_STATUS", payload: ws.status });
  }, [ws.status]);

  useEffect(() => {
    dispatch({ type: "LOAD_START" });
  }, [conflict]);

  useEffect(() => {
    if (!mappedBriefing) return;
    dispatch({ type: "DATA_RECEIVED", payload: { data: mappedBriefing, fromCache: ws.dataFromCache } });
  }, [mappedBriefing, ws.dataFromCache]);

  useEffect(() => {
    if (!ws.analysisError) return;
    dispatch({ type: "LOAD_ERROR", payload: ws.analysisError });
  }, [ws.analysisError]);

  const meta = useMemo(() => {
    return {
      isLive: state.connectionStatus === "connected" || state.connectionStatus === "analyzing",
      lastUpdatedLabel: formatTimeAgo(state.lastUpdated),
      runAnalysis: ws.runAnalysis,
      refresh: ws.refresh,
      initialLoadPending: ws.initialLoadPending,
    };
  }, [state.connectionStatus, state.lastUpdated, ws.runAnalysis, ws.refresh, ws.initialLoadPending]);

  return { state, dispatch, meta };
}
