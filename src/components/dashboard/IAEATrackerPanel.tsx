import { useState, useEffect, useCallback } from "react";
import { IntelPanel, IntelPanelSkeleton } from "@/components/dashboard/IntelPanel";
import { getIaeaTracker, type IaeaTrackerResponse, type IaeaTrackerCorrelationNote } from "@/lib/api";
import { Plane, ChevronDown, ChevronRight, Cloud, FileText, MessageCircle, Calendar, MapPin } from "lucide-react";

const CONFIDENCE_STYLES: Record<string, string> = {
  high: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  medium: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  low: "bg-muted/50 text-muted-foreground border-border",
};

function formatFlightPlanStatus(status: string | undefined) {
  const normalized = (status || "unknown").toLowerCase();
  const labels: Record<string, string> = {
    no_new_request: "No new request",
    cancelled: "Cancelled",
    unknown: "Unknown",
  };
  return labels[normalized] ?? normalized.replace(/_/g, " ");
}

function ConfidenceBadge({ confidence }: { confidence: string }) {
  const c = (confidence || "low").toLowerCase();
  const style = CONFIDENCE_STYLES[c] ?? CONFIDENCE_STYLES.low;
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider ${style}`}>
      {c}
    </span>
  );
}

export function IAEATrackerPanel() {
  const [data, setData] = useState<IaeaTrackerResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAdsB, setShowAdsB] = useState(false);
  const [showMetar, setShowMetar] = useState(false);
  const [showFlightPlan, setShowFlightPlan] = useState(false);
  const [showPress, setShowPress] = useState(false);
  const [showTelegram, setShowTelegram] = useState(false);
  const [showNotams, setShowNotams] = useState(false);

  const fetchTracker = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getIaeaTracker();
      setData(result ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTracker();
  }, [fetchTracker]);

  if (loading && !data) {
    return <IntelPanelSkeleton lines={4} />;
  }

  const summary = data?.summary ?? "";
  const notes = (data?.correlation_notes ?? []) as IaeaTrackerCorrelationNote[];
  const adsb = data?.oeiii_adsb;
  const aircraft = adsb?.aircraft ?? [];
  const metar = data?.metar_orer;
  const flightPlan = data?.flight_plan_status;
  const press = data?.iaea_press_grossi;
  const telegram = data?.iaea_telegram_signals;
  const notamsBlock = data?.notams;
  const pressItems = press?.items ?? [];
  const telegramPosts = telegram?.posts ?? [];
  const notamList = Array.isArray(notamsBlock?.notams) ? notamsBlock.notams : [];

  return (
    <IntelPanel
      title="IAEA / OE-III TRACKER"
      icon={<Plane className="h-3.5 w-3.5 text-muted-foreground" />}
    >
      {error && (
        <p className="text-[11px] text-red-400 font-medium">{error}</p>
      )}

      {data?.error && (
        <p className="text-[11px] text-amber-400">{data.error}</p>
      )}

      {summary && (
        <p className="text-[11px] text-foreground/90 leading-relaxed">{summary}</p>
      )}

      {/* Correlation notes with confidence */}
      {notes.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">Signals</p>
          <ul className="space-y-1.5">
            {notes.map((n, i) => (
              <li key={i} className="flex items-start gap-2 text-[11px]">
                <ConfidenceBadge confidence={n.confidence} />
                <span className="text-foreground/85 flex-1 min-w-0">{n.hint}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ADS-B / OE-III */}
      {adsb && (aircraft.length > 0 || adsb.correlation_hint) && (
        <div className="border-t border-border/60 pt-2 space-y-1">
          <button
            type="button"
            onClick={() => setShowAdsB(!showAdsB)}
            className="flex items-center gap-1.5 w-full text-left text-[11px] font-medium text-foreground"
          >
            {showAdsB ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            <Plane className="h-3.5 w-3.5 text-primary" />
            OE-III ADS-B ({aircraft.length})
          </button>
          {showAdsB && (
            <div className="pl-5 space-y-1 text-[11px] text-muted-foreground">
              {adsb.correlation_hint && <p>{adsb.correlation_hint}</p>}
              {aircraft.slice(0, 5).map((ac, i) => (
                <div key={i} className="flex justify-between gap-2">
                  <span className="font-mono truncate">{ac.hex ?? ac.flight ?? "—"}</span>
                  <span>
                    {ac.on_ground ? "Ground" : "Air"}
                    {ac.location_interpretation === "parked_erbil" && " · Erbil"}
                  </span>
                </div>
              ))}
              {aircraft.length > 5 && <p>+{aircraft.length - 5} more</p>}
            </div>
          )}
        </div>
      )}

      {/* METAR ORER */}
      {metar && (metar.raw || metar.correlation_hint) && (
        <div className="border-t border-border/60 pt-2 space-y-1">
          <button
            type="button"
            onClick={() => setShowMetar(!showMetar)}
            className="flex items-center gap-1.5 w-full text-left text-[11px] font-medium text-foreground"
          >
            {showMetar ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            <Cloud className="h-3.5 w-3.5 text-sky-400" />
            METAR ORER
            {metar.operational_delay_risk && (
              <span className="text-amber-400 font-medium">Delay risk</span>
            )}
          </button>
          {showMetar && (
            <div className="pl-5 space-y-0.5 text-[11px] text-muted-foreground">
              {metar.correlation_hint && <p>{metar.correlation_hint}</p>}
              {metar.visibility_m != null && <p>Visibility: {metar.visibility_m} m</p>}
              {metar.rvr_m != null && <p>RVR: {metar.rvr_m} m</p>}
              {metar.raw && <p className="font-mono text-[10px] break-all">{metar.raw}</p>}
            </div>
          )}
        </div>
      )}

      {/* NOTAMs */}
      {notamsBlock && (notamList.length > 0 || notamsBlock.correlation_hint) && (
        <div className="border-t border-border/60 pt-2 space-y-1">
          <button
            type="button"
            onClick={() => setShowNotams(!showNotams)}
            className="flex items-center gap-1.5 w-full text-left text-[11px] font-medium text-foreground"
          >
            {showNotams ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            <MapPin className="h-3.5 w-3.5 text-amber-400" />
            NOTAMs ({notamList.length})
          </button>
          {showNotams && (
            <div className="pl-5 space-y-1.5 text-[11px] text-muted-foreground">
              {notamsBlock.correlation_hint && <p>{notamsBlock.correlation_hint}</p>}
              {notamList.slice(0, 10).map((n, i) => {
                const item = n as { id?: string; text?: string; effective?: string; expiry?: string; location?: string };
                return (
                  <div key={i} className="rounded border border-border/50 px-2 py-1 bg-background/30">
                    {item.location && <p className="font-mono text-[10px] text-foreground/80">{item.location}</p>}
                    {item.text && <p className="break-words">{item.text}</p>}
                    {(item.effective || item.expiry) && (
                      <p className="text-[10px] mt-0.5">
                        {item.effective && <span>Valid from: {item.effective}</span>}
                        {item.expiry && <span className="ml-2">Until: {item.expiry}</span>}
                      </p>
                    )}
                  </div>
                );
              })}
              {notamList.length > 10 && <p>+{notamList.length - 10} more</p>}
            </div>
          )}
        </div>
      )}

      {/* Flight plan status */}
      {flightPlan && flightPlan.status !== "unknown" && (
        <div className="border-t border-border/60 pt-2 space-y-1">
          <button
            type="button"
            onClick={() => setShowFlightPlan(!showFlightPlan)}
            className="flex items-center gap-1.5 w-full text-left text-[11px] font-medium text-foreground"
          >
            {showFlightPlan ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            <FileText className="h-3.5 w-3.5 text-muted-foreground" />
            Flight plan: {formatFlightPlanStatus(flightPlan.status)}
          </button>
          {showFlightPlan && flightPlan.correlation_hint && (
            <p className="pl-5 text-[11px] text-muted-foreground">{flightPlan.correlation_hint}</p>
          )}
        </div>
      )}

      {/* IAEA Press */}
      {press && (pressItems.length > 0 || press.correlation_hint) && (
        <div className="border-t border-border/60 pt-2 space-y-1">
          <button
            type="button"
            onClick={() => setShowPress(!showPress)}
            className="flex items-center gap-1.5 w-full text-left text-[11px] font-medium text-foreground"
          >
            {showPress ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
            IAEA Press / Grossi ({pressItems.length})
          </button>
          {showPress && (
            <div className="pl-5 space-y-1 text-[11px] text-muted-foreground">
              {press.correlation_hint && <p>{press.correlation_hint}</p>}
              {pressItems.slice(0, 3).map((item, i) => (
                <a
                  key={i}
                  href={item.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block truncate text-primary hover:underline"
                >
                  {item.title || "—"}
                </a>
              ))}
              {pressItems.length > 3 && <p>+{pressItems.length - 3} more</p>}
            </div>
          )}
        </div>
      )}

      {/* Telegram signals */}
      {telegram && (telegramPosts.length > 0 || telegram.correlation_hint) && (
        <div className="border-t border-border/60 pt-2 space-y-1">
          <button
            type="button"
            onClick={() => setShowTelegram(!showTelegram)}
            className="flex items-center gap-1.5 w-full text-left text-[11px] font-medium text-foreground"
          >
            {showTelegram ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            <MessageCircle className="h-3.5 w-3.5 text-sky-400" />
            Telegram ({telegramPosts.length})
          </button>
          {showTelegram && (
            <div className="pl-5 space-y-1 text-[11px] text-muted-foreground">
              {telegram.correlation_hint && <p>{telegram.correlation_hint}</p>}
              {telegramPosts.slice(0, 3).map((p, i) => (
                <p key={i} className="line-clamp-2">{p.text || "—"}</p>
              ))}
              {telegramPosts.length > 3 && <p>+{telegramPosts.length - 3} more</p>}
            </div>
          )}
        </div>
      )}

      {!data && !loading && !error && (
        <p className="text-[11px] text-muted-foreground italic">IAEA tracker data unavailable.</p>
      )}
    </IntelPanel>
  );
}
