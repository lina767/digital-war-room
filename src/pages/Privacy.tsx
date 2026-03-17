import { useState } from "react";
import { Shield } from "lucide-react";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { SEO } from "@/components/SEO";

const CONTACT = {
  name: "Lina Braun",
  address: "Leitershofer Straße 40",
  city: "86157 Augsburg",
  email: "social@linabraun.eu",
};

const Privacy = () => {
  const [lang, setLang] = useState<"de" | "en">("de");

  return (
    <>
      <SEO
        title="Privacy Policy — Digital War Room"
        description="Privacy policy and data protection information for Digital War Room. Available in German and English."
        path="/privacy"
      />
      <ContentPageLayout
      label={lang === "de" ? "RECHTLICHES" : "LEGAL"}
      title={lang === "de" ? "Datenschutzerklärung" : "Privacy Policy"}
      icon={<Shield className="h-5 w-5 text-muted-foreground" />}
      maxWidth="3xl"
    >
      <div className="mb-6 flex items-center justify-end gap-2">
        <span className="text-xs text-muted-foreground font-mono hidden sm:inline">Language:</span>
        <div className="flex rounded-md border border-border overflow-hidden">
          <button
            type="button"
            onClick={() => setLang("de")}
            className={`px-3 py-1.5 text-xs font-medium transition-colors touch-manipulation ${
              lang === "de"
                ? "bg-primary text-primary-foreground"
                : "bg-background text-muted-foreground hover:text-foreground hover:bg-muted/50"
            }`}
          >
            Deutsch
          </button>
          <button
            type="button"
            onClick={() => setLang("en")}
            className={`px-3 py-1.5 text-xs font-medium transition-colors touch-manipulation ${
              lang === "en"
                ? "bg-primary text-primary-foreground"
                : "bg-background text-muted-foreground hover:text-foreground hover:bg-muted/50"
            }`}
          >
            English
          </button>
        </div>
      </div>

      <div className="space-y-8 text-sm sm:text-[15px] text-muted-foreground leading-relaxed">
          {lang === "de" ? (
            <>
              <section>
                <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
                  1. Verantwortliche Stelle
                </h2>
                <p>
                  Verantwortlich für die Datenverarbeitung im Sinne der DSGVO ist:
                  <br /><br />
                  {CONTACT.name}<br />
                  {CONTACT.address}<br />
                  {CONTACT.city}<br />
                  E-Mail:{" "}
                  <a href={`mailto:${CONTACT.email}`} className="text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">
                    {CONTACT.email}
                  </a>
                </p>
              </section>

              <section>
                <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
                  2. Erhobene Daten
                </h2>
                <p>
                  Es werden keine Kontodaten oder personenbezogenen Nutzerkonten erhoben. Beim Besuch der Plattform können technisch bedingt Zugriffsdaten (z. B. IP-Adresse, Datum/Uhrzeit, abgerufene Seiten, Browsertyp) an den Hosting- bzw. CDN-Anbieter übermittelt werden. Die Plattform kann Analysetools (z. B. Vercel Analytics) einsetzen, die anonymisierte Nutzungsdaten erfassen. Die Analysefunktionen der Plattform arbeiten mit KI (z. B. Sprachmodelle zur Synthese von Lageberichten); dabei werden ausschließlich die für die Konfliktanalyse eingebundenen offenen Daten verarbeitet, nicht Ihre personenbezogenen Daten.
                </p>
              </section>

              <section>
                <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
                  3. Zweck und Rechtsgrundlage
                </h2>
                <p>
                  Die Verarbeitung dient dem Betrieb der Webseite, der Bereitstellung der Analyse- und Dashboard-Funktionen (inkl. KI-gestützter Synthese) sowie der Gewährleistung von Sicherheit und Stabilität. Rechtsgrundlage ist vor allem Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse am Betrieb der Plattform).
                </p>
              </section>

              <section>
                <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
                  4. Speicherdauer
                </h2>
                <p>
                  Personenbezogene Daten werden nur so lange gespeichert, wie es für die genannten Zwecke erforderlich ist oder gesetzliche Aufbewahrungspflichten bestehen. Zugriffs- und Protokolldaten werden in der Regel nach kurzer Frist gelöscht oder anonymisiert.
                </p>
              </section>

              <section>
                <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
                  5. Ihre Rechte
                </h2>
                <p>
                  Sie haben das Recht auf Auskunft (Art. 15 DSGVO), Berichtigung (Art. 16 DSGVO), Löschung (Art. 17 DSGVO), Einschränkung der Verarbeitung (Art. 18 DSGVO), Datenübertragbarkeit (Art. 20 DSGVO) und Widerspruch (Art. 21 DSGVO). Sofern die Verarbeitung auf einer Einwilligung beruht, können Sie diese jederzeit mit Wirkung für die Zukunft widerrufen. Sie haben zudem das Recht, sich bei einer Aufsichtsbehörde zu beschweren (Art. 77 DSGVO).
                </p>
              </section>

              <section>
                <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
                  6. Cookies, KI und externe Dienste
                </h2>
                <p>
                  Die Plattform kann technisch notwendige Cookies bzw. Speicherzugriffe (z. B. für Einstellungen) verwenden. Für die KI-gestützte Auswertung und Synthese der Konfliktanalysen kommen Dienste Dritter (z. B. Anbieter von Sprachmodellen) zum Einsatz; die dort verarbeiteten Inhalte beziehen sich auf die Analyse-Daten der Plattform, nicht auf Ihre personenbezogenen Daten. Darüber hinaus können Hosting- und Analysedienste (z. B. Vercel) genutzt werden. Für die bei Dritten verarbeiteten Daten gelten jeweils deren Datenschutzbestimmungen.
                </p>
              </section>

              <section>
                <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
                  7. Kontakt
                </h2>
                <p>
                  Für Fragen zum Datenschutz wenden Sie sich bitte an:{" "}
                  <a href={`mailto:${CONTACT.email}`} className="text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">
                    {CONTACT.email}
                  </a>
                </p>
              </section>
            </>
          ) : (
            <>
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
                  3. Purpose and legal basis
                </h2>
                <p>
                  Processing is carried out to operate the website, provide the analysis and dashboard features (including AI-assisted synthesis), and ensure security and stability. The legal basis is in particular Art. 6(1)(f) GDPR (legitimate interest in operating the platform).
                </p>
              </section>

              <section>
                <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
                  4. Storage period
                </h2>
                <p>
                  Personal data are retained only for as long as necessary for the purposes stated above or as required by law. Access and log data are generally deleted or anonymised after a short period.
                </p>
              </section>

              <section>
                <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
                  5. Your rights
                </h2>
                <p>
                  You have the right to access (Art. 15 GDPR), rectification (Art. 16 GDPR), erasure (Art. 17 GDPR), restriction of processing (Art. 18 GDPR), data portability (Art. 20 GDPR) and to object (Art. 21 GDPR). Where processing is based on consent, you may withdraw that consent at any time with effect for the future. You also have the right to lodge a complaint with a supervisory authority (Art. 77 GDPR).
                </p>
              </section>

              <section>
                <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
                  6. Cookies, AI and third-party services
                </h2>
                <p>
                  The platform may use technically necessary cookies or local storage (e.g. for preferences). For AI-assisted evaluation and synthesis of conflict analyses, third-party services (e.g. providers of language models) are used; the data processed there relates to the platform’s analysis data, not to your personal data. Hosting and analytics services (e.g. Vercel) may also be used. The respective privacy policies of those providers apply to data processed by them.
                </p>
              </section>

              <section>
                <h2 className="text-xs font-mono tracking-wider text-foreground uppercase mb-2">
                  7. Contact
                </h2>
                <p>
                  For any questions regarding data protection, please contact:{" "}
                  <a href={`mailto:${CONTACT.email}`} className="text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">
                    {CONTACT.email}
                  </a>
                </p>
              </section>
            </>
          )}
      </div>
    </ContentPageLayout>
    </>
  );
};

export default Privacy;
