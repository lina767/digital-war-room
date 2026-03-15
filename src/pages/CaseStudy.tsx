import { Link } from "react-router-dom";
import { ContentPageLayout } from "@/components/ContentPageLayout";

const CaseStudy = () => {
  return (
    <ContentPageLayout
      label="CASE STUDY"
      title="Example: Iran and the Strait of Hormuz"
      description="How a single analysis run combines 12 intelligence streams into one escalation assessment and BLUF summary. This page explains the flow from agent outputs to supervisor synthesis."
      maxWidth="5xl"
    >
      <div className="space-y-10 sm:space-y-12">
        <section className="space-y-4">
          <h2 className="text-lg sm:text-xl font-semibold tracking-tight">
            What the case study illustrates
          </h2>
          <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
            For the conflict &quot;Iran&quot;, the platform runs all 12 agents in parallel. Each agent returns a score and structured data (e.g. FININT: Brent price and Polymarket odds; SIGINT: aircraft and ships in the Persian Gulf; NEWS: headline sentiment; CHOKEPOINT: Hormuz status and tanker counts). The supervisor then receives a compact payload of these results and produces a single <code className="text-foreground/80">escalation_score</code> (0–100), <code className="text-foreground/80">threat_level</code>, <code className="text-foreground/80">key_findings</code>, <code className="text-foreground/80">scenarios</code> and a short BLUF <code className="text-foreground/80">summary</code>.
          </p>
        </section>

        <section className="space-y-4">
          <h2 className="text-lg sm:text-xl font-semibold tracking-tight">
            Agent outputs that feed the synthesis
          </h2>
          <ul className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl space-y-2 list-disc list-inside">
            <li>
              <strong className="text-foreground">FININT</strong> – Oil prices (Brent/WTI), Polymarket conflict-related markets, Fear &amp; Greed; combined into a financial escalation score.
            </li>
            <li>
              <strong className="text-foreground">SIGINT</strong> – Military aircraft (e.g. ADS-B), naval vessels in the Gulf, conflict intel from RSS (BBC, DW, Al Jazeera, think tanks). Feeds geofencing (ships in sanctions zones) and AIS anomaly detection.
            </li>
            <li>
              <strong className="text-foreground">NEWS</strong> – Articles and sentiment; headlines surface in the ticker and key findings.
            </li>
            <li>
              <strong className="text-foreground">GEOINT</strong> – NASA FIRMS thermal anomalies (hotspots); overlayed on the map and used by PROXIMITY for strike–civilian correlation.
            </li>
            <li>
              <strong className="text-foreground">CHOKEPOINT</strong> – Strait of Hormuz (and Bab el-Mandeb, Suez) status, tanker counts, military vessels, disruption risk. Enriched with SIGINT ships and ENERGY (Brent impact).
            </li>
            <li>
              <strong className="text-foreground">ENERGY</strong> – AGSI+ gas storage, commodities, FAO Food Price Index. For Iran, a &quot;global impact&quot; note when oil moves sharply (Hormuz risk premium).
            </li>
            <li>
              <strong className="text-foreground">DIPLO</strong> – OFAC SDN, EU sanctions, UN/ICJ news; feeds compliance risk score and key findings.
            </li>
            <li>
              <strong className="text-foreground">PROXIMITY</strong> – FIRMS thermal events correlated with OSM schools/hospitals; human-shield / collateral risk labels.
            </li>
            <li>
              <strong className="text-foreground">Signal Framework (narrative)</strong> – State vs. exile media comparison (IRNA/Fars vs. Iran International/Radio Farda); synthesis probability and credibility gaps.
            </li>
          </ul>
        </section>

        <section className="space-y-4">
          <h2 className="text-lg sm:text-xl font-semibold tracking-tight">
            From scores to threat level and key findings
          </h2>
          <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
            The supervisor computes a <strong className="text-foreground">weighted combined score</strong> (see{" "}
            <Link to="/methodology" className="text-primary hover:underline">Methodology</Link>
            {" "}for weights). If the supervisor LLM is enabled, it receives this payload and returns a JSON with <code className="text-foreground/80">threat_level</code>, <code className="text-foreground/80">key_findings</code>, <code className="text-foreground/80">scenarios</code> and <code className="text-foreground/80">summary</code>. The backend then <strong className="text-foreground">appends</strong> agent-level findings to <code className="text-foreground/80">key_findings</code> (e.g. &quot;SIGINT – 3 warship(s) in region&quot;, &quot;CHOKEPOINT – Hormuz: OPEN (risk 45/100)&quot;, NEWS headlines, GEOINT hotspots, TECHINT IODA events, etc.). So the final briefing is a mix of LLM synthesis and rule-based agent snippets. When the LLM fails or is disabled, a rule-based fallback maps the combined score to MINIMAL/LOW/ELEVATED/HIGH/CRITICAL and leaves key findings to be filled from agent data only.
          </p>
        </section>

        <section className="space-y-4">
          <h2 className="text-lg sm:text-xl font-semibold tracking-tight">
            Try it on the dashboard
          </h2>
          <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
            Open the <Link to="/" className="text-primary hover:underline">dashboard</Link> and select conflict &quot;Iran&quot;. The left panel shows all agents and their data sources; the right panel shows the updated briefing, key findings, Global Impact (when ENERGY indicates oil/Hormuz risk), and the escalation timeline. The map overlays thermal anomalies, aircraft and ships. Sanctions Compliance uses SIGINT (ships/aircraft) and DIPLO (OFAC/EU) for geofencing and risk score. All of this comes from one analysis run that you can trigger via &quot;Refresh analysis&quot; (or wait for the automatic daily run).
          </p>
        </section>
      </div>
    </ContentPageLayout>
  );
};

export default CaseStudy;
