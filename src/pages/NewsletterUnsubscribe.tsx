import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { Mail } from "lucide-react";
import { newsletterUnsubscribe } from "@/lib/api";
import { SEO } from "@/components/SEO";

export default function NewsletterUnsubscribe() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("Invalid or expired unsubscribe link.");
      return;
    }
    newsletterUnsubscribe(token)
      .then((res) => {
        setStatus("success");
        setMessage(res.message);
      })
      .catch((err) => {
        setStatus("error");
        setMessage(err instanceof Error ? err.message : "Unsubscribe failed.");
      });
  }, [token]);

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
        <div className="space-y-4 text-sm">
          {status === "loading" && <p className="text-muted-foreground">Processing…</p>}
          {status === "success" && (
            <p className="text-foreground">{message || "You have been unsubscribed."}</p>
          )}
          {status === "error" && <p className="text-destructive">{message}</p>}
          <p>
            <Link to="/" className="text-primary hover:underline">
              Return to Dashboard
            </Link>
          </p>
        </div>
      </ContentPageLayout>
    </>
  );
}
