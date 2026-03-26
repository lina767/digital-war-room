/**
 * Backend API client — split by domain under this folder; import from `@/lib/api` or `@/lib/api/<domain>`.
 */

export {
  DEFAULT_FETCH_TIMEOUT_MS,
  HttpError,
  getApiBase,
  getAuthHeaders,
  getWsUrl,
  apiUrl,
  apiFetch,
  readJson,
  readJsonOrThrow,
  readOkJson,
  type ApiFetchInit,
} from "./client";

export {
  ANALYSIS_TIMEOUT_MS,
  LATEST_ANALYSIS_TIMEOUT_MS,
  getAnalyzeStatus,
  getEscalationTimeline,
  getLatestAnalysis,
  triggerRefreshAnalysis,
  normalizeAnalysisResponse,
  type AnalyzeResponse,
  type EscalationTimelinePoint,
  type LatestAnalysisResult,
  type ProvenanceIndexEntry,
  type TriggerRefreshResponse,
} from "./analyze";

export {
  newsletterSubscribe,
  newsletterConfirm,
  newsletterUnsubscribe,
} from "./newsletter";

export {
  getComplianceZones,
  postComplianceRouteScreening,
  getDocuments,
  postDocumentsIngest,
  postDocumentsQa,
  type ZonesResponse,
  type RouteScreeningBody,
  type RouteScreeningResult,
  type DocumentItem,
} from "./compliance";

export {
  fetchGreynoiseThreats,
  fetchGreynoiseTrend,
  type GreynoiseEmergingThreat,
  type GreynoiseResult,
  type GreynoiseTopIp,
  type GreynoiseTrendPoint,
  type GreynoiseTrendResponse,
} from "./greynoise";

export type {
  SourceResult,
  ProcessingStep,
  ScoreConfidence,
  AgentMeta,
  AgentsHealthSource,
  AgentsHealthResponse,
  AnalysisRunSummary,
  TokenInOut,
  MonitoringErrorEntry,
  AgentsMonitoringResponse,
  GoogleTrendSerpSnapshot,
  GoogleTrendSerpOrganic,
  GoogleTrendSerpQuota,
  AgentsOpsHeartbeatRow,
  AgentsOpsAgentRow,
  AgentsOpsStatusResponse,
} from "./agents";
export {
  getAgentsHealth,
  getAgentsHistory,
  getAgentsMonitoring,
  getAgentsOpsStatus,
  getAgentsStatus,
  postGoogleTrendSnapshot,
} from "./agents";

export {
  getConflictEvents,
  getTheaterEvents,
  type ConflictEventForHeatmap,
  type TheaterEvent,
} from "./theater";

export { getChokepointOverrides, postChokepointOverrides } from "./chokepoints";
