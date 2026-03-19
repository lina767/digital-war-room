import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CONFLICT_OPTIONS } from "@/components/dashboard/conflictData";
import { newsletterSubscribe } from "@/lib/api";

interface NewsletterSubscribeFormProps {
  /** Optional conflict preselected (e.g. from daily briefing page). */
  defaultConflict?: string;
  /** Compact layout (single row) vs stacked. */
  compact?: boolean;
}

export function NewsletterSubscribeForm({ defaultConflict = "Iran", compact }: NewsletterSubscribeFormProps) {
  const [email, setEmail] = useState("");
  const [conflict, setConflict] = useState(defaultConflict);
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
      await newsletterSubscribe({ email: trimmed, conflict: conflict || "Iran" });
      toast.success("Please check your inbox to confirm your subscription.");
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
        <select
          value={conflict}
          onChange={(e) => setConflict(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          disabled={loading}
        >
          {CONFLICT_OPTIONS.map((o) => (
            <option key={o.id} value={o.apiValue}>
              {o.label}
            </option>
          ))}
        </select>
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
      <div>
        <label htmlFor="newsletter-conflict" className="block text-sm font-medium mb-1">
          Conflict (optional)
        </label>
        <select
          id="newsletter-conflict"
          value={conflict}
          onChange={(e) => setConflict(e.target.value)}
          className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
          disabled={loading}
        >
          {CONFLICT_OPTIONS.map((o) => (
            <option key={o.id} value={o.apiValue}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <Button type="submit" disabled={loading}>
        {loading ? "Subscribing…" : "Subscribe to daily briefing"}
      </Button>
    </form>
  );
}
