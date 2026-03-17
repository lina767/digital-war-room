import { useMemo, useState } from "react";
import { Search, Database, Key, ExternalLink } from "lucide-react";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  SOURCE_DIRECTORY,
  getReliabilityLabel,
  type DataSourceEntry,
  type ReliabilityTier,
} from "@/lib/sourceDirectory";
import { AGENTS_WITH_SOURCES } from "@/components/dashboard/agentsConfig";
import { SEO } from "@/components/SEO";
import { TITLE_SOURCE_DIRECTORY, DESCRIPTION_SOURCE_DIRECTORY } from "@/lib/seoCopy";

const RELIABILITY_ORDER: ReliabilityTier[] = ["official", "curated", "community", "supplementary"];

const SourceDirectory = () => {
  const [search, setSearch] = useState("");
  const [agentFilter, setAgentFilter] = useState<string>("");
  const [reliabilityFilter, setReliabilityFilter] = useState<ReliabilityTier | "">("");

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return SOURCE_DIRECTORY.filter((s) => {
      const matchSearch =
        !q ||
        s.name.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q) ||
        s.agents.some((a) => a.toLowerCase().includes(q));
      const matchAgent = !agentFilter || s.agents.includes(agentFilter);
      const matchReliability = !reliabilityFilter || s.reliability === reliabilityFilter;
      return matchSearch && matchAgent && matchReliability;
    });
  }, [search, agentFilter, reliabilityFilter]);

  return (
    <>
      <SEO
        title={TITLE_SOURCE_DIRECTORY}
        description={DESCRIPTION_SOURCE_DIRECTORY}
        path="/sources"
        breadcrumbs={[
          { name: "Home", url: "https://digital-war-room.com/" },
          { name: "Source Directory", url: "https://digital-war-room.com/sources" },
        ]}
      />
      <ContentPageLayout
        label="TRANSPARENCY"
        title="Source Directory"
        description="A transparent, searchable directory of all data sources used by the platform, with reliability ratings. Each source is linked to the intelligence agents that use it. Derived outputs (e.g. the Global Impact panel for Iran — oil moves, Strait of Hormuz / chokepoint risk from ENERGY and key findings; Sanctions Compliance — risk score from OFAC/EU via DIPLO, geofencing and AIS anomalies from SIGINT) are shown on the dashboard but do not appear as separate sources here."
        icon={<Database className="h-5 w-5 text-muted-foreground" />}
        maxWidth="5xl"
      >
      {/* Search and filters */}
        <div className="mb-8 space-y-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              type="search"
              placeholder="Search by name, description, or agent…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 bg-muted/50 border-border"
              aria-label="Search sources"
            />
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-xs text-muted-foreground font-medium mr-1">Agent:</span>
            <select
              value={agentFilter}
              onChange={(e) => setAgentFilter(e.target.value)}
              className="h-8 rounded-md border border-border bg-background px-2 text-xs text-foreground"
              aria-label="Filter by agent"
            >
              <option value="">All agents</option>
              {AGENTS_WITH_SOURCES.map((a) => (
                <option key={a.name} value={a.name}>
                  {a.name}
                </option>
              ))}
            </select>
            <span className="text-xs text-muted-foreground font-medium ml-4 mr-1">Reliability:</span>
            <select
              value={reliabilityFilter}
              onChange={(e) => setReliabilityFilter((e.target.value || "") as ReliabilityTier | "")}
              className="h-8 rounded-md border border-border bg-background px-2 text-xs text-foreground"
              aria-label="Filter by reliability"
            >
              <option value="">All</option>
              {RELIABILITY_ORDER.map((t) => (
                <option key={t} value={t}>
                  {getReliabilityLabel(t)}
                </option>
              ))}
            </select>
            <span className="text-xs text-muted-foreground ml-2">
              {filtered.length} source{filtered.length !== 1 ? "s" : ""}
            </span>
          </div>
        </div>

        {/* Legend */}
        <div className="mb-6 p-3 rounded-lg border border-border bg-muted/30 text-xs text-muted-foreground">
          <p className="font-medium text-foreground mb-1">Reliability ratings</p>
          <ul className="space-y-0.5">
            <li><strong>Official</strong> – Government, UN, or official institutions (e.g. NASA, OFAC, CISA, EU, UN/ICJ).</li>
            <li><strong>Curated</strong> – Verified APIs with clear terms (e.g. ACLED, NewsAPI, Alpha Vantage, GDELT).</li>
            <li><strong>Community</strong> – Open feeds, OSINT, community-sourced (e.g. ADSB, RSS, Telegram, OONI).</li>
            <li><strong>Supplementary</strong> – Optional or auxiliary data (e.g. custom GeoJSON, third-party aggregators).</li>
          </ul>
        </div>

        {/* Source cards */}
        <ul className="space-y-4">
          {filtered.map((source) => (
            <SourceCard key={source.id} source={source} />
          ))}
        </ul>
        {filtered.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center">
            No sources match your search. Try a different query or clear filters.
          </p>
        )}
    </ContentPageLayout>
    </>
  );
};

function SourceCard({ source }: { source: DataSourceEntry }) {
  const tierColors: Record<ReliabilityTier, string> = {
    official: "bg-primary/15 text-primary border-primary/30",
    curated: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
    community: "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30",
    supplementary: "bg-muted text-muted-foreground border-border",
  };
  const tierClass = tierColors[source.reliability] ?? tierColors.community;

  return (
    <li className="rounded-lg border border-border bg-card/50 p-4 sm:p-5 hover:border-primary/30 transition-colors">
      <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
        <h2 className="text-base sm:text-lg font-semibold tracking-tight">{source.name}</h2>
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="outline" className={`text-[11px] font-medium ${tierClass}`}>
            {getReliabilityLabel(source.reliability)}
          </Badge>
          {source.keyRequired && (
            <Badge variant="secondary" className="text-[11px] gap-0.5">
              <Key className="h-2.5 w-2.5" />
              Key required
            </Badge>
          )}
          {source.free && (
            <Badge variant="outline" className="text-[11px] text-muted-foreground">
              Free
            </Badge>
          )}
        </div>
      </div>
      <p className="text-sm text-muted-foreground mb-3">{source.description}</p>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] text-muted-foreground font-medium">Used by:</span>
        {source.agents.map((a) => (
          <Badge key={a} variant="outline" className="text-[11px] font-mono">
            {a}
          </Badge>
        ))}
        {source.url && (
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline ml-auto"
          >
            <ExternalLink className="h-3 w-3" />
            Docs / Register
          </a>
        )}
      </div>
    </li>
  );
}

export default SourceDirectory;
