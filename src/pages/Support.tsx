import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Heart } from "lucide-react";
import { getApiBase } from "@/lib/api";
import { Button } from "@/components/ui/button";

const Support = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCheckout = async () => {
    setError(null);
    setLoading(true);
    try {
      const base = getApiBase();
      const res = await fetch(`${base}/api/create-checkout-session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          return_url_origin: typeof window !== "undefined" ? window.location.origin : undefined,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error((data as { detail?: string }).detail ?? res.statusText ?? "Checkout could not be started.");
      }
      const url = (data as { url?: string }).url;
      if (url) {
        window.location.href = url;
        return;
      }
      throw new Error("No checkout URL returned.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
        <div className="mb-6 flex items-center justify-between gap-3">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-xs sm:text-sm text-muted-foreground hover:text-foreground transition-colors touch-manipulation"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Back to dashboard</span>
          </Link>
        </div>

        <header className="mb-6 sm:mb-8">
          <p className="font-mono text-[11px] sm:text-xs tracking-[0.28em] text-muted-foreground uppercase mb-2">
            SUPPORT
          </p>
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Heart className="h-5 w-5 text-primary" aria-hidden />
            Support the Mission
          </h1>
          <p className="text-sm text-muted-foreground mt-2">
            One-time donation via Stripe. You will be redirected to Stripe’s secure checkout page.
          </p>
        </header>

        <div className="rounded-lg border border-border bg-card/40 p-6 sm:p-8">
          {error && (
            <p className="text-sm text-destructive mb-4" role="alert">
              {error}
            </p>
          )}
          <Button
            onClick={handleCheckout}
            disabled={loading}
            className="w-full sm:w-auto"
          >
            {loading ? "Redirecting…" : "Support the Mission"}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default Support;
