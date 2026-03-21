import { Link } from "react-router-dom";
import type { AsyncTokenStatus } from "@/hooks/useAsyncTokenResult";

interface NewsletterTokenContentProps {
  status: AsyncTokenStatus;
  message: string;
  loadingLabel: string;
  successFallback: string;
  /** Confirm page links to Daily Briefing; unsubscribe only needs home. */
  showDailyBriefingLink?: boolean;
}

export function NewsletterTokenContent({
  status,
  message,
  loadingLabel,
  successFallback,
  showDailyBriefingLink = true,
}: NewsletterTokenContentProps) {
  return (
    <div className="space-y-4 text-sm">
      {status === "loading" && <p className="text-muted-foreground">{loadingLabel}</p>}
      {status === "success" && <p className="text-foreground">{message || successFallback}</p>}
      {status === "error" && <p className="text-destructive">{message}</p>}
      <p>
        <Link to="/" className="text-primary hover:underline">
          Return to Dashboard
        </Link>
        {showDailyBriefingLink && (
          <>
            {" · "}
            <Link to="/daily-briefing" className="text-primary hover:underline">
              Daily Briefing
            </Link>
          </>
        )}
      </p>
    </div>
  );
}
