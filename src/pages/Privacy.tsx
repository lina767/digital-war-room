import { Shield } from "lucide-react";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { SEO } from "@/components/SEO";
import { TITLE_PRIVACY, DESCRIPTION_PRIVACY } from "@/lib/seoCopy";

const CONTACT = {
  name: "Lina Braun",
  address: "Leitershofer Straße 40",
  city: "86157 Augsburg",
  email: "social@linabraun.eu",
};

const Privacy = () => {
  return (
    <>
      <SEO
        title={TITLE_PRIVACY}
        description={DESCRIPTION_PRIVACY}
        path="/privacy"
        breadcrumbs={[
          { name: "Home", url: "https://digital-war-room.com/" },
          { name: "Privacy Policy", url: "https://digital-war-room.com/privacy" },
        ]}
      />
      <ContentPageLayout
        label="LEGAL"
        title="Privacy Policy"
        icon={<Shield className="h-5 w-5 text-muted-foreground" />}
        maxWidth="3xl"
      >
        <div className="space-y-8 text-sm sm:text-[15px] text-muted-foreground leading-relaxed">
          <section>
            <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
              1. Controller
            </h2>
            <p>
              The controller responsible for data processing within the meaning of the GDPR is:
              <br /><br />
              {CONTACT.name}<br />
              {CONTACT.address}<br />
              {CONTACT.city}<br />
              Email:{" "}
              <a href={`mailto:${CONTACT.email}`} className="text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">
                {CONTACT.email}
              </a>
            </p>
          </section>

          <section>
            <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
              2. Data we collect
            </h2>
            <p>
              No account data or personal user accounts are collected. When you use the platform, access data (e.g. IP address, date/time, pages accessed, browser type) may be transmitted to our hosting or CDN provider. The platform may use analytics tools (e.g. Vercel Analytics) that collect anonymised usage data. The platform’s analysis features use AI (e.g. language models for synthesising situation reports); only the open data used for conflict analysis is processed there, not your personal data.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
              3. Newsletter
            </h2>
            <p>
              If you subscribe to the Daily Briefing newsletter, we store your email address for the sole purpose of
              sending you the daily briefing email. We use double opt-in: you must confirm your subscription via the
              link in the confirmation email. For delivery, we use Resend as email service provider (processor). You
              can unsubscribe at any time via the link in each newsletter. We do not sell your email address.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
              4. Purpose and legal basis
            </h2>
            <p>
              Processing is carried out to operate the website, provide the analysis and dashboard features (including
              AI-assisted synthesis), and ensure security and stability. The legal basis is in particular Art. 6(1)(f)
              GDPR (legitimate interest in operating the platform). For newsletter delivery, the legal basis is your
              consent under Art. 6(1)(a) GDPR, which you can withdraw at any time by unsubscribing.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
              5. Storage period
            </h2>
            <p>
              Personal data are retained only for as long as necessary for the purposes stated above or as required by
              law. Newsletter subscription data are kept until you unsubscribe. Access and log data are generally
              deleted or anonymised after a short period.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
              6. Your rights
            </h2>
            <p>
              You have the right to access (Art. 15 GDPR), rectification (Art. 16 GDPR), erasure (Art. 17 GDPR), restriction of processing (Art. 18 GDPR), data portability (Art. 20 GDPR) and to object (Art. 21 GDPR). Where processing is based on consent, you may withdraw that consent at any time with effect for the future. You also have the right to lodge a complaint with a supervisory authority (Art. 77 GDPR).
            </p>
          </section>

          <section>
            <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
              7. Cookies, AI and third-party services
            </h2>
            <p>
              The platform may use technically necessary cookies or local storage (e.g. for preferences). For AI-assisted evaluation and synthesis of conflict analyses, third-party services (e.g. providers of language models) are used; the data processed there relates to the platform’s analysis data, not to your personal data. Hosting and analytics services (e.g. Vercel) may also be used. The respective privacy policies of those providers apply to data processed by them.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
              8. Contact
            </h2>
            <p>
              For any questions regarding data protection, please contact:{" "}
              <a href={`mailto:${CONTACT.email}`} className="text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">
                {CONTACT.email}
              </a>
            </p>
          </section>
        </div>
      </ContentPageLayout>
    </>
  );
};

export default Privacy;
