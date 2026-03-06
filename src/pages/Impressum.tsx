import { Link } from "react-router-dom";
import { ArrowLeft, FileText } from "lucide-react";

const Impressum = () => {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-10">
        <div className="mb-6 sm:mb-8 flex items-center justify-between gap-3">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-xs sm:text-sm text-muted-foreground hover:text-foreground transition-colors touch-manipulation"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Back to dashboard</span>
          </Link>
          <div className="hidden sm:flex items-center gap-2 text-xs text-muted-foreground font-mono">
            <span className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-border">
              <FileText className="h-3 w-3" />
            </span>
            <span>Impressum</span>
          </div>
        </div>

        <header className="mb-8 sm:mb-10">
          <p className="font-mono text-[11px] sm:text-xs tracking-[0.28em] text-muted-foreground uppercase mb-3">
            LEGAL NOTICE
          </p>
          <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight">
            Impressum
          </h1>
        </header>

        <main className="space-y-6 text-sm sm:text-[15px] text-muted-foreground">
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
        </main>
      </div>
    </div>
  );
};

export default Impressum;
