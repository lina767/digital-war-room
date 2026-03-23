import { FileDown, RefreshCw, Share2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ThreatLevel } from "@/features/daily-briefing/types/briefing.types";
import { formatDTG } from "@/features/daily-briefing/utils/formatDTG";
import { threatLevelClass } from "@/features/daily-briefing/utils/threatLevelColor";

interface BriefingHeaderProps {
  threatLevel: ThreatLevel;
  escalationScore: number;
  lastUpdated: Date;
  isLive: boolean;
  onRefresh: () => void;
  onExportPDF: () => void;
  onShare: () => void;
}

export function BriefingHeader(props: BriefingHeaderProps) {
  const { threatLevel, escalationScore, lastUpdated, isLive, onRefresh, onExportPDF, onShare } = props;
  return (
    <header className="briefing-card sticky top-2 z-20 mb-4 flex items-center justify-between gap-3 px-4 py-3 backdrop-blur">
      <div className="min-w-0">
        <p className="briefing-mono text-[11px] text-[var(--text-tertiary)]">{formatDTG(lastUpdated)}</p>
        <p className="briefing-mono text-[11px] text-[var(--text-secondary)]">{isLive ? "LIVE FEED" : "CACHED SNAPSHOT"}</p>
      </div>
      <div className="text-center">
        <p className={`briefing-mono text-sm font-semibold ${threatLevelClass(threatLevel)}`}>{threatLevel}</p>
        <p className="briefing-mono text-xs text-[var(--text-secondary)]">{escalationScore}/100</p>
      </div>
      <div className="flex items-center gap-1.5">
        <Button size="sm" onClick={onExportPDF}>
          <FileDown className="h-3.5 w-3.5" />
          Export PDF
        </Button>
        <Button size="sm" variant="ghost" onClick={onShare}>
          <Share2 className="h-3.5 w-3.5" />
          Share
        </Button>
        <Button size="icon" variant="ghost" onClick={onRefresh} aria-label="Refresh briefing">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
