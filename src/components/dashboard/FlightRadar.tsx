import { Plane } from "lucide-react";

export function FlightRadar() {
  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-2">
      <h3 className="font-mono text-[10px] text-muted-foreground tracking-wider">FLIGHT RADAR</h3>
      <div className="flex items-center gap-2">
        <Plane className="h-4 w-4 text-primary" />
        <span className="font-mono text-lg text-foreground font-bold">12</span>
        <span className="text-xs text-muted-foreground">military aircraft detected</span>
      </div>
      <a
        href="https://www.adsbexchange.com/"
        target="_blank"
        rel="noopener noreferrer"
        className="text-[10px] text-primary hover:underline font-mono"
      >
        View on ADSB-Exchange →
      </a>
    </div>
  );
}
