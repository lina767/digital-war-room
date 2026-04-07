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

export async function postChatAsk(body: { question: string; conflict: string }): Promise<ChatAskResponse> {
  const res = await apiFetch(apiUrl("chat/ask"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    timeoutMs: 25_000,
  });
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as ChatAskResponse;
}

export interface ChatFeedbackBody {
  response_id: string;
  conflict: string;
  question: string;
  question_type: ChatQuestionType;
  answer: string;
  confidence_score: number;
  sources: string[];
  helpful: boolean;
  comment?: string;
}

export async function postChatFeedback(body: ChatFeedbackBody): Promise<void> {
  const res = await apiFetch(apiUrl("chat/feedback"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    timeoutMs: 12_000,
  });
  if (!res.ok) throw new Error(await res.text());
}

export interface ChatFeedbackTypeSummary {
  question_type: string;
  count: number;
  helpful_count: number;
  helpful_rate: number;
  avg_confidence: number;
}

export interface ChatFeedbackSummaryResponse {
  status: "ok";
  days: number;
  storage: "database" | "memory";
  total_feedback: number;
  helpful_total: number;
  helpful_rate: number;
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
