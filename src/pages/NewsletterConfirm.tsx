import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { Mail } from "lucide-react";
import { newsletterConfirm } from "@/lib/api";

export default function NewsletterConfirm() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("Invalid or expired confirmation link.");
      return;
    }
    newsletterConfirm(token)
      .then((res) => {
        setStatus("success");
        setMessage(res.message);
      })
      .catch((err) => {
        setStatus("error");
        setMessage(err instanceof Error ? err.message : "Confirmation failed.");
      });
  }, [token]);

  return (
    <ContentPageLayout
      label="NEWSLETTER"
      title="Confirm subscription"
      icon={<Mail className="h-5 w-5 text-muted-foreground" />}
      maxWidth="md"
    >
      <div className="space-y-4 text-sm">
        {status === "loading" && <p className="text-muted-foreground">Confirming…</p>}
        {status === "success" && (
          <p className="text-foreground">{message || "You're subscribed. You'll receive the daily briefing by email."}</p>
        )}
        {status === "error" && <p className="text-destructive">{message}</p>}
        <p>
          <Link to="/" className="text-primary hover:underline">
            Return to Dashboard
          </Link>
          {" · "}
          <Link to="/daily-briefing" className="text-primary hover:underline">
            Daily Briefing
          </Link>
        </p>
      </div>
    </ContentPageLayout>
  );
}
