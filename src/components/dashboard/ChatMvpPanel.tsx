import { useMemo, useState } from "react";
import { MessageCircle, ThumbsDown, ThumbsUp } from "lucide-react";
import { toast } from "sonner";
import { postChatAsk, postChatFeedback, type ChatAskResponse, type ChatQuestionType } from "@/lib/api/chat";
import { getAnalyzeStatus, triggerRefreshAnalysis } from "@/lib/api/analyze";

const QUICK_PROMPTS: Array<{ label: string; text: string }> = [
  { label: "Situation", text: "Give me a concise situation overview for this conflict." },
  { label: "Risk", text: "What are the top risk drivers right now?" },
  { label: "Since yesterday", text: "What changed since yesterday?" },
  { label: "Next 24h", text: "What should we watch in the next 24 hours?" },
  { label: "Sources", text: "What are the strongest supporting sources for this assessment?" },
];

const TYPE_LABEL: Record<ChatQuestionType, string> = {
  situation_overview: "Situation overview",
  risk_assessment: "Risk assessment",
  changes_since_yesterday: "Changes since yesterday",
  next_24h_outlook: "Next 24h outlook",
  source_check: "Source check",
};

interface ChatMvpPanelProps {
  conflict: string;
}

interface ChatTurn {
  id: string;
  question: string;
  loading: boolean;
  result: ChatAskResponse | null;
  error: string | null;
  feedbackSent: boolean | null;
}

const MAX_TURNS = 8;

function confidenceBadge(score: number): "Low" | "Medium" | "High" {
  if (score >= 0.7) return "High";
  if (score >= 0.45) return "Medium";
  return "Low";
}

function sourceLabel(url: string): string {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace(/^www\./, "");
    const path = parsed.pathname === "/" ? "" : parsed.pathname.slice(0, 24);
    return `${host}${path}${parsed.pathname.length > 24 ? "..." : ""}`;
  } catch {
    return url;
  }
}

