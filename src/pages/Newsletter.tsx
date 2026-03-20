import { ContentPageLayout } from "@/components/ContentPageLayout";
import { Mail } from "lucide-react";
import { Link } from "react-router-dom";
import { NewsletterSubscribeForm } from "@/components/newsletter/NewsletterSubscribeForm";
import { SEO } from "@/components/SEO";

export default function Newsletter() {
  return (
    <>
      <SEO
        title="Daily Briefing Newsletter — Digital War Room"
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
          <p className="text-muted-foreground leading-relaxed">
            Get the latest situation report every day in your inbox. After you subscribe, we send a confirmation email (double opt-in). Only confirmed addresses receive the daily briefing. You can unsubscribe at any time via the link in each email.
          </p>
          <p className="text-muted-foreground text-xs">
            If the confirmation email does not arrive within a few minutes, check your Spam or Promotions folder.
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
