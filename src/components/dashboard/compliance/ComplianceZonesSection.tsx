import { useEffect, useState } from "react";
import { MapPin, ChevronDown, ChevronRight } from "lucide-react";
import { getComplianceZones, type ZonesResponse } from "@/lib/api";

export function ComplianceZonesSection() {
  const [zones, setZones] = useState<ZonesResponse | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getComplianceZones().then((data) => {
      if (!cancelled && data) setZones(data);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const count = zones ? zones.sanctions_zones.length + zones.all_zones.length : 0;
  if (count === 0) return null;

  return (
    <div className="space-y-1">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground w-full"
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        <MapPin className="h-3 w-3" />
        <span>Zones ({count})</span>
      </button>
      {open && zones && (
        <div className="pl-4 space-y-1 text-[11px]">
          <div>
            <span className="text-muted-foreground">Sanctions:</span>
            {zones.sanctions_zones.map((z, i) => (
              <p key={i} className="font-mono truncate">
                {z.name ?? "-"}
              </p>
            ))}
          </div>
          <div>
            <span className="text-muted-foreground">All zones:</span>
            {zones.all_zones.slice(0, 15).map((z, i) => (
              <p key={i} className="font-mono truncate">
                {z.name ?? "-"}
              </p>
            ))}
            {zones.all_zones.length > 15 && (
              <p className="text-muted-foreground">+{zones.all_zones.length - 15} more</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
