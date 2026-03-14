import { useState } from "react";
import { Heart } from "lucide-react";
import { ContentPageLayout } from "@/components/ContentPageLayout";
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
    <ContentPageLayout
      label="SUPPORT"
      title="Support the Mission"
      icon={<Heart className="h-5 w-5 text-primary" />}
      description="This project is intentionally free and open: no paywall, no partisan framing, no sensationalism — just structured insights that anyone can use. To keep the Digital War Room online and up to date, I need help covering the basic operating costs (API usage, including the Claude API: Haiku and Sonnet). One-time donation via Stripe. You will be redirected to Stripe's secure checkout page."
      maxWidth="2xl"
    >
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
    </ContentPageLayout>
  );
};

export default Support;
