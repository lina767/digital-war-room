import { useSearchParams } from "react-router-dom";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { Mail } from "lucide-react";
import { newsletterUnsubscribe } from "@/lib/api";
import { SEO } from "@/components/SEO";
import { useAsyncTokenResult } from "@/hooks/useAsyncTokenResult";
import { NewsletterTokenContent } from "@/components/newsletter/NewsletterTokenContent";

export default function NewsletterUnsubscribe() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const { status, message } = useAsyncTokenResult(
    token,
    "Invalid or expired unsubscribe link.",
    newsletterUnsubscribe,
  );

  return (
    <>
      <SEO
        title="Unsubscribe from Newsletter — Digital War Room"
        description="Manage your Digital War Room newsletter subscription preferences."
        path="/newsletter/unsubscribe"
        noindex
        breadcrumbs={[
          { name: "Home", url: "https://digital-war-room.com/" },
          { name: "Newsletter", url: "https://digital-war-room.com/newsletter" },
          { name: "Unsubscribe", url: "https://digital-war-room.com/newsletter/unsubscribe" },
        ]}
      />
      <ContentPageLayout
        label="NEWSLETTER"
        title="Unsubscribe"
        icon={<Mail className="h-5 w-5 text-muted-foreground" />}
        maxWidth="md"
      >
        <NewsletterTokenContent
          status={status}
          message={message}
          loadingLabel="Processing…"
          successFallback="You have been unsubscribed."
          showDailyBriefingLink={false}
        />
      </ContentPageLayout>
    </>
  );
}
