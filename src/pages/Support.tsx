import { useCallback } from "react";
import { Link } from "react-router-dom";
import { loadStripe } from "@stripe/stripe-js";
import { EmbeddedCheckoutProvider, EmbeddedCheckout } from "@stripe/react-stripe-js";
import { ArrowLeft, Heart } from "lucide-react";
import { getApiBase } from "@/lib/api";

const stripePublishableKey = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY as string | undefined;

const stripePromise = stripePublishableKey ? loadStripe(stripePublishableKey) : null;

const Support = () => {
  const fetchClientSecret = useCallback(async () => {
    const base = getApiBase();
    const res = await fetch(`${base}/api/create-checkout-session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        return_url_origin: typeof window !== "undefined" ? window.location.origin : undefined,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error((err as { detail?: string })?.detail ?? res.statusText);
    }
    const data = (await res.json()) as { clientSecret: string };
    return data.clientSecret;
  }, []);

  if (!stripePublishableKey) {
    return (
      <div className="min-h-screen bg-background text-foreground flex flex-col items-center justify-center p-6">
        <p className="text-muted-foreground text-sm mb-4">Stripe is not configured (VITE_STRIPE_PUBLISHABLE_KEY).</p>
        <Link to="/" className="text-primary hover:underline text-sm">Back to dashboard</Link>
      </div>
    );
  }

  if (!stripePromise) {
    return (
      <div className="min-h-screen bg-background text-foreground flex flex-col items-center justify-center p-6">
        <p className="text-muted-foreground text-sm">Loading…</p>
      </div>
    );
  }

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
            Support me
          </h1>
          <p className="text-sm text-muted-foreground mt-2">
            One-time donation via Stripe. Complete the form below to pay securely.
          </p>
        </header>

        <div className="rounded-lg border border-border bg-card/40 overflow-hidden">
          <EmbeddedCheckoutProvider
            stripe={stripePromise}
            options={{ fetchClientSecret }}
          >
            <EmbeddedCheckout />
          </EmbeddedCheckoutProvider>
        </div>
      </div>
    </div>
  );
};

export default Support;
