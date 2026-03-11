import { useState } from "react";
import {
  IRAN_CONFLICT_ACTORS,
  activityFromKeyFindings,
  type ConflictActor,
  type ActorRole,
} from "@/components/dashboard/actorsData";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown, Users } from "lucide-react";

const ROLE_STYLES: Record<ActorRole, string> = {
  aggressor: "bg-destructive/20 text-destructive border-destructive/40",
  retaliating: "bg-orange-500/20 text-orange-500 border-orange-500/40",
  defender: "bg-primary/20 text-primary border-primary/40",
  neutral: "bg-muted text-muted-foreground border-border",
};

const ROLE_LABELS: Record<ActorRole, string> = {
  aggressor: "AGGRESSOR",
  retaliating: "RETALIATING",
  defender: "DEFENDER",
  neutral: "NEUTRAL",
};

function activityBarColor(activity: number): string {
  if (activity >= 80) return "bg-destructive";
  if (activity >= 60) return "bg-orange-500";
  return "bg-primary/80";
}

interface ActorsPanelProps {
  /** From analysis; may include actors with activity and intelligence */
  conflictData: { key_findings?: string[]; actors?: ConflictActor[] } | null;
  /** Only show for Iran */
  activeConflict?: string | null;
}

export function ActorsPanel({ conflictData, activeConflict }: ActorsPanelProps) {
  const [openId, setOpenId] = useState<string | null>(null);
  const isIran = activeConflict != null && String(activeConflict).toLowerCase().includes("iran");

  const actors: ConflictActor[] = (() => {
    if (Array.isArray(conflictData?.actors) && conflictData.actors.length > 0) {
      return conflictData.actors;
    }
    if (!isIran) return [];
    const keyFindings = conflictData?.key_findings ?? [];
    return IRAN_CONFLICT_ACTORS.map((a) => ({
      ...a,
      activity: activityFromKeyFindings(a.id, a.name, keyFindings),
      intelligence: undefined,
    })) as ConflictActor[];
  })();

  if (actors.length === 0) return null;

  return (
    <div className="rounded-lg border border-border bg-card/50 overflow-hidden">
      <div className="px-2 py-1.5 border-b border-border flex items-center gap-1.5">
        <Users className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="font-mono text-[10px] text-muted-foreground tracking-wider">ACTORS</span>
        <span className="text-[10px] text-muted-foreground ml-auto">{actors.length}</span>
      </div>
      <ul className="divide-y divide-border/60 max-h-[320px] overflow-y-auto">
        {actors.map((actor) => (
          <li key={actor.id}>
            <Collapsible
              open={openId === actor.id}
              onOpenChange={(open) => setOpenId(open ? actor.id : null)}
            >
              <CollapsibleTrigger className="w-full px-3 py-2 flex items-center gap-2 text-left hover:bg-muted/30 transition-colors">
                <span className="font-mono text-xs font-medium truncate flex-1 min-w-0">
                  {actor.name}
                </span>
                <span
                  className={`shrink-0 text-[9px] font-mono px-1.5 py-0.5 rounded border ${ROLE_STYLES[actor.role]}`}
                >
                  {ROLE_LABELS[actor.role]}
                </span>
                <div className="w-12 h-1.5 rounded-full bg-muted overflow-hidden shrink-0">
                  <div
                    className={`h-full rounded-full transition-all ${activityBarColor(actor.activity)}`}
                    style={{ width: `${Math.min(100, actor.activity)}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono text-muted-foreground w-6 text-right">
                  {actor.activity}
                </span>
                <ChevronDown
                  className={`h-3 w-3 shrink-0 text-muted-foreground transition-transform ${
                    openId === actor.id ? "rotate-180" : ""
                  }`}
                />
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="px-3 pb-3 pt-0 border-t border-border/50 bg-background/50 space-y-2 text-[11px]">
                  {actor.intelligence?.official_position && (
                    <div>
                      <p className="font-mono text-muted-foreground uppercase tracking-wider mb-0.5">
                        Official position
                      </p>
                      <p className="leading-snug">{actor.intelligence.official_position}</p>
                    </div>
                  )}
                  {actor.intelligence?.verified_actions &&
                    actor.intelligence.verified_actions.length > 0 && (
                      <div>
                        <p className="font-mono text-muted-foreground uppercase tracking-wider mb-0.5">
                          Doing (verified actions)
                        </p>
                        <ul className="list-disc list-inside space-y-0.5">
                          {actor.intelligence.verified_actions.map((a, i) => (
                            <li key={i}>{a}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  {actor.intelligence?.signals && actor.intelligence.signals.length > 0 && (
                    <div>
                      <p className="font-mono text-muted-foreground uppercase tracking-wider mb-0.5">
                        Signals
                      </p>
                      <ul className="list-disc list-inside space-y-0.5">
                        {actor.intelligence.signals.map((s, i) => (
                          <li key={i}>{s}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {actor.intelligence?.military_profile && (
                    <div>
                      <p className="font-mono text-muted-foreground uppercase tracking-wider mb-0.5">
                        Military profile
                      </p>
                      <p className="leading-snug">{actor.intelligence.military_profile}</p>
                    </div>
                  )}
                  {!actor.intelligence ||
                    (!actor.intelligence.official_position &&
                      !(actor.intelligence.verified_actions?.length) &&
                      !(actor.intelligence.signals?.length) &&
                      !actor.intelligence.military_profile) && (
                    <p className="text-muted-foreground italic">
                      Actor intelligence (position, actions, signals, military profile) will be
                      filled from analysis when available.
                    </p>
                  )}
                </div>
              </CollapsibleContent>
            </Collapsible>
          </li>
        ))}
      </ul>
    </div>
  );
}
