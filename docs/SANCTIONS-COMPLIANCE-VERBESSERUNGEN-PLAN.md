# Sanctions Compliance – Vollständiger Verbesserungsplan (mit Feedback eingearbeitet)

Einheitlicher Plan für alle Sanctions-Compliance-Verbesserungen inkl. Erklärung/UI-Text, Document QA (klar gescoped), Geofencing/AIS-Verständlichkeit, Screening, Risk-Drill-Down, Export, technische Robustheit, Accessibility, Rate Limiting und Error Boundaries.

---

## A. Phase 1 – Copy, UI-Text, Quick Wins

Phase 1 ist der richtige Start. Alle Texte und Label-Bedeutungen laufen über eine **Single Source of Truth**.

### A.1 complianceCopy.ts als Single Source of Truth

- **Neue Datei** [src/lib/complianceCopy.ts](src/lib/complianceCopy.ts) mit:
  - **Intro/Disclaimer:** `COMPLIANCE_INTRO_SHORT`, `COMPLIANCE_INTRO_FULL`, `COMPLIANCE_DISCLAIMER`, optional `COMPLIANCE_GLOSSARY` (OFAC, SDN, Geofencing, AIS, Band, IRGC/EO).
  - **Match-Level-Labels:** `MATCH_LEVEL_LABELS: Record<string, string>` – für jeden Match-Level (EXACT, STRONG_FUZZY, WEAK_FUZZY, REVIEW) eine **kurze Nutzer-erklärende Bezeichnung**, z. B.:
    - EXACT: "Exact list match – name matches sanctioned entity directly."
    - STRONG_FUZZY: "Strong fuzzy match – high similarity, likely same entity (e.g. spelling/transliteration)."
    - WEAK_FUZZY: "Weak fuzzy match – moderate similarity; manual review recommended."
    - REVIEW: "Low similarity – flagged for review only; verify manually."
  - **Risk-Level-Labels (optional):** `RISK_LEVEL_LABELS` für LOW/MEDIUM/HIGH/CRITICAL mit kurzer Bedeutung (z. B. "CRITICAL: Direct list hit or very high exposure").
- **Panel:** Intro aus Copy, (i)-Tooltip mit FULL-Text, Disclaimer aus Copy. **Match-Badges** und Tooltips/Texte für Match-Level nutzen die Einträge aus `MATCH_LEVEL_LABELS` (nicht nur den Key anzeigen, sondern die Bedeutung), damit EXACT vs. STRONG_FUZZY etc. überall erklärt sind. Risk-Score-Band mit „(rough range)“; optional Risk-Level-Badge mit Label aus Copy.

### A.2 Glossary / Begriffe

- Tooltips bei OFAC SDN, EU Consolidated; optional aufklappbarer Block „Key terms“ aus `COMPLIANCE_GLOSSARY`. Daily Briefing Sektion „6. Sanctions Compliance“ mit gleicher Intro und Disclaimer aus Copy.

### A.3 Geofencing / AIS: „No alerts“-Text und SIGINT-Summary

- **No-alerts-Meldung:** Ersetzen durch Erklärung aus Copy (oder festem Text): Wann Alerts erscheinen (SIGINT-Positionen in Sanktionszonen; AIS-Anomalien); warum leer; Dark Activity braucht zwei aufeinanderfolgende Läufe. Optional (i)-Tooltip.
- **Backend:** Im Compliance-Block `sigint_window_summary` ergänzen: `aircraft_count`, `ships_count`, `in_sanctions_zones` (Supervisor).
- **Frontend:** Typ `sigint_window_summary?`; wenn vorhanden und keine Alerts: „This run: X aircraft, Y ships in conflict region; none in sanctions zones.“

### A.4 Quick Wins in Phase 1 (ca. 30 Min)

- **AbortController** in SanctionsSearch: `useRef<AbortController | null>(null)`; vor neuem Request `abortRef.current?.abort()`, neuer Controller, `fetch(..., { signal })`; bei Abort Loading zurücksetzen.
- **Retry:** Bei Fehler „Retry“-Button anzeigen; bei Klick gleiche Anfrage erneut senden.
- **Null-Safety:** Alle `compliance!.…!` in [CompliancePanel.tsx](src/components/dashboard/CompliancePanel.tsx) durch optional chaining (`compliance?.…`) ersetzen.
- **OFAC Recent Actions URL:** Nur `url.startsWith("https://")` als `href` setzen; sonst nur Text oder `href="#"`.

Diese Punkte blockieren nicht; sie können zusammen mit Copy/Intro in Phase 1 umgesetzt werden.

---

## B. Phase 2 – Document QA (klar gescoped) + ggf. nachziehen

### B.1 Scope Document QA

- **Vor dem Bau klären:** Was steht hinter `/api/documents/qa`?
  - **Variante A – RAG über OFAC-PDFs:** Eigenes Projekt (PDF-Ingest, Chunks, Embeddings, Retrieval). Soll **nicht** Phase-2-Scope blockieren; als separates Vorhaben planen.
  - **Variante B – Bestehenden Compliance-Kontext an Claude weiterreichen:** Nur aktuellen Kontext (z. B. OFAC-Sample, Risk-Score, Konflikt) an LLM übergeben und Frage beantworten lassen. **Machbar** in Phase 2, blockiert technische Fixes nicht.
