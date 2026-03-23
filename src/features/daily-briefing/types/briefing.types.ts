export type ThreatLevel = "MINIMAL" | "LOW" | "ELEVATED" | "HIGH" | "CRITICAL";

export type AgentId =
  | "FININT"
  | "SIGINT"
  | "GEOINT"
  | "SOCMINT"
  | "NEWS"
  | "CYBER"
  | "ENERGY"
  | "PROTEST"
  | "DIPLO"
  | "PROXIMITY"
  | "TECHINT"
  | "CHOKEPOINT"
  | "GREYNOISE";

export type ConfidenceLevel = "HIGH" | "MEDIUM" | "LOW";
export type SourceTier = "A" | "B" | "C" | "D";

export interface Finding {
  id: string;
  agent: AgentId;
  type: string;
  title: string;
  body: string;
  confidence: ConfidenceLevel;
  sourceTier: SourceTier;
  timestamp: Date;
  rawData?: Record<string, unknown>;
  sourceUrls?: string[];
}

export type ScenarioType = "ESCALATION" | "DE_ESCALATION" | "STATUS_QUO" | "WILDCARD";

export interface Scenario {
  id: string;
  type: ScenarioType;
  probability: number;
  description: string;
  keyDrivers: { agent: AgentId; reason: string }[];
  timeHorizon?: string;
}

export interface EscalationSignal {
  label: string;
  weight: number;
  agent: AgentId;
}

export interface PricePoint {
  label: string;
  value: number;
  changePct: number;
}

export interface StockPoint {
  symbol: string;
  value: number;
  changePct: number;
}

export interface PolymarketOdds {
  question: string;
  yesProbability: number;
}

export interface ChokepointStatus {
  name: string;
  status: "NORMAL" | "RESTRICTED" | "HOSTILE";
  trafficChangePct: number;
  disruptionScore: number;
}

export interface AgentStatus {
  agent: AgentId;
  status: "success" | "running" | "error" | "timeout" | "disabled";
  score: number | null;
  lastUpdated: Date | null;
  error?: string;
  latencyMs?: number;
}

export interface AgentSource {
  name: string;
  tier: SourceTier;
}

export interface AgentModelMeta {
  model: string;
  tokensUsed: number;
  latencyMs: number;
  sources: AgentSource[];
}

export interface AgentDataBlock {
  status: AgentStatus;
  findings: Finding[];
  rawData: unknown;
  metadata: AgentModelMeta;
}

export interface DailyBriefingData {
  conflict: string;
  threatLevel: ThreatLevel;
  escalationScore: number;
  bluf: string;
  keyFindings: Finding[];
  scenarios: Scenario[];
  predictiveOutlook: {
    trajectory: "ESCALATING" | "STABLE" | "DE_ESCALATING";
    signals: EscalationSignal[];
  };
  agents: Record<AgentId, AgentDataBlock>;
  market: {
    brent: PricePoint | null;
    wti: PricePoint | null;
    gold: PricePoint | null;
    defenseStocks: StockPoint[];
    polymarket: PolymarketOdds[];
  };
  chokepoints: ChokepointStatus[];
  generatedAt: Date;
  version: string;
}

export type BriefingConnectionStatus = "connecting" | "connected" | "analyzing" | "disconnected" | "error";

export interface BriefingState {
  data: DailyBriefingData | null;
  connectionStatus: BriefingConnectionStatus;
  expandedAgents: Set<AgentId>;
  expandedFindings: Set<string>;
  lastUpdated: Date | null;
  isExporting: boolean;
  isLoading: boolean;
  error: string | null;
  fromCache: boolean;
}

export type BriefingAction =
  | { type: "LOAD_START" }
  | { type: "DATA_RECEIVED"; payload: { data: DailyBriefingData; fromCache: boolean } }
  | { type: "LOAD_ERROR"; payload: string }
  | { type: "CONNECTION_STATUS"; payload: BriefingConnectionStatus }
  | { type: "TOGGLE_AGENT"; payload: AgentId }
  | { type: "TOGGLE_FINDING"; payload: string }
  | { type: "EXPORT_START" }
  | { type: "EXPORT_COMPLETE" };
