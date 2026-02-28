const countries = [
  { name: "Iran", status: "DEGRADED", ok: false },
  { name: "Israel", status: "NORMAL", ok: true },
  { name: "US", status: "NORMAL", ok: true },
];

export function InternetConnectivity() {
  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-2">
      <h3 className="font-mono text-[10px] text-muted-foreground tracking-wider">INTERNET CONNECTIVITY</h3>
      <div className="space-y-1.5">
        {countries.map((c) => (
          <div key={c.name} className="flex items-center justify-between text-xs font-mono">
            <span>{c.name}</span>
            <span className="flex items-center gap-1.5">
              <span className={`h-1.5 w-1.5 rounded-full ${c.ok ? "bg-primary" : "bg-warning animate-pulse"}`} />
              <span className={c.ok ? "text-primary" : "text-warning"}>{c.status}</span>
            </span>
          </div>
        ))}
      </div>
      <p className="text-[9px] text-muted-foreground">Source: NetBlocks / IODA</p>
    </div>
  );
}