- **Empfehlung:** Document QA in Phase 2 nur umsetzen, wenn klar **Variante B** gewünscht ist (kein RAG, kein PDF-Chunk-System). Andernfalls Phase 2 auf technische Fixes + Copy/UI beschränken und Document QA in einen späteren Scope verschieben.

### B.2 Falls Document QA (Variante B)

- Neuer Bereich im Panel: „Ask about sanctions documents“ mit Eingabe + Button; Request an bestehenden Endpoint mit `source: "ofac"`, `conflict` aus Kontext; Anzeige Antwort + Confidence; AbortController/Retry analog SanctionsSearch; Disclaimer.

---

## C. Phase 3 – Screening, Batch, Rate Limit, Accessibility

### C.1 Batch-Screening mit „Screen all actors“

- **Backend:** `POST /api/compliance/sanctions-check` um optionales `queries?: string[]` erweitern; parallele Aufrufe mit begrenzter Concurrency (z. B. max 5 gleichzeitig serverseitig). Response pro Query bündeln; `screened_at` pro Result.
- **Frontend – zwei Wege:**
  1. **„Screen all actors“-Button:** Entitäten aus **aktuellem Konflikt-Kontext** laden. **Datenquelle (geprüft):** `ConflictData` hat `actors?: Array<{ id, name, role, activity, intelligence? }>` ([useConflictWebSocket.ts](src/hooks/useConflictWebSocket.ts)). Das Backend füllt `actors` nur, wenn `conflict` „iran“ enthält ([supervisor.py](backend/agents/supervisor.py): `_build_iran_actors(key_findings)`), mit Namen aus `_IRAN_ACTORS` (z. B. Israel, United States, Iran, IRGC, NATO, Hezbollah, Houthis, Iraqi PMF). Für „Screen all actors“: `data?.actors?.map(a => a.name) ?? []` an Batch-Endpoint senden. Bei **keinen** Actors (z. B. anderer Konflikt): Button deaktivieren oder ausblenden, optional Tooltip „Conflict actors available for Iran only.“ **Das ist der eigentliche Mehrwert** gegenüber manuellem Eintippen.
  2. **Textarea (optional):** Zeilen/Komma als Liste; gleicher Batch-POST für Nutzer, die eigene Namen eingeben wollen.
- **Rate Limiting (Client):** Bei vielen Entitäten (z. B. 20) nicht alle parallel feuern. **Throttle:** z. B. max 3 parallele Requests; Rest in Queue nacheinander oder in kleinen Batches. Verhindert Backend-Überlastung.

### C.2 Transliteration / Alias, screened_at

- Backend: In Match-Response `aliases_checked`, `screened_at`; Frontend: Anzeige „Transliterations checked“, „Screened at: …“. Optional „Recent screenings“ (lokal oder API).

### C.3 Keyboard Accessibility

- **SanctionsSearch:** Formular und Input mit `aria-label` (z. B. "Screen firm or partner name against sanctions lists"); Button `aria-label="Run sanctions check"`.
- **CollapsibleSections:** `aria-expanded={expanded}` am Button; `aria-controls` auf die ID des ein-/ausblendbaren Bereichs. So ist das Tool keyboard- und screenreader-tauglich.

### C.4 Risk-Score-Drill-Down

