import { ContentPageLayout } from "@/components/ContentPageLayout";
import { Mail } from "lucide-react";
import { Link } from "react-router-dom";
import { NewsletterSubscribeForm } from "@/components/newsletter/NewsletterSubscribeForm";
import { SEO } from "@/components/SEO";

export default function Newsletter() {
  return (
    <>
      <SEO
        title="Daily Briefing Newsletter – Digital War Room"
        description="Subscribe to receive the Digital War Room daily intelligence briefing by email."
        path="/newsletter"
        breadcrumbs={[
          { name: "Home", url: "https://digital-war-room.com/" },
          { name: "Newsletter", url: "https://digital-war-room.com/newsletter" },
        ]}
      />
      <ContentPageLayout
        label="NEWSLETTER"
        title="Daily Briefing by email"
        icon={<Mail className="h-5 w-5 text-muted-foreground" />}
        maxWidth="md"
      >
        <div className="space-y-6 text-sm">
          <div className="rounded-lg border border-border bg-card/40 p-4 space-y-3">
            <p className="font-medium text-foreground">What you get each day</p>
            <ul className="list-disc pl-5 space-y-1.5 text-muted-foreground">
              <li>
                A short <strong className="text-foreground">BLUF</strong> executive summary plus a primary link into the live{" "}
                <Link to="/app/dashboard" className="text-primary hover:underline">
                  dashboard
                </Link>
                .
              </li>
              <li>
                A <strong className="text-foreground">daily infographic snapshot</strong> generated from the same briefing data as the site.
              </li>
              <li>
                <strong className="text-foreground">Key developments</strong> with individual tracked links into dashboard context (and a public{" "}
                <Link to="/daily-briefing" className="text-primary hover:underline">
                  daily briefing
                </Link>{" "}
                fallback).
              </li>
            </ul>
            <div className="pt-2">
              <p className="text-xs text-muted-foreground mb-2">
                Example of the infographic style you receive in email (representative layout; content changes daily).
              </p>
              <img
                src="/newsletter/example-infographic.png"
                alt="Example daily intelligence infographic snapshot from Digital War Room"
                className="w-full max-w-xl rounded-md border border-border"
                width={1200}
                height={630}
                loading="lazy"
                decoding="async"
              />
            </div>
          </div>
          <p className="text-muted-foreground leading-relaxed">
            Get the latest situation report every day in your inbox. After you subscribe, we send a confirmation email (double opt-in). Only confirmed addresses receive the daily briefing. You can unsubscribe at any time via the link in each email.
          </p>
          <p className="text-muted-foreground text-xs">
            If the confirmation email does not arrive within a few minutes, check your Spam or Promotions folder.
          </p>
          <p className="text-muted-foreground text-xs">
            Sharing the project? See the{" "}
            <Link to="/docs/documentation?doc=attention-playbook" className="text-primary hover:underline">
              Attention playbook
            </Link>{" "}
            for a one-line pitch, audience ladder, and content rhythm.
          </p>
          <NewsletterSubscribeForm />
          <p className="text-muted-foreground text-xs">
            By subscribing you agree to our{" "}
            <Link to="/privacy" className="text-primary hover:underline">
              Privacy Policy
            </Link>
            . We only use your email to send the daily briefing and do not share it with third parties.
          </p>
        </div>
      </ContentPageLayout>
    </>
  );
}
