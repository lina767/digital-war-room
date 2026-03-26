import { useState } from "react";
import { Button } from "@/components/ui/button";
import { getAnalyticsConsent, setAnalyticsConsent, type AnalyticsConsent } from "@/lib/analyticsConsent";

type Props = {
  onChange: (value: AnalyticsConsent) => void;
};

export function AnalyticsConsentBanner({ onChange }: Props) {
  const [consent] = useState(() => getAnalyticsConsent());

  if (consent !== null) return null;

  return (
    <div className="fixed bottom-4 left-4 right-4 z-50 rounded-lg border border-border bg-card p-4 shadow-xl">
      <p className="text-sm text-muted-foreground">
        We use optional analytics to improve reliability and UX. You can allow or decline analytics at any time by
        clearing local storage and choosing again.
      </p>
      <div className="mt-3 flex gap-2">
        <Button
          size="sm"
          onClick={() => {
            setAnalyticsConsent("granted");
            onChange("granted");
          }}
        >
          Allow analytics
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            setAnalyticsConsent("denied");
            onChange("denied");
          }}
        >
          Decline
        </Button>
      </div>
    </div>
  );
}

