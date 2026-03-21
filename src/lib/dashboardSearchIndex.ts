import type { ConflictData } from "@/hooks/useConflictWebSocket";

export type SearchCategory = "finding" | "headline" | "agent";

export interface SearchHit {
  id: string;
  category: SearchCategory;
  title: string;
  snippet: string;
  meta?: string;
  url?: string;
  agentLabel?: string;
}

const MAX_BUILT = 400;
const SNIP = 220;

function clip(s: string, n = SNIP): string {
  const t = s.replace(/\s+/g, " ").trim();
  if (t.length <= n) return t;
  return `${t.slice(0, n - 1)}…`;
}

function pushAgent(
  hits: SearchHit[],
  id: string,
  agentLabel: string,
  text: string | null | undefined,
  meta?: string,
) {
  if (!text || typeof text !== "string") return;
  const t = text.trim();
  if (!t) return;
  hits.push({
    id,
    category: "agent",
    title: agentLabel,
    snippet: clip(t),
    meta,
    agentLabel,
  });
}

/** Build a flat list of searchable items from current conflict analysis. */
export function buildSearchHits(data: ConflictData | null): SearchHit[] {
  if (!data) return [];
  const hits: SearchHit[] = [];

  const findings = data.key_findings ?? [];
  for (let i = 0; i < findings.length && hits.length < MAX_BUILT; i++) {
    const f = findings[i];
    const ctx = data.key_findings_context?.[i];
    const combined = ctx ? `${f}\n${ctx}` : f;
    hits.push({
      id: `finding-${i}`,
      category: "finding",
      title: clip(f, 80),
      snippet: clip(combined),
      meta: "Key finding",
    });
  }

  (data.scenarios ?? []).forEach((s, i) => {
    if (s.description) {
      hits.push({
        id: `scenario-${i}`,
        category: "finding",
        title: `Scenario ${i + 1} (${Math.round((s.probability ?? 0) * 100)}%)`,
        snippet: clip(s.description),
        meta: "Scenario",
      });
    }
  });

  (data.root_cause_suggestions ?? []).forEach((rc, i) => {
    if (hits.length >= MAX_BUILT) return;
    const line = `${rc.signal} → ${rc.likely_cause}`;
    hits.push({
      id: `root-cause-${i}`,
      category: "finding",
      title: clip(rc.signal, 80),
      snippet: clip(line),
      meta: rc.confidence ? `Likely driver (${rc.confidence})` : "Likely driver",
    });
  });

  pushAgent(hits, "summary", "Overview", data.summary, "BLUF / summary");
  pushAgent(hits, "narrative_story", "Narrative", data.narrative_story ?? undefined, "Cross-stream story");

  const newsSum = data.news?.summary;
  pushAgent(hits, "news-summary", "NEWS", newsSum, "News agent");

  (data.news?.articles ?? []).forEach((a, i) => {
    const title = a.title?.trim() || "Untitled headline";
    const line = [a.source, a.title].filter(Boolean).join(" — ");
    hits.push({
      id: `headline-${i}-${a.url ?? i}`,
      category: "headline",
      title: clip(title, 100),
      snippet: clip(line),
      meta: a.source ? String(a.source) : "Headline",
      url: a.url,
    });
  });

  (data.corroborated_patterns ?? []).forEach((p, i) => {
    if (p.summary) {
      hits.push({
        id: `corr-${i}`,
        category: "finding",
        title: clip(p.summary, 90),
        snippet: clip(p.summary),
        meta: p.agent_ids?.length ? `Corroborated (${p.agent_ids.join(", ")})` : "Corroborated pattern",
      });
    }
  });

  (data.pattern_flags ?? []).forEach((p, i) => {
    if (hits.length >= MAX_BUILT) return;
    const title = (p.title ?? p.id ?? "Pattern").trim();
    const line = [p.title, p.detail].filter(Boolean).join(" — ");
    if (!line.trim()) return;
    hits.push({
      id: `pattern-flag-${i}-${p.id ?? i}`,
      category: "finding",
      title: clip(title, 90),
      snippet: clip(line),
      meta: "Data pattern watch",
    });
  });

  (data.finint?.polymarket ?? []).forEach((m, i) => {
    if (m.question) {
      hits.push({
        id: `poly-${i}`,
        category: "agent",
        title: "FININT — Polymarket",
        snippet: clip(m.question),
        meta: m.probability != null ? `${Math.round(m.probability * 100)}%` : "Market",
        agentLabel: "FININT",
        url: m.url,
      });
    }
  });

  pushAgent(hits, "cyber", "CYBER / TECHINT", data.cyber?.summary, "Cyber");

  const tech = data.techint as { summary?: string } | undefined;
  pushAgent(hits, "techint", "TECHINT", tech?.summary, "Tech / export controls");

  pushAgent(hits, "energy", "ENERGY", data.energy?.summary, "Energy & commodities");
  pushAgent(hits, "protest", "PROTEST", data.protest?.summary, "Protest");
  pushAgent(hits, "diplo", "DIPLOMATIC", data.diplo?.summary, "Sanctions & diplomacy");
  pushAgent(hits, "proximity", "PROXIMITY", data.proximity?.summary, "Proximity");
  pushAgent(hits, "chokepoint", "CHOKEPOINT", data.chokepoint?.summary, "Chokepoints");

  const nar = data.narrative;
  pushAgent(hits, "narrative-synth", "SIGNAL FRAMEWORK", nar?.synthesis_text, "Narrative synthesis");
  (nar?.source_comparison_table ?? []).forEach((row, i) => {
    const blob = [row.point, row.state_narrative, row.exile_narrative].filter(Boolean).join(" | ");
    if (blob) {
      hits.push({
        id: `narr-row-${i}`,
        category: "agent",
        title: "SIGNAL FRAMEWORK",
        snippet: clip(blob),
        meta: row.point ? clip(row.point, 60) : "Comparison row",
        agentLabel: "SIGNAL FRAMEWORK",
      });
    }
  });

  const pred = data.predictive;
  const esc = [...(pred?.escalation ?? []), pred?.baseline_escalation].filter(Boolean);
  esc.forEach((e, i) => {
    if (!e) return;
    const parts = [e.horizon, e.level, ...(e.drivers ?? []), e.notes].filter(Boolean);
    const t = parts.join(" — ");
    hits.push({
      id: `pred-${i}`,
      category: "agent",
      title: "PREDICTIVE",
      snippet: clip(t),
      meta: e.horizon,
      agentLabel: "PREDICTIVE",
    });
  });

  const risk = data.compliance?.risk_score;
  if (risk) {
    const drivers = (risk.drivers ?? []).map((d) => `${d.factor}: ${d.detail}`).join(" | ");
    pushAgent(hits, "compliance-risk", "COMPLIANCE", `${risk.level}. ${drivers}`, "Compliance");
  }

  (data.alerts ?? []).forEach((al, i) => {
    hits.push({
      id: `alert-${i}`,
      category: "finding",
      title: clip(al.text, 80),
      snippet: clip(al.text),
      meta: `${al.severity} · ${al.source}`,
    });
  });

  (data.sigint?.aircraft ?? []).forEach((ac, i) => {
    if (ac.flight) {
      hits.push({
        id: `ac-${i}`,
        category: "agent",
        title: "SIGINT — Aircraft",
        snippet: clip(ac.flight),
        meta: ac.country,
        agentLabel: "SIGINT",
      });
    }
  });
  (data.sigint?.conflict_reports ?? []).forEach((r, i) => {
    if (r.title) {
      hits.push({
        id: `sig-report-${i}`,
        category: "headline",
        title: clip(r.title, 100),
        snippet: clip([r.title, r.source].filter(Boolean).join(" — ")),
        meta: r.source ?? "SIGINT report",
        url: r.url,
      });
    }
  });

  (data.diplo?.un_icj_news ?? []).forEach((n, i) => {
    if (n.title) {
      hits.push({
        id: `icj-${i}`,
        category: "headline",
        title: clip(n.title, 100),
        snippet: clip([n.title, n.source].filter(Boolean).join(" — ")),
        meta: n.source ?? "UN / ICJ",
        url: n.url,
      });
    }
  });

  return hits.slice(0, MAX_BUILT);
}

const MAX_RESULTS = 60;

export function filterSearchHits(hits: SearchHit[], query: string): SearchHit[] {
  const q = query.trim().toLowerCase();
  if (!q) return hits.slice(0, MAX_RESULTS);
  const out = hits.filter((h) => {
    const blob = `${h.title} ${h.snippet} ${h.meta ?? ""} ${h.agentLabel ?? ""}`.toLowerCase();
    return blob.includes(q);
  });
  return out.slice(0, MAX_RESULTS);
}
