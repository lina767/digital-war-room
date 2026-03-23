interface BriefingFooterProps {
  generatedAt: Date;
  version: string;
}

export function BriefingFooter({ generatedAt, version }: BriefingFooterProps) {
  return (
    <footer className="mt-6 border-t border-[var(--border-subtle)] pt-4 text-xs text-[var(--text-secondary)]">
      <p className="classification-banner briefing-mono mb-2">UNCLASSIFIED // OPEN SOURCE</p>
      <p>
        Methodology: Multi-agent synthesis via Claude Sonnet supervisor. Individual agents blend LLM extraction with
        rule-based scoring.
      </p>
      <p className="briefing-mono mt-2">
        Generated: {generatedAt.toISOString()} | {version}
      </p>
      <p className="mt-1">Digital War Room – digital-war-room.com</p>
    </footer>
  );
}
