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

export function ChatMvpPanel({ conflict }: ChatMvpPanelProps) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ChatAskResponse | null>(null);
  const [feedbackSent, setFeedbackSent] = useState<boolean | null>(null);

  const confidenceLabel = useMemo(() => {
    if (!result) return "";
    return `${Math.round(Math.max(0, Math.min(1, result.confidence_score)) * 100)}%`;
  }, [result]);

  async function onAsk() {
    const q = question.trim();
    if (!q || loading) return;
    setLoading(true);
    setFeedbackSent(null);
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
      setResult(response);
      if (response.fallback_used) {
        toast.info("Answer quality was too low for Chat MVP, so a safe fallback was returned.");
      }
    } catch (e) {
      if (e instanceof TypeError) {
        toast.error("Backend is currently unreachable. Please retry in a few seconds.");
      } else {
        toast.error(e instanceof Error ? e.message : "Chat request failed");
      }
    } finally {
      setLoading(false);
    }
  }

  async function onFeedback(helpful: boolean) {
    if (!result || feedbackSent !== null) return;
    try {
      await postChatFeedback({
        response_id: result.response_id,
        helpful,
      });
      setFeedbackSent(helpful);
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
            onClick={() => setQuestion(item.text)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="space-y-2">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
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

      {result && (
        <div className="space-y-2 rounded border border-border/60 bg-background/40 p-2.5">
          <div className="flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
            <span>{TYPE_LABEL[result.question_type]}</span>
            <span>Confidence: {confidenceLabel}</span>
          </div>
          <p className="text-xs whitespace-pre-wrap">{result.answer}</p>
          <div className="text-[10px] text-muted-foreground">
            Sources: {result.sources.length > 0 ? result.sources.length : 0}
          </div>
          {result.sources.length > 0 && (
            <ul className="space-y-1">
              {result.sources.slice(0, 5).map((src) => (
                <li key={src} className="text-[11px] break-all">
                  <a href={src} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                    {src}
                  </a>
                </li>
              ))}
            </ul>
          )}
          <div className="flex items-center gap-1 pt-1 border-t border-border/60">
            <span className="text-[10px] text-muted-foreground mr-1">Helpful?</span>
            <button
              type="button"
              onClick={() => void onFeedback(true)}
              disabled={feedbackSent !== null}
              aria-label="Helpful"
              className="rounded border border-border p-1 text-muted-foreground hover:text-foreground disabled:opacity-50"
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => void onFeedback(false)}
              disabled={feedbackSent !== null}
              aria-label="Not helpful"
              className="rounded border border-border p-1 text-muted-foreground hover:text-foreground disabled:opacity-50"
            >
              <ThumbsDown className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
