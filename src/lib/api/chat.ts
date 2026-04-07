import { apiFetch, apiUrl } from "./client";

export type ChatQuestionType =
  | "situation_overview"
  | "risk_assessment"
  | "changes_since_yesterday"
  | "next_24h_outlook"
  | "source_check";

export interface ChatAskResponse {
  response_id: string;
  question_type: ChatQuestionType;
  answer: string;
  confidence_score: number;
  sources: string[];
  fallback_used: boolean;
}

async function toApiError(res: Response, fallback: string): Promise<Error> {
  let text = "";
  try {
    text = await res.text();
  } catch {
    return new Error(fallback);
  }
  if (!text.trim()) return new Error(fallback);
  try {
    const parsed = JSON.parse(text) as { detail?: unknown; error?: unknown; message?: unknown };
    const detail = parsed?.detail;
    if (typeof detail === "string" && detail.trim()) return new Error(detail.trim());
    if (detail && typeof detail === "object") {
      const status = "status" in detail ? String((detail as Record<string, unknown>).status ?? "").trim() : "";
      if (status) return new Error(status);
    }
    const alt = [parsed?.error, parsed?.message].find((x) => typeof x === "string" && x.trim()) as string | undefined;
    if (alt) return new Error(alt.trim());
  } catch {
    // Fall through to plaintext handling.
  }
  return new Error(text.trim() || fallback);
}

export async function postChatAsk(body: { question: string; conflict: string }): Promise<ChatAskResponse> {
  try {
    const res = await apiFetch(apiUrl("chat/ask"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      timeoutMs: 25_000,
    });
    if (!res.ok) throw await toApiError(res, `Chat request failed (HTTP ${res.status})`);
    return (await res.json()) as ChatAskResponse;
  } catch (e) {
    if (e instanceof Error) throw e;
    throw new Error("Chat request failed");
  }
}

export interface ChatFeedbackBody {
  response_id: string;
  helpful: boolean;
  comment?: string;
}

export async function postChatFeedback(body: ChatFeedbackBody): Promise<void> {
  try {
    const res = await apiFetch(apiUrl("chat/feedback"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      timeoutMs: 12_000,
    });
    if (!res.ok) throw await toApiError(res, `Feedback failed (HTTP ${res.status})`);
  } catch (e) {
    if (e instanceof Error) throw e;
    throw new Error("Feedback request failed");
  }
}

export interface ChatFeedbackTypeSummary {
  question_type: string;
  count: number;
  helpful_count: number;
  helpful_rate: number;
  avg_confidence: number;
  fallback_count?: number;
  fallback_rate?: number;
}

export interface ChatFeedbackSummaryResponse {
  status: "ok";
  days: number;
  storage: "database" | "memory";
  total_feedback: number;
  helpful_total: number;
  helpful_rate: number;
  fallback_total?: number;
  fallback_rate?: number;
  by_question_type: ChatFeedbackTypeSummary[];
  trend_days: Array<{
    day: string;
    count: number;
    helpful_count: number;
    helpful_rate: number;
  }>;
}

export async function getChatFeedbackSummary(days = 7): Promise<ChatFeedbackSummaryResponse | null> {
  try {
    const res = await apiFetch(apiUrl("chat/feedback/summary", { days }), {
      method: "GET",
      timeoutMs: 12_000,
    });
    if (!res.ok) return null;
    return (await res.json()) as ChatFeedbackSummaryResponse;
  } catch {
    return null;
  }
}
