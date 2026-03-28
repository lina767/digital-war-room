import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { SEO } from "@/components/SEO";
import { CONFLICT_OPTIONS } from "@/components/dashboard/conflictData";
import {
  loadPins,
  addPin,
  deletePin,
  exportPinsJson,
  type InvestigationPin,
} from "@/lib/investigationStore";
import { ArrowLeft, Pin, Trash2, Download } from "lucide-react";
import { toast } from "sonner";

export default function InvestigationWorkspacePage() {
  const [pins, setPins] = useState<InvestigationPin[]>([]);
  const [title, setTitle] = useState("");
  const [conflict, setConflict] = useState(CONFLICT_OPTIONS[0]?.apiValue ?? "Iran");
  const [notes, setNotes] = useState("");
  const [refUrl, setRefUrl] = useState("");

  const refresh = useCallback(() => setPins(loadPins()), []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const onAdd = () => {
    const t = title.trim();
    if (!t) {
      toast.error("Title required");
      return;
    }
    addPin({ conflict, title: t, notes: notes.trim(), refUrl: refUrl.trim() || undefined });
    setTitle("");
    setNotes("");
    setRefUrl("");
    refresh();
    toast.success("Pin saved");
  };

  const onExport = () => {
    const blob = new Blob([exportPinsJson()], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `investigation-pins-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Exported pins JSON");
  };

  return (
    <>
      <SEO
        title="Investigation Workspace – Digital War Room"
        description="Save signals, notes, and evidence links for analyst case building."
        path="/app/investigation"
      />
      <div className="min-h-screen bg-background text-foreground">
        <header className="border-b border-border px-4 py-3 flex items-center gap-4">
          <Button variant="ghost" size="sm" asChild>
            <Link to="/app/dashboard" className="inline-flex items-center gap-2">
              <ArrowLeft className="h-4 w-4" aria-hidden />
              Dashboard
            </Link>
          </Button>
          <h1 className="font-mono text-sm tracking-wider text-primary">INVESTIGATION WORKSPACE</h1>
        </header>

        <main className="max-w-3xl mx-auto px-4 py-6 space-y-6">
          <p className="text-sm text-muted-foreground">
            Lightweight case notes stored in this browser. Add a theater, title, and analyst notes; export JSON for reporting.
            For map-correlated workflows, open the{" "}
            <Link to="/app/dashboard" className="text-primary underline">
              dashboard
            </Link>{" "}
            and paste references here.
          </p>

          <Card className="p-4 border-border space-y-3">
            <h2 className="font-mono text-xs text-muted-foreground flex items-center gap-2">
              <Pin className="h-3.5 w-3.5" aria-hidden />
              New pin
            </h2>
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="text-xs font-mono text-muted-foreground">
                Theater
                <select
                  value={conflict}
                  onChange={(e) => setConflict(e.target.value)}
                  className="mt-1 w-full h-9 rounded-md border border-input bg-background px-2 text-sm"
                >
                  {CONFLICT_OPTIONS.map((o) => (
                    <option key={o.id} value={o.apiValue}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs font-mono text-muted-foreground sm:col-span-2">
                Title
                <Input value={title} onChange={(e) => setTitle(e.target.value)} className="mt-1 font-mono text-sm" placeholder="e.g. Carrier movement + outage correlation" />
              </label>
              <label className="text-xs font-mono text-muted-foreground sm:col-span-2">
                Notes
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="mt-1 w-full min-h-[88px] rounded-md border border-input bg-background px-2 py-2 text-sm font-mono"
                  placeholder="Hypothesis, sources, next checks…"
                />
              </label>
              <label className="text-xs font-mono text-muted-foreground sm:col-span-2">
                Reference URL (optional)
                <Input value={refUrl} onChange={(e) => setRefUrl(e.target.value)} className="mt-1 font-mono text-sm" placeholder="https://…" />
              </label>
            </div>
            <Button type="button" onClick={onAdd}>
              Save pin
            </Button>
          </Card>

          <div className="flex items-center justify-between gap-2">
            <h2 className="font-mono text-xs text-muted-foreground">Saved pins ({pins.length})</h2>
            <Button type="button" variant="outline" size="sm" onClick={onExport} disabled={pins.length === 0}>
              <Download className="h-3.5 w-3.5 mr-1" aria-hidden />
              Export JSON
            </Button>
          </div>

          <ul className="space-y-3">
            {pins.length === 0 && (
              <li className="text-sm text-muted-foreground italic">No pins yet.</li>
            )}
            {pins.map((p) => (
              <li key={p.id}>
                <Card className="p-3 border-border">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-medium text-sm">{p.title}</div>
                      <div className="text-[11px] text-muted-foreground font-mono mt-0.5">
                        {p.conflict} · {new Date(p.createdAt).toLocaleString()}
                      </div>
                      {p.notes ? <p className="text-xs mt-2 whitespace-pre-wrap">{p.notes}</p> : null}
                      {p.refUrl ? (
                        <a href={p.refUrl} className="text-xs text-primary break-all inline-block mt-1" target="_blank" rel="noopener noreferrer">
                          {p.refUrl}
                        </a>
                      ) : null}
                    </div>
                    <div className="flex flex-col gap-1 shrink-0">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-destructive"
                        aria-label="Delete pin"
                        onClick={() => {
                          deletePin(p.id);
                          refresh();
                          toast.success("Removed");
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        </main>
      </div>
    </>
  );
}
