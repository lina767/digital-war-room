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

const LAST_UPDATED = "26 March 2026";

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
            <p>
              Last updated: <strong className="text-foreground">{LAST_UPDATED}</strong>
            </p>
          </section>

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
              We do not offer personal user accounts. Depending on your use, we process:
              <br />
              - Technical access data (e.g. IP address, date/time, URL, user agent, referrer) through our
              hosting/CDN and server infrastructure.
              <br />
              - Newsletter data (email address and consent metadata for double opt-in) if you subscribe.
              <br />
              - Security and anti-abuse metadata (e.g. rate-limit or request integrity data) where required to
              protect the service.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
              3. Newsletter
            </h2>
            <p>
              If you subscribe to the Daily Briefing newsletter, we store your email address for the sole purpose of
              sending you the daily briefing email. We use double opt-in: you must confirm your subscription via the
              link in the confirmation email. For delivery, we use Resend as our processor. You can unsubscribe at any
              time via the link in each newsletter. We do not sell your email address.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
              4. Purpose and legal basis
            </h2>
            <p>
              Processing is carried out to operate the website, provide the analysis and dashboard features (including
              AI-assisted synthesis), and ensure security and stability. Legal bases are:
              <br />
              - Art. 6(1)(f) GDPR (legitimate interests) for secure and reliable operation, technical logs,
              performance monitoring, and abuse prevention.
              <br />
              - Art. 6(1)(a) GDPR (consent) for newsletter subscriptions (double opt-in), revocable at any time with
              effect for the future.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
              5. Storage period
            </h2>
            <p>
              We retain personal data only as long as necessary for the stated purposes or as required by law.
              Newsletter data are stored until you unsubscribe (plus any legally required proof periods for consent and
              dispatch). Technical log and security data are retained for a limited period and then deleted or
              anonymized.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
              6. Your rights
            </h2>
            <p>
              You have rights to access (Art. 15 GDPR), rectification (Art. 16 GDPR), erasure (Art. 17 GDPR),
              restriction (Art. 18 GDPR), portability (Art. 20 GDPR), and objection (Art. 21 GDPR). If processing is
              based on consent, you may withdraw consent at any time with effect for the future. You also have the
              right to lodge a complaint with a supervisory authority (Art. 77 GDPR).
            </p>
          </section>

          <section>
            <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
              7. Recipients, third countries, AI and analytics
            </h2>
            <p>
              We use service providers (processors) for hosting/CDN and operational services (including analytics and
              email delivery). Current providers include Vercel (hosting/analytics) and Resend (email delivery). Where
              providers process data outside the EU/EEA, transfers are based on appropriate safeguards (e.g. adequacy
              decisions or Standard Contractual Clauses), where applicable.
              <br /><br />
              The platform may use technically necessary storage mechanisms (such as local storage) to keep preferences
              or required app state. If analytics are enabled, they are used to improve reliability and product quality.
              <br /><br />
              AI services are used to process open-source intelligence content and generate analyses. We do not require
              account-based personal profiles for using core features.
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
