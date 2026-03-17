import { ContentPageLayout } from "@/components/ContentPageLayout";
import { SEO } from "@/components/SEO";

const Impressum = () => {
  return (
    <>
      <SEO
        title="Impressum — Digital War Room"
        description="Legal notice and contact information for Digital War Room (Angaben gemäß § 5 TMG)."
        path="/impressum"
        lang="de"
      />
      <ContentPageLayout label="LEGAL NOTICE" title="Impressum" maxWidth="3xl">
      <div className="space-y-6 text-sm sm:text-[15px] text-muted-foreground">
        <section>
          <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
            Angaben gemäß § 5 TMG
          </h2>
          <p className="leading-relaxed">
            Lina Braun<br />
            Leitershofer Straße 40<br />
            86157 Augsburg
          </p>
        </section>

        <section>
          <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
            Kontakt
          </h2>
          <p className="leading-relaxed">
            E-Mail:{" "}
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
            Verantwortlich für den Inhalt
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
