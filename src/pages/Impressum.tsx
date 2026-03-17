import { ContentPageLayout } from "@/components/ContentPageLayout";
import { SEO } from "@/components/SEO";

const Impressum = () => {
  return (
    <>
      <SEO
        title="Legal Notice — Digital War Room"
        description="Legal notice and contact information for Digital War Room."
        path="/impressum"
        breadcrumbs={[
          { name: "Home", url: "https://digital-war-room.com/" },
          { name: "Legal Notice", url: "https://digital-war-room.com/impressum" },
        ]}
      />
      <ContentPageLayout label="LEGAL" title="Legal Notice" maxWidth="3xl">
      <div className="space-y-6 text-sm sm:text-[15px] text-muted-foreground">
        <section>
          <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
            Information according to § 5 TMG (Germany)
          </h2>
          <p className="leading-relaxed">
            Lina Braun<br />
            Leitershofer Straße 40<br />
            86157 Augsburg
          </p>
        </section>

        <section>
          <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
            Contact
          </h2>
          <p className="leading-relaxed">
            Email:{" "}
            <a
              href="mailto:social@linabraun.eu"
              className="text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded"
            >
              social@linabraun.eu
            </a>
          </p>
        </section>

        <section>
          <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
            Responsible for content
          </h2>
          <p className="leading-relaxed">
            Lina Braun<br />
            Leitershofer Straße 40<br />
            86157 Augsburg
          </p>
        </section>
      </div>
    </ContentPageLayout>
    </>
  );
};

export default Impressum;