- Pro Driver onClick: Scroll zu Sektion (#sanctions-lists, #geofencing-alerts, #ais-anomalies) oder Modal mit zugrunde liegenden Daten. Mapping factor → sectionId; IDs an Sektionen setzen.

### C.5 Export, Listen-Transparenz

- Export-Button pro Screening: JSON (query, matches, screened_at, threshold_policy). Unter „Sanctions Lists“ Hinweis „Lists covered: OFAC SDN, EU Consolidated; UN, UK OFSI, Swiss SECO not yet integrated.“

---

## D. Phase 4 – Geofencing Persistenz, AIS Confidence, Error Boundaries

### D.1 Geofencing: first_seen / last_seen – Laufzeitmodell (geklärt, umgesetzt)

- **Laufzeitmodell (geklärt):** Die App läuft als **einziger persistenter Prozess** (FastAPI lifespan, periodischer Run alle 6h in main.py + on-demand via API). `_previous_sigint` in supervisor.py überlebt zwischen Läufen; bei Restart/Deploy ist der Zustand weg. **Entscheidung:** In-Memory-Store für Geofencing-Persistenz umgesetzt; ausreichend für Single-Instance und typische Railway-Worker. Für Audit-Pflicht oder Multi-Instance später **DB** einplanen (Tabelle z. B. `geofencing_alerts`).
- **Umgesetzt:** In [geofencing.py](backend/compliance/geofencing.py) Modul-Store `_geofencing_state: (conflict, asset_id, zone_name) -> { first_seen_at, last_seen_at }`. `check_sigint_for_sanctions(sigint_result, conflict=...)` aktualisiert den Store pro Alert und hängt an jeden Alert `first_seen_at`, `last_seen_at`, `duration_hours` an. Supervisor übergibt `conflict` an die Funktion.

### D.2 Geofencing Deduplizierung + Dauer (umgesetzt)

- **Backend:** Jeder Alert (ein Asset in einer Zone pro Lauf) wird im Store aktualisiert; pro Alert werden first_seen_at, last_seen_at und duration_hours (Stunden, gerundet) mitgeliefert. Keine zusätzliche Gruppierung nötig (ein Eintrag pro Asset+Zone pro Lauf).
- **Frontend:** [CompliancePanel](src/components/dashboard/CompliancePanel.tsx) zeigt pro Geofencing-Card optional „First seen“, „Last seen“ (ISO-Zeit), „Duration“ (Xh), sofern die Felder vom Backend gesetzt sind.

### D.3 AIS: gap_hours / last_seen_at / confidence (umgesetzt)

- **Backend:** [ais_anomaly.py](backend/compliance/ais_anomaly.py) – `AISAnomaly` mit optionalen Feldern `gap_hours`, `last_seen_at`, `confidence`. Spoofing: `gap_hours` = time_diff_h, `last_seen_at` = aktueller Ship-Timestamp, Confidence HIGH/MEDIUM aus Geschwindigkeits-Abweichung bzw. Flag/Zone. Dark Activity: `previous_run_ts` aus Supervisor (`_previous_sigint_ts`), daraus `last_seen_at`, `gap_hours`, Confidence HIGH (Hormuz/Iran) bzw. MEDIUM.
- **Supervisor:** Übergibt `previous_run_ts` an `analyze_ais_anomalies`, speichert nach jedem Lauf `_previous_sigint_ts[conflict] = time.time()`.
- **Frontend:** [CompliancePanel](src/components/dashboard/CompliancePanel.tsx) – AIS-Anomaly-Cards zeigen optional Gap (Xh), Last seen (ISO UTC), Confidence-Badge mit Tooltip („Heuristic confidence: strong/moderate indicator“).

### D.4 Error Boundaries

- **React Error Boundary** um die einzelnen Sections des Compliance-Panels (z. B. RiskScoreDisplay, SanctionsSearch, GeofencingAlerts, AISAnomaliesSection, OFAC Summary). Wenn eine Sub-Component wegen unerwartetem Backend-Response crasht, fängt der Boundary den Fehler ab und zeigt eine Fallback-UI (z. B. „This section could not be loaded“) statt das **gesamte Panel** mitzureißen.

---

## E. Weitere Punkte (unverändert)

- **Ownership-Visualisierung:** ownership_chain als vertikaler Tree/kleiner Graph (Phase 3 oder 4).
- **Optional:** Geofencing um Monitoring-Zonen (high_risk); Listen-Indikator; PDF-Export für Screening.

---

## F. Zusammenfassung der Änderungen zum vorherigen Plan

| Thema | Anpassung |
|-------|-----------|
| Copy | **MATCH_LEVEL_LABELS** und optional **RISK_LEVEL_LABELS** in complianceCopy.ts; Panel nutzt diese für Badges und Erklärungen. |
| Phase 1 | AbortController, Retry, Null-Safety, URL-Check als **Quick Wins** in Phase 1. |
| Document QA | **Klarer Scope:** Nur Variante B (bestehender Kontext an LLM) in Phase 2; RAG/PDF = eigenes Projekt, blockiert nicht. |
| Batch-Screening | **„Screen all actors“-Button** aus Konflikt-Kontext (data.actors / conflict_entities) als Hauptoption; Textarea optional. |
| Rate Limiting | **Client-Throttle** (z. B. max 3 parallele Requests) bei Batch in Phase 3. |
| Geofencing Persistenz | **Laufzeitmodell** dokumentiert: In-Memory vs. DB; Abhängigkeit von persistentem Prozess (Railway) klären. |
| Accessibility | **aria-label** (SanctionsSearch), **aria-expanded** / **aria-controls** (CollapsibleSections) in Phase 3. |
| Error Boundaries | **Error Boundary** pro Section in Phase 4. |

---

## Dateien-Referenzen

| Bereich | Dateien |
|---------|---------|
| Copy / Labels | [src/lib/complianceCopy.ts](src/lib/complianceCopy.ts) (neu), [CompliancePanel.tsx](src/components/dashboard/CompliancePanel.tsx) |
| Quick Wins | CompliancePanel.tsx |
| SIGINT Summary | [supervisor.py](backend/agents/supervisor.py), useConflictWebSocket, CompliancePanel.tsx |
| Batch / Actors | routes.py, sanctions_search.py, CompliancePanel.tsx; Datenquelle für Akteure prüfen (data.actors / key_findings) |
| Accessibility | CompliancePanel.tsx (Form, CollapsibleSection) |
| Geofencing Store | geofencing.py, supervisor.py, ggf. DB-Migration |
| Error Boundary | CompliancePanel.tsx oder Wrapper-Komponente |
