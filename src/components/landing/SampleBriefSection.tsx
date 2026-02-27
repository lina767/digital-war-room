export function SampleBriefSection() {
  return (
    <section className="py-24 border-t border-border">
      <div className="container mx-auto px-4">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            What a Brief <span className="text-primary">Looks Like</span>
          </h2>
        </div>

        <div className="max-w-2xl mx-auto">
          <div className="rounded-lg border border-primary/30 bg-card border-glow overflow-hidden">
            <pre className="font-mono text-xs sm:text-sm p-6 text-muted-foreground leading-relaxed overflow-x-auto whitespace-pre">
{`┌─────────────────────────────────────────────────┐
│ INTELLIGENCE BRIEF · US-IRAN · 2025-03-15 14:32 │
│ Classification: OSINT ONLY                       │
├─────────────────────────────────────────────────┤
│ `}<span className="text-foreground">BLUF:</span>{` Escalation Score `}<span className="text-threat">7.2/10 ▲</span>{`                 │
│                                                  │
│ `}<span className="text-foreground">KEY FINDINGS</span>{`                                     │
│ `}<span className="text-primary">●</span>{` 3x RC-135 sorties over Persian Gulf (6h)      │
│ `}<span className="text-primary">●</span>{` Brent crude +4.2% in 24h                      │
│ `}<span className="text-primary">●</span>{` Polymarket "US strikes Iran" → 34% (+8pts)    │
│ `}<span className="text-primary">●</span>{` IRGC mobilization reports (unverified)        │
│                                                  │
│ `}<span className="text-foreground">SCENARIOS</span>{`                                        │
│ [45%] Continued pressure campaign               │
│ [32%] Limited kinetic strike                    │
│ [23%] Back-channel de-escalation                │
└─────────────────────────────────────────────────┘`}
            </pre>
          </div>
        </div>
      </div>
    </section>
  );
}
