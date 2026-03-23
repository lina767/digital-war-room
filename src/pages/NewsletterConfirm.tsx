import { useSearchParams } from "react-router-dom";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { Mail } from "lucide-react";
import { newsletterConfirm } from "@/lib/api";
import { SEO } from "@/components/SEO";
import { useAsyncTokenResult } from "@/hooks/useAsyncTokenResult";
import { NewsletterTokenContent } from "@/components/newsletter/NewsletterTokenContent";

export default function NewsletterConfirm() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const { status, message } = useAsyncTokenResult(
    token,
    "Invalid or expired confirmation link.",
    newsletterConfirm,
  );

  return (
    <>
      <SEO
        title="Confirm Newsletter Subscription – Digital War Room"
        description="Confirm your newsletter subscription for the Digital War Room daily briefing."
        path="/newsletter/confirm"
        noindex
        breadcrumbs={[
          { name: "Home", url: "https://digital-war-room.com/" },
          { name: "Newsletter", url: "https://digital-war-room.com/newsletter" },
          { name: "Confirm", url: "https://digital-war-room.com/newsletter/confirm" },
        ]}
      />
      <ContentPageLayout
        label="NEWSLETTER"
        title="Confirm subscription"
        icon={<Mail className="h-5 w-5 text-muted-foreground" />}
        maxWidth="md"
      >
        <NewsletterTokenContent
          status={status}
          message={message}
          loadingLabel="Confirming…"
          successFallback="You're subscribed. You'll receive the daily briefing by email."
        />
      </ContentPageLayout>
    </>
  );
}
