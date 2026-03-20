import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { newsletterSubscribe } from "@/lib/api";

interface NewsletterSubscribeFormProps {
  /** Optional conflict preselected (e.g. from daily briefing page). */
  defaultConflict?: string;
  /** Compact layout (single row) vs stacked. */
  compact?: boolean;
}

export function NewsletterSubscribeForm({ defaultConflict = "Iran", compact }: NewsletterSubscribeFormProps) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) {
      toast.error("Please enter your email address.");
      return;
    }
    setLoading(true);
    try {
      const res = await newsletterSubscribe({ email: trimmed, conflict: defaultConflict || "Iran" });
      toast.success(`${res.message} If you don't see it, check Spam/Promotions.`);
      setEmail("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Subscription failed.");
    } finally {
      setLoading(false);
    }
  };

  if (compact) {
    return (
      <form onSubmit={handleSubmit} className="flex flex-wrap items-center gap-2">
        <Input
          type="email"
          placeholder="your@email.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="max-w-[220px]"
          disabled={loading}
          required
        />
        <Button type="submit" disabled={loading}>
          {loading ? "Subscribing…" : "Subscribe to daily briefing"}
        </Button>
      </form>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 max-w-md">
      <div>
        <label htmlFor="newsletter-email" className="block text-sm font-medium mb-1">
          Email
        </label>
        <Input
          id="newsletter-email"
          type="email"
          placeholder="your@email.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={loading}
          required
        />
      </div>
      <Button type="submit" disabled={loading}>
        {loading ? "Subscribing…" : "Subscribe to daily briefing"}
      </Button>
    </form>
  );
}
