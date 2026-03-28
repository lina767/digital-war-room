import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, Settings2, CheckCheck, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type AlertNotification,
} from "@/lib/api/alerts";
import { AlertRulesDialog } from "@/components/dashboard/AlertRulesDialog";

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export function AlertNotificationCenter() {
  const [open, setOpen] = useState(false);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<AlertNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchNotifications({ limit: 40 });
      setItems(data.notifications);
      setUnread(data.unread_count);
    } catch {
      // ignore offline / 401
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 45_000);
    return () => window.clearInterval(id);
  }, [load]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const onReadOne = async (n: AlertNotification) => {
    if (n.read_at) return;
    try {
      await markNotificationRead(n.id);
      setItems((prev) =>
        prev.map((x) => (x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x)),
      );
      setUnread((u) => Math.max(0, u - 1));
    } catch {
      // ignore
    }
  };

  const onReadAll = async () => {
    try {
      await markAllNotificationsRead();
      setItems((prev) => prev.map((x) => ({ ...x, read_at: x.read_at ?? new Date().toISOString() })));
      setUnread(0);
    } catch {
      // ignore
    }
  };

  return (
    <>
      <div className="relative" ref={wrapRef}>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="relative h-9 px-2 font-mono text-xs border-border"
          aria-label="Alert notifications"
          aria-expanded={open}
          onClick={() => {
            setOpen((o) => !o);
            if (!open) void load();
          }}
        >
          <Bell className="h-3.5 w-3.5" aria-hidden />
          {unread > 0 && (
            <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-destructive text-destructive-foreground text-[10px] font-bold flex items-center justify-center">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </Button>
        {open && (
          <Card className="absolute right-0 top-full mt-1 z-50 w-[min(100vw-2rem,22rem)] max-h-[min(70vh,24rem)] overflow-hidden flex flex-col shadow-lg border-border bg-popover">
            <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border bg-card/80">
              <span className="text-[11px] font-mono tracking-wider text-muted-foreground">ALERTS</span>
              <div className="flex items-center gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-[11px]"
                  onClick={() => setRulesOpen(true)}
                >
                  <Settings2 className="h-3.5 w-3.5 mr-1" aria-hidden />
                  Rules
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-[11px]"
                  disabled={unread === 0}
                  onClick={() => void onReadAll()}
                >
                  <CheckCheck className="h-3.5 w-3.5 mr-1" aria-hidden />
                  All read
                </Button>
              </div>
            </div>
            <div className="overflow-y-auto flex-1 min-h-0">
              {loading && items.length === 0 && (
                <div className="flex items-center justify-center py-8 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
                </div>
              )}
              {!loading && items.length === 0 && (
                <p className="text-xs text-muted-foreground px-3 py-6 text-center">
                  No alerts yet. Configure rules to get notified when scores or keywords match.
                </p>
              )}
              {items.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  className={`w-full text-left px-3 py-2 border-b border-border/60 hover:bg-muted/40 transition-colors ${
                    !n.read_at ? "bg-primary/5" : ""
                  }`}
                  onClick={() => void onReadOne(n)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-xs font-medium text-foreground line-clamp-2">{n.title}</span>
                    <span className="text-[10px] text-muted-foreground shrink-0 font-mono">
                      {formatTime(n.created_at)}
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-1 line-clamp-3">{n.body}</p>
                </button>
              ))}
            </div>
          </Card>
        )}
      </div>
      <AlertRulesDialog open={rulesOpen} onOpenChange={setRulesOpen} onSaved={() => void load()} />
    </>
  );
}
