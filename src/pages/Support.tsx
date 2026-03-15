import { Heart } from "lucide-react";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { Button } from "@/components/ui/button";

const BUY_ME_A_COFFEE_URL = "https://buymeacoffee.com/digitalwarroom";

const Support = () => {
  return (
    <ContentPageLayout
      label="SUPPORT"
      title="Support the Mission"
      icon={<Heart className="h-5 w-5 text-primary" />}
      description="This project is intentionally free and open: no paywall, no partisan framing, no sensationalism — just structured insights that anyone can use. To keep the Digital War Room online and up to date, I need help covering the basic operating costs (API usage, including the Claude API: Haiku and Sonnet). Support via Buy Me a Coffee — one-time or monthly."
      maxWidth="2xl"
    >
      <div className="rounded-lg border border-border bg-card/40 p-6 sm:p-8">
        <Button
          asChild
          className="w-full sm:w-auto"
        >
          <a href={BUY_ME_A_COFFEE_URL} target="_blank" rel="noopener noreferrer">
            Support the Mission
          </a>
        </Button>
      </div>
    </ContentPageLayout>
  );
};

export default Support;
