import { useRef, useState } from "react";
import { MessageCircle } from "lucide-react";
import { getApiBase } from "@/lib/api";
import { DEFAULT_CONFLICT } from "@/components/dashboard/conflictData";
import { DOC_QA_DISCLAIMER, DOC_QA_INTRO, DOC_QA_PLACEHOLDER } from "@/lib/complianceCopy";
import type { ConflictData } from "@/hooks/useConflictWebSocket";
import type { DocumentQAResponse } from "./shared";

export function DocumentQASection({ data }: { data: ConflictData | null }) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DocumentQAResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  function buildContext() {
    const c = data?.compliance;
    if (!c) return undefined;
    const sample = c.ofac_sdn?.sample ?? [];
    const ofacSample: string[] = sample
      .map((s: { name?: string; type?: string; program?: string }) => {
        const name = s.name?.trim();
        if (!name) return "";
        const type = s.type;
        const program = s.program;
        if (type || program) return `${name} (${[type, program].filter(Boolean).join(", ")})`;
        return name;
      })
      .filter(Boolean);
    const programs = c.ofac_sdn?.programs ?? [];
    const ofacProgramsSummary =
      programs.length > 0
        ? programs.slice(0, 12).map((p: { name?: string; count?: number }) => `${p.name ?? "?"} (${p.count ?? 0})`).join(", ")
        : undefined;
    const riskLevel = c.risk_score?.level;
    const drivers = c.risk_score?.drivers ?? [];
    const riskDriversSummary =
      drivers.length > 0 ? drivers.slice(0, 6).map((d) => `${d.factor}: ${d.detail}`).join("; ") : undefined;
    return {
      ofac_sample: ofacSample.length > 0 ? ofacSample : undefined,
      ofac_programs_summary: ofacProgramsSummary,
      risk_level: riskLevel ?? undefined,
      risk_drivers_summary: riskDriversSummary,
    };
  }

  async function handleAsk() {
    if (!question.trim()) return;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const base = getApiBase();
      const resp = await fetch(`${base}/api/compliance/document-qa`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          conflict: data?.conflict ?? DEFAULT_CONFLICT,
          context: buildContext(),
        }),
        signal: abortRef.current.signal,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json: DocumentQAResponse = await resp.json();
      setResult(json);
    } catch (err: unknown) {
      if ((err as Error).name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-2">
      <span className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
        <MessageCircle className="h-3 w-3" />
        Ask about sanctions documents
      </span>
      <p className="text-[11px] text-muted-foreground">{DOC_QA_INTRO}</p>
      <div className="flex flex-col gap-1.5">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={DOC_QA_PLACEHOLDER}
          rows={2}
          aria-label="Question about current compliance context"
          className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary resize-y min-h-[48px]"
        />
        <button
          type="button"
          onClick={handleAsk}
          disabled={loading || !question.trim()}
          aria-label="Ask question about compliance context"
          className="self-start rounded border border-border bg-primary/10 px-2 py-1 text-xs font-mono hover:bg-primary/20 disabled:opacity-50"
        >
          {loading ? "…" : "Ask"}
        </button>
      </div>
      {error && (
        <div className="flex items-center gap-2">
          <p className="text-[11px] text-destructive">{error}</p>
          <button type="button" onClick={handleAsk} className="text-[11px] text-primary hover:underline">
            Retry
          </button>
        </div>
      )}
      {result && (
        <div className="rounded border border-border bg-background/50 px-2.5 py-1.5 space-y-1">
          <p className="text-[11px] text-foreground whitespace-pre-wrap">{result.answer}</p>
          {result.confidence != null && result.confidence > 0 && (
            <p className="text-[10px] text-muted-foreground">Confidence: {Math.round(result.confidence * 100)}%</p>
          )}
          <p className="text-[10px] text-muted-foreground/80 border-t border-border/50 pt-1">
            {result.disclaimer ?? DOC_QA_DISCLAIMER}
          </p>
        </div>
      )}
    </div>
  );
}