function createTurnId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `turn-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function ChatMvpPanel({ conflict }: ChatMvpPanelProps) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [sendPromptDirectly, setSendPromptDirectly] = useState(false);
  const [turns, setTurns] = useState<ChatTurn[]>([]);

  const turnsView = useMemo(() => turns.slice(-MAX_TURNS).reverse(), [turns]);

  async function onAsk(rawQuestion?: string) {
    const q = (rawQuestion ?? question).trim();
    if (!q || loading) return;
    setLoading(true);
    const turnId = createTurnId();
    setTurns((prev) => [...prev, { id: turnId, question: q, loading: true, result: null, error: null, feedbackSent: null }].slice(-MAX_TURNS));
    if (!rawQuestion) setQuestion("");
    try {
      const status = await getAnalyzeStatus(conflict);
      if (status && !status.cached) {
        try {
          await triggerRefreshAnalysis(conflict);
        } catch {
          // If already running or temporarily unavailable, keep a clear user hint.
        }
        if (status.running) {
          toast.info("Analysis is warming up. I'll still try to answer with currently available cache.");
        } else {
          toast.info("Analysis was started in background. I'll still try to answer now.");
        }
      }
      const response = await postChatAsk({ question: q, conflict });
      setTurns((prev) =>
        prev.map((t) => (t.id === turnId ? { ...t, loading: false, result: response, error: null, feedbackSent: null } : t)),
      );
      if (response.fallback_used) {
        toast.info("Answer quality was too low for Chat MVP, so a safe fallback was returned.");
      }
    } catch (e) {
      const message =
        e instanceof TypeError
          ? "Backend is currently unreachable. Please retry in a few seconds."
          : e instanceof Error
            ? e.message
            : "Chat request failed";
      setTurns((prev) => prev.map((t) => (t.id === turnId ? { ...t, loading: false, error: message } : t)));
      if (e instanceof TypeError) {
        toast.error("Backend is currently unreachable. Please retry in a few seconds.");
      } else {
        toast.error(e instanceof Error ? e.message : "Chat request failed");
      }
    } finally {
      setLoading(false);
    }
  }

  async function onFeedback(turnId: string, helpful: boolean) {
    const turn = turns.find((t) => t.id === turnId);
    if (!turn?.result || turn.feedbackSent !== null) return;
    try {
      await postChatFeedback({
        response_id: turn.result.response_id,
        helpful,
      });
      setTurns((prev) => prev.map((t) => (t.id === turnId ? { ...t, feedbackSent: helpful } : t)));
      toast.success("Thanks, feedback saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Feedback failed");
    }
  }

  return (
    <section className="rounded-lg border border-border bg-card/40 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <MessageCircle className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
        <h3 className="font-mono text-[11px] text-muted-foreground tracking-wider">CHAT MVP</h3>
      </div>
      <p className="text-xs text-muted-foreground">
        Ask in any language. Answers are returned in English with confidence and sources.
      </p>
      <div className="flex flex-wrap gap-1">
        {QUICK_PROMPTS.map((item) => (
          <button
            key={item.label}
            type="button"
            className="rounded border border-border px-2 py-1 text-[11px] font-mono text-muted-foreground hover:text-foreground hover:bg-muted/30"
            onClick={() => {
              setQuestion(item.text);
              if (sendPromptDirectly) {
                void onAsk(item.text);
              }
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      <label className="flex items-center gap-2 text-[10px] text-muted-foreground">
        <input
          type="checkbox"
          checked={sendPromptDirectly}
          onChange={(e) => setSendPromptDirectly(e.target.checked)}
          className="h-3 w-3 rounded border-border bg-background"
        />
        Send quick prompts directly
      </label>
      <div className="space-y-2">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void onAsk();
            }
          }}
          placeholder="Ask about current situation, risks, changes, or evidence…"
          rows={3}
          className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs resize-y min-h-[64px]"
        />
        <button
          type="button"
          onClick={onAsk}
          disabled={loading || !question.trim()}
          className="rounded border border-border bg-primary/10 px-2 py-1 text-xs font-mono hover:bg-primary/20 disabled:opacity-50"
        >
          {loading ? "Asking…" : "Ask"}
        </button>
      </div>

      <div className="space-y-2 max-h-[380px] overflow-auto pr-1">
        {turnsView.map((turn) => {
          const result = turn.result;
          const confidence = result ? `${Math.round(Math.max(0, Math.min(1, result.confidence_score)) * 100)}%` : "";
          return (
            <div key={turn.id} className="space-y-2 rounded border border-border/60 bg-background/40 p-2.5">
              <p className="text-xs font-medium">{turn.question}</p>
              {turn.loading && <p className="text-xs text-muted-foreground">Asking...</p>}
              {turn.error && <p className="text-xs text-destructive">{turn.error}</p>}
              {result && (
                <>
                  <div className="flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
                    <span>{TYPE_LABEL[result.question_type]}</span>
                    <span>
                      Confidence: {confidence} ({confidenceBadge(result.confidence_score)})
                    </span>
                  </div>
                  <p className="text-xs whitespace-pre-wrap">{result.answer}</p>
                  <div className="text-[10px] text-muted-foreground">Sources: {result.sources.length}</div>
                  {result.sources.length > 0 && (
                    <ul className="space-y-1">
                      {result.sources.slice(0, 5).map((src) => (
                        <li key={src} className="text-[11px] break-all">
                          <a href={src} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                            {sourceLabel(src)}
                          </a>
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="flex items-center gap-1 pt-1 border-t border-border/60">
                    <span className="text-[10px] text-muted-foreground mr-1">Helpful?</span>
                    <button
                      type="button"
                      onClick={() => void onFeedback(turn.id, true)}
                      disabled={turn.feedbackSent !== null}
                      aria-label="Helpful"
                      className="rounded border border-border p-1 text-muted-foreground hover:text-foreground disabled:opacity-50"
                    >
                      <ThumbsUp className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => void onFeedback(turn.id, false)}
                      disabled={turn.feedbackSent !== null}
                      aria-label="Not helpful"
                      className="rounded border border-border p-1 text-muted-foreground hover:text-foreground disabled:opacity-50"
                    >
                      <ThumbsDown className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
