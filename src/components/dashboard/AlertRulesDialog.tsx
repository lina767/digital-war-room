import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import {
  fetchAlertRules,
  createAlertRule,
  updateAlertRule,
  deleteAlertRule,
  type AlertRule,
  type AlertRuleKind,
} from "@/lib/api/alerts";
import { Loader2, Trash2, X } from "lucide-react";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved?: () => void;
}

const KINDS: { value: AlertRuleKind; label: string; hint: string }[] = [
  { value: "keyword", label: "Keyword", hint: "Match in summary, findings, headlines" },
  { value: "escalation_min", label: "Min escalation score", hint: "Fires when escalation_score ≥ threshold" },
  { value: "threat_level", label: "Threat level", hint: "Comma-separated: CRITICAL,HIGH,ELEVATED,LOW,MINIMAL" },
];

export function AlertRulesDialog({ open, onOpenChange, onSaved }: Props) {
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("New rule");
  const [kind, setKind] = useState<AlertRuleKind>("keyword");
  const [conflictSub, setConflictSub] = useState("");
  const [keyword, setKeyword] = useState("");
  const [minEsc, setMinEsc] = useState("60");
  const [threatLevels, setThreatLevels] = useState("CRITICAL,HIGH");
  const [notifyEmail, setNotifyEmail] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetchAlertRules();
      setRules(r);
    } catch {
      setRules([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const resetForm = () => {
    setName("New rule");
    setKind("keyword");
    setConflictSub("");
    setKeyword("");
    setMinEsc("60");
    setThreatLevels("CRITICAL,HIGH");
    setNotifyEmail("");
  };

  const onCreate = async () => {
    setSaving(true);
    try {
      const body: Parameters<typeof createAlertRule>[0] = {
        name,
        rule_kind: kind,
        conflict_substring: conflictSub,
        enabled: true,
        notify_email: notifyEmail.trim() || undefined,
      };
      if (kind === "keyword") body.keyword = keyword.trim() || undefined;
      if (kind === "escalation_min") body.min_escalation = parseFloat(minEsc) || 0;
      if (kind === "threat_level") body.threat_levels = threatLevels.trim() || undefined;
      await createAlertRule(body);
      resetForm();
      await load();
      onSaved?.();
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  const onToggle = async (r: AlertRule) => {
    try {
      await updateAlertRule(r.id, { enabled: !r.enabled });
      await load();
      onSaved?.();
    } catch {
      // ignore
    }
  };

  const onDelete = async (r: AlertRule) => {
    if (!confirm(`Delete rule "${r.name}"?`)) return;
    try {
      await deleteAlertRule(r.id);
      await load();
      onSaved?.();
    } catch {
      // ignore
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="alert-rules-title"
    >
      <Card className="w-full max-w-lg max-h-[90vh] overflow-hidden flex flex-col border-border shadow-xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 id="alert-rules-title" className="text-sm font-mono font-semibold tracking-wider">
            ALERT RULES
          </h2>
          <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={() => onOpenChange(false)} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="overflow-y-auto flex-1 px-4 py-3 space-y-4">
          <div className="space-y-2 text-xs">
            <label className="block font-mono text-muted-foreground">Rule name</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} className="font-mono text-xs h-9" />
            <label className="block font-mono text-muted-foreground mt-2">Theater contains (optional)</label>
            <Input
              value={conflictSub}
              onChange={(e) => setConflictSub(e.target.value)}
              placeholder="e.g. Ukraine — empty = any theater"
              className="font-mono text-xs h-9"
            />
            <label className="block font-mono text-muted-foreground mt-2">Rule type</label>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as AlertRuleKind)}
              className="w-full h-9 rounded-md border border-input bg-background px-2 text-xs font-mono"
            >
              {KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
            <p className="text-[10px] text-muted-foreground">{KINDS.find((x) => x.value === kind)?.hint}</p>
            {kind === "keyword" && (
              <>
                <label className="block font-mono text-muted-foreground mt-2">Keyword</label>
                <Input value={keyword} onChange={(e) => setKeyword(e.target.value)} className="font-mono text-xs h-9" />
              </>
            )}
            {kind === "escalation_min" && (
              <>
                <label className="block font-mono text-muted-foreground mt-2">Minimum score</label>
                <Input
                  type="number"
                  step="0.1"
                  value={minEsc}
                  onChange={(e) => setMinEsc(e.target.value)}
                  className="font-mono text-xs h-9"
                />
              </>
            )}
            {kind === "threat_level" && (
              <>
                <label className="block font-mono text-muted-foreground mt-2">Threat levels</label>
                <Input value={threatLevels} onChange={(e) => setThreatLevels(e.target.value)} className="font-mono text-xs h-9" />
              </>
            )}
            <label className="block font-mono text-muted-foreground mt-2">Notify email (optional, Resend)</label>
            <Input
              type="email"
              value={notifyEmail}
              onChange={(e) => setNotifyEmail(e.target.value)}
              placeholder="analyst@example.com"
              className="font-mono text-xs h-9"
            />
            <Button type="button" className="w-full mt-2" size="sm" disabled={saving} onClick={() => void onCreate()}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Add rule"}
            </Button>
          </div>

          <div className="border-t border-border pt-3">
            <h3 className="text-[11px] font-mono text-muted-foreground mb-2">Active rules</h3>
            {loading && (
              <div className="flex justify-center py-4">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            )}
            {!loading && rules.length === 0 && (
              <p className="text-xs text-muted-foreground">No rules yet.</p>
            )}
            <ul className="space-y-2">
              {rules.map((r) => (
                <li
                  key={r.id}
                  className="flex items-start justify-between gap-2 rounded border border-border/80 px-2 py-2 text-xs"
                >
                  <div className="min-w-0">
                    <div className="font-medium truncate">{r.name}</div>
                    <div className="text-[10px] text-muted-foreground font-mono">
                      {r.rule_kind}
                      {r.conflict_substring ? ` · ${r.conflict_substring}` : ""}
                      {r.enabled ? "" : " · disabled"}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Button type="button" variant="outline" size="sm" className="h-7 text-[10px] px-2" onClick={() => void onToggle(r)}>
                      {r.enabled ? "Off" : "On"}
                    </Button>
                    <Button type="button" variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => void onDelete(r)}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Card>
    </div>
  );
}
