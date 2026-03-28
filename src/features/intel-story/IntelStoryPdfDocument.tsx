import { Document, Page, Text, View, StyleSheet } from "@react-pdf/renderer";
import type { IntelStorySnapshot } from "./types";

const styles = StyleSheet.create({
  page: { padding: 24, fontSize: 10, color: "#111" },
  banner: { fontSize: 9, letterSpacing: 2, marginBottom: 10, color: "#666" },
  heading: { fontSize: 16, marginBottom: 6 },
  subheading: { fontSize: 12, marginTop: 10, marginBottom: 4 },
  line: { marginBottom: 4 },
  footer: { position: "absolute", bottom: 20, left: 24, right: 24, fontSize: 9, color: "#666" },
});

export function IntelStoryPdfDocument({ snapshot }: { snapshot: IntelStorySnapshot }) {
  const findings = snapshot.key_findings ?? [];
  return (
    <Document>
      <Page size="A4" style={styles.page}>
        <Text style={styles.banner}>UNCLASSIFIED // OPEN SOURCE</Text>
        <Text style={styles.heading}>Intel Story — Dashboard Export</Text>
        <Text style={styles.line}>
          Theater: {snapshot.conflict}
          {snapshot.threat_level != null ? ` | Threat: ${snapshot.threat_level}` : ""}
          {snapshot.escalation_score != null ? ` | Escalation: ${snapshot.escalation_score}` : ""}
        </Text>
        {snapshot.summary ? (
          <>
            <Text style={styles.subheading}>Summary</Text>
            <Text style={styles.line}>{snapshot.summary}</Text>
          </>
        ) : null}
        {snapshot.narrative_story ? (
          <>
            <Text style={styles.subheading}>Narrative</Text>
            <Text style={styles.line}>{snapshot.narrative_story}</Text>
          </>
        ) : null}
        {findings.length > 0 ? (
          <>
            <Text style={styles.subheading}>Key findings</Text>
            {findings.map((f, i) => (
              <Text key={i} style={styles.line}>
                • {f}
              </Text>
            ))}
          </>
        ) : null}
        <Text style={styles.footer}>
          Digital War Room | Exported {snapshot.exportedAt}
          {snapshot.analysis_run_id ? ` | Run ${snapshot.analysis_run_id}` : ""}
        </Text>
      </Page>
    </Document>
  );
}
