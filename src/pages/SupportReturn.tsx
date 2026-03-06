import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, CheckCircle } from "lucide-react";
import { getApiBase } from "@/lib/api";

type Status = "loading" | "complete" | "open" | "error";

const SupportReturn = () => {
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get("session_id");
  const [status, setStatus] = useState<Status>("loading");
  const [customerEmail, setCustomerEmail] = useState<string>("");

  useEffect(() => {
    if (!sessionId) {
      setStatus("error");
      return;
    }
    const base = getApiBase();
    fetch(`${base}/api/session-status?session_id=${encodeURIComponent(sessionId)}`)
      .then((res) => res.json())
      .then((data: { status?: string; customer_email?: string }) => {
        if (data.status === "complete") {
          setStatus("complete");
          setCustomerEmail(data.customer_email ?? "");
        } else if (data.status === "open") {
          setStatus("open");
        } else {
          setStatus("error");
        }
      })
      .catch(() => setStatus("error"));
  }, [sessionId]);

  if (status === "open") {
    return (
      <div className="min-h-screen bg-background text-foreground flex flex-col items-center justify-center p-6">
        <p className="text-muted-foreground text-sm mb-4">Payment was not completed. You can try again.</p>
        <Link to="/support" className="text-primary hover:underline text-sm">Back to Support</Link>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="min-h-screen bg-background text-foreground flex flex-col items-center justify-center p-6">
        <p className="text-muted-foreground text-sm mb-4">Something went wrong. Please try again from the Support page.</p>
        <Link to="/support" className="text-primary hover:underline text-sm">Back to Support</Link>
      </div>
    );
  }

  if (status === "complete") {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <div className="max-w-xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
          <div className="mb-6">
            <Link
              to="/"
              className="inline-flex items-center gap-2 text-xs sm:text-sm text-muted-foreground hover:text-foreground transition-colors touch-manipulation"
            >
              <ArrowLeft className="h-4 w-4" />
              <span>Back to dashboard</span>
            </Link>
          </div>
          <section className="rounded-lg border border-border bg-card/40 p-6 sm:p-8 text-center">
            <CheckCircle className="h-12 w-12 text-primary mx-auto mb-4" aria-hidden />
            <h1 className="text-xl sm:text-2xl font-semibold tracking-tight mb-2">Thank you</h1>
            <p className="text-sm text-muted-foreground">
              Your support is greatly appreciated.
              {customerEmail && (
                <> A confirmation was sent to <span className="text-foreground font-medium">{customerEmail}</span>.</>
              )}
            </p>
            <Link
              to="/"
              className="inline-block mt-6 text-sm font-medium text-primary hover:text-primary/90 hover:underline"
            >
              Return to dashboard
            </Link>
          </section>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col items-center justify-center p-6">
      <p className="text-muted-foreground text-sm">Loading…</p>
    </div>
  );
};

export default SupportReturn;
