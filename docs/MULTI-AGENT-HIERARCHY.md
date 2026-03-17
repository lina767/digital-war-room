# Multi-Agent-Hierarchie: Analysts → Middle Management → Supervisor

Konzept, wie sich innerhalb der bestehenden Agents eine klare Drei-Ebenen-Struktur etablieren lässt: **Analysts** (fachliche Sub-Agents), **Middle Management** (Domain-Manager pro Agent), **Supervisor** (bestehender CEO/Supervisor).

---

## Sinn / Wann lohnt es sich?

| Lohnt sich | Eher overkill |
|------------|----------------|
| Mehrere **unabhängige Quellen** pro Domain (NEWS: NewsAPI, RSS, NewsData, GNews; GEOINT: FIRMS, ReliefWeb, EO, GDELT). | Agent mit **einer** Quelle oder einem klaren linearen Ablauf. |
| **Gleiches Muster** über Domains: Quellen parallel → Aggregation → ein Result. | Großer Big-Bang-Refactor aller 13 Agents ohne konkreten Nutzen. |
| **Testbarkeit:** Analysts einzeln testen, Manager mit Mock-Outputs. | Zusätzliche Abstraktion ohne Wiederverwendung oder bessere Observability. |
| **Observability:** Pro-Quelle Latenz/Fehler (z. B. für Health-Dashboard). | |

**Empfehlung:** Pattern **nur dort** einführen, wo es klaren Mehrwert bringt. NEWS als Referenz umgesetzt (nutzt `run_domain_with_analysts`); andere Agents bei Bedarf schrittweise nachziehen (z. B. GEOINT, FININT), Rest unverändert lassen.

---

## Effizienz, Eleganz, Zusammenarbeit

### Effizienz

| Aspekt | Bewertung |
|--------|-----------|
| **Domain-Runner** | Kein zusätzlicher Lauf: Analysts laufen weiter parallel (ein ThreadPool pro Domain). Overhead: ein Executor, ein Dict-Zusammenbau – vernachlässigbar. |
| **Handoff (Zwei Phasen)** | Wenn `USE_AGENT_HANDOFF=true`: Wave 1 und Wave 2 nacheinander → Gesamtlaufzeit kann **länger** sein als ein einziger paralleler Lauf aller Agents. Trade-off: bessere Zusammenarbeit (Kontext) vs. Latenz. Für maximale Effizienz: Handoff aus lassen oder Kontext aus **vorherigem** Lauf (Cache) nutzen statt zweiter Phase. |
| **Doppelte Aufrufe** | Keine: Jede Quelle wird einmal pro Lauf aufgerufen; Manager aggregiert nur. |

### Eleganz

- **Ein Runner, eine Signatur:** `run_domain_with_analysts(conflict, analysts=[(name, fn), ...], manager=fn, context=None)` – alle Domains nutzen dieselbe Schleife (parallel → manager). Analysts können optional `(conflict, context)` unterstützen; der Runner ruft intern `_run_analyst_safe` auf und fängt fehlendes Context-Argument ab.
- **Manager = eine Funktion:** Pro Domain eine Manager-Funktion, die `(conflict, analyst_results, context?)` bekommt – klare Verantwortung, gut testbar mit Mock-`analyst_results`.
- **Verträge:** Domain-Output bleibt der bestehende Contract (z. B. `NewsResult`); die Aufteilung in Analysts + Manager ist Implementierungsdetail.

### Zusammenarbeit

- **Kontext (Handoff):** `AgentContext` mit `peer_summaries`, `focus_regions`, `key_findings_so_far`, `escalation_signals` – Wave-2-Agents (z. B. GEOINT, NEWS) können gezielter arbeiten. GEOINT nutzt `focus_regions` für zusätzliche FIRMS-Abfragen; NEWS kann `peer_summaries` im Summary erwähnen. Nutzung von `context.summary_for_agent(agent_name)` in weiteren Agents ausbaubar.
- **Corroborated patterns:** Supervisor baut aus Agent-Ergebnissen Muster, in denen **mehrere** Agents dasselbe Thema erwähnen (z. B. Strait of Hormuz, Sanktionen) – explizite Zusammenarbeit auf Synthese-Ebene.
- **Enrichment über Domains:** Bereits vorhanden (z. B. Chokepoint mit SIGINT/Energy/News, Compliance mit SIGINT/Diplo). Das Analyst–Manager-Pattern betrifft die **innere** Struktur pro Domain; die **zwischen** Domain-Zusammenarbeit bleibt Supervisor + Enrichment-Schritte.

**Kurz:** Effizient durch parallele Analysts und minimalen Overhead; elegant durch einheitliches Runner-Pattern und klare Manager-Rolle; Zusammenarbeit durch Handoff-Kontext (Wave 2), corroborated patterns und bestehende Cross-Domain-Enrichments. Handoff-Option ist ein bewusster Trade-off Latenz vs. Kontext.

---

## Robustheit

| Schicht | Verhalten bei Fehlern |
|---------|------------------------|
| **Domain-Runner** | Pro Analyst: Timeout oder Exception → Eintrag `{name: {"error": "timeout"}` bzw. `{"error": str(e)}`; Manager wird **immer** mit vollständigem `analyst_results` aufgerufen (auch bei Teilausfällen). Manager-Exception wird nach oben durchgereicht, damit der Aufrufer (z. B. NEWS) ein Fallback-Result zurückgeben kann. |
| **Manager (z. B. NEWS)** | Erwartet pro Quelle `.get(name) or {}`; bei `result.get("error")` wird die Quelle als leer behandelt (z. B. `articles: []`). Fusion/Score/Summary laufen mit Teilergebnissen; `_meta` und `source_results` bilden fehlgeschlagene Quellen als "error" ab. |
| **Aufrufer (z. B. _run_rule_based_news)** | `try/except` um den gesamten `run_domain_with_analysts`-Aufruf; bei jeder Exception wird ein **gültiges Domain-Result** (Score 50, leere Listen, `summary: "NEWS data unavailable."`, `_meta` mit `error_summary`) zurückgegeben – kein Abbruch der Pipeline. |
| **Handoff / Kontext** | `build_context_from_results` nutzt durchgängig `.get()` und `isinstance`; ungültige Koordinaten (z. B. nicht-numerische `lat`/`lon`) werden mit `try/except (TypeError, ValueError)` übersprungen, damit fehlerhafte SIGINT-Daten den Kontext-Bau nicht zum Absturz bringen. |
| **Supervisor** | Pro Agent: Timeout/Exception → `_result_or_fallback` liefert Contract-Fallback + `"error": str(e)`; alle Agents liefern ein Dict. Synthese und corroborated_patterns kommen mit Teilergebnissen zurecht. |

**Kurz:** Analyst- und Agent-Fehler führen zu definierten Fallbacks (Fehler-Einträge, leere Listen, Fallback-Score), kein ungefangener Crash. Kontext-Build ist gegen kaputte Koordinaten abgesichert. Manager- und Runner-Logik sind so umgesetzt, dass Teilausfälle toleriert werden.

---

## Aktuelle Struktur (bereits hierarchisch)

| Ebene | Heute | Rolle |
|-------|--------|--------|
| **Supervisor** | CEO (`ceo.py`) / Legacy-Supervisor (`supervisor.py`) | Gewichtet Division-Ergebnisse, LLM-Synthese, key_findings, threat_level, summary. |
| **Middle Management** | Division Heads (`division.py`, `divisions/*.py`) | Pro Division: mehrere Agents, gewichteter Score, Anomalie-Erkennung, Division-Summary. |
| **„Agents“** | 13 run_*_agent(conflict) | Pro Domain ein Einstieg; intern teils bereits mehrere „Quellen“/Tools. |

**Lücke:** Die 13 Top-Level-Agents sind heute **monolithisch** (eine Funktion pro Domain). Middle Management existiert nur auf **Division-Ebene** (Military, Financial, …), nicht **innerhalb** eines Agents. NEWS ist die Ausnahme: dort gibt es bereits explizit Source-Agents (NewsAPI, RSS, …) → Fusion → Escalation-Meta.

---

## Zielbild: Analysts + Manager pro Domain

Jeder der 13 Agents wird intern als **Multi-Agent-System** modelliert:

```
┌─────────────────────────────────────────────────────────────────┐
│ SUPERVISOR (CEO / Legacy-Supervisor)                             │
│   Input: Division-Summaries + Compliance                         │
│   Output: escalation_score, threat_level, key_findings, summary   │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Division Head │   │ Division Head │   │ Division Head │   … (bereits vorhanden)
│ (Middle Mgmt  │   │ (Middle Mgmt  │   │ (Middle Mgmt  │
│  auf Div-Ebene)│   │  auf Div-Ebene)│   │  auf Div-Ebene)│
└───────┬───────┘   └───────┬───────┘   └───────┬───────┘
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ NEWS Agent    │   │ GEOINT Agent  │   │ FININT Agent  │   ← Top-Level-Agent = „Domain“
│ (Domain)      │   │ (Domain)      │   │ (Domain)      │
│               │   │               │   │               │
│  ┌─────────┐  │   │  ┌─────────┐  │   │  ┌─────────┐  │
│  │ Manager │  │   │  │ Manager │  │   │  │ Manager │  │   ← Middle Management (pro Domain)
│  └────┬────┘  │   │  └────┬────┘  │   │  └────┬────┘  │
│       │       │   │       │       │   │       │       │
│  ┌────┴────┐  │   │  ┌────┴────┐  │   │  ┌────┴────┐  │
│  │Analysts │  │   │  │Analysts │  │   │  │Analysts │  │   ← Analysts (Sub-Agents)
│  │NewsAPI  │  │   │  │FIRMS    │  │   │  │Brent/WTI│  │
│  │RSS      │  │   │  │ReliefWeb│  │   │  │Polymarket│ │
│  │GDELT    │  │   │  │EO Links │  │   │  │OFAC     │  │
│  │…        │  │   │  │…        │  │   │  │…        │  │
│  └─────────┘  │   │  └─────────┘  │   │  └─────────┘  │
└───────────────┘   └───────────────┘   └───────────────┘
```

- **Analysts:** schmale Aufgabe (eine Quelle, eine Methode), liefern Rohdaten/Teilergebnis.
- **Manager (pro Domain):** koordiniert Analysts (parallel/sequentiell), aggregiert, bewertet, baut das **einheitliche Agent-Result** (Score, Summary, Listen). Entspricht konzeptionell einem „Middle Management“ pro Domain.
- **Supervisor:** bleibt wie heute (CEO oder Legacy); sieht nur die 13 Domain-Results.

---

## Vorteile

- **Rollenklarheit:** Wer liefert Daten (Analyst), wer fasst zusammen (Manager), wer synthetisiert global (Supervisor).
- **Wiederverwendbarkeit:** Analysts können bei mehreren Domains genutzt werden (z. B. „RSS“ als Analyst für NEWS und für SOCMINT).
- **Testbarkeit:** Analysts einzeln testbar; Manager mit Mock-Analyst-Outputs.
- **Skalierung:** Neue Quelle = neuer Analyst; Domain-API (run_*_agent) bleibt stabil.
- **Observability:** Pro Analyst/Manager Metriken (Latenz, Fehler) möglich.

---

## Konkrete Umsetzung

### 1. Lightweight-Pattern: Analyst + Manager (ohne großes Framework)

Ein minimales Pattern in `backend/agents/`:

- **Analyst:** Callable `(conflict: str, context: Optional[AgentContext] = None) -> Dict[str, Any]` (Teilergebnis, z. B. `{"source": "newsapi", "articles": [...], "count": N}`).
- **Manager:** Callable `(conflict: str, analyst_results: Dict[str, Any], context: Optional[AgentContext] = None) -> Dict[str, Any]`; liefert das **volle** Agent-Result (Score, Summary, Listen) gemäß Contract (z. B. `NewsResult`).
- **Runner:** Gemeinsame Hilfsfunktion `run_domain_with_analysts(conflict, analysts=[(name, fn), ...], manager=fn, context=None)` in **`agents/domain_runner.py`** führt alle Analysts parallel aus, sammelt `analyst_results`, ruft dann den Manager auf und gibt dessen Rückgabe zurück.

Bestehende `run_*_agent` bleiben die Einstiegspunkte; intern können sie `run_domain_with_analysts` nutzen (oder die aktuelle Implementierung beibehalten bis zur schrittweisen Migration).

### 2. NEWS (bereits nah dran)

- **Analysts:** `_run_newsapi_source_agent`, `_run_rss_source_agent`, `_run_newsdata_source_agent`, `_run_gnews_source_agent` (bereits vorhanden).
- **Manager:** Fusion + Escalation + NER = ein expliziter „NewsManager“: Input = Dict[analyst_name, result], Output = einheitliches News-Result. Heute: `_run_news_fusion_agent` + `_run_escalation_headline_agent` + `_run_ner_enrichment`; das kann als eine Manager-Funktion gekapselt werden.
- **Einstieg:** `run_news_agent(conflict, context)` ruft Runner(analysts=[…], manager=news_manager).

### 3. GEOINT (migrierbar)

- **Analysts:** z. B. `get_thermal_anomalies` (FIRMS), `get_conflict_hotspot_news` (ReliefWeb/ACLED), `get_eo_browser_links`, `get_gdelt_geo_countries`; optional `_fetch_thermal_anomalies_for_focus_regions` (Handoff). Jeder als kleine Funktion mit klarem Output (z. B. Liste Anomalien, Liste Reports, Links).
- **Manager:** Nimmt die Analyst-Outputs, berechnet Score (z. B. `_compute_geoint_score`), baut Hotspots/Clusters, schreibt Summary und `_meta`. Entspricht der heutigen Logik in `_run_rule_based_geoint`, aber mit expliziten Analyst-Ergebnissen als Input.
- **Einstieg:** `run_geoint_agent(conflict, context)` = Runner(analysts=[firms_analyst, reliefweb_analyst, eo_analyst, gdelt_analyst], manager=geoint_manager).

### 4. FININT, SIGINT, andere

- **FININT:** Analysts = Brent/WTI, Polymarket, OFAC, Metaculus, …; Manager = gewichteter Score, Summary, einheitliches FinintResult.
- **SIGINT:** Analysts = ADSB, Conflict Reports, Hormuz Tankers (Chokepoint); Manager = sigint_score, aircraft/ships Listen, summary.
- Analog für ENERGY, TECHINT, CYBER, PROTEST, DIPLO, PROXIMITY, CHOKEPOINT, NARRATIVE: pro Domain 3–6 Analysts + 1 Manager definieren.

### 5. Keine Änderung am Supervisor

- Supervisor/CEO konsumiert weiterhin die 13 Domain-Results (von den „Managern“). API und Verträge (Contracts) bleiben gleich.
- Optional: Manager-Output kann ein Feld `_analyst_summaries: Dict[str, str]` oder `_sources: List[SourceResult]` enthalten, das der Supervisor oder das Frontend für Transparenz nutzt.

---

## Implementierungsoptionen

| Option | Aufwand | Beschreibung |
|--------|--------|--------------|
| **A) Nur dokumentieren** | Gering | NEWS als Referenz in diesem Doc beschreiben; andere Agents bei Refactors schrittweise an dasselbe Muster anpassen. |
| **B) Runner-Helper** | Mittel | Gemeinsame Funktion `run_domain_with_analysts(conflict, analysts: List[Callable], manager: Callable, context=None)` in z. B. `agents/runner.py`; NEWS und GEOINT darauf umstellen, Rest unverändert. |
| **C) Registry pro Domain** | Höher | Pro Domain eine kleine Registry (Analyst-Namen + Callables), Manager registriert; Runner liest Registry und führt aus. Ermöglicht Konfiguration pro Domain (z. B. Analysts ein/aus). |
| **D) LLM für Manager** | Variabel | Manager kann optional ein LLM nutzen („Fasse die Analyst-Ergebnisse zusammen, priorisiere Konflikt-Relevanz“); aktuell überwiegend regelbasiert möglich. |

Empfehlung: **B)** zuerst umsetzen (Runner + explizite Analyst-/Manager-Signaturen für NEWS und GEOINT), dann schrittweise weitere Domains migrieren; **C)** nur bei Bedarf (z. B. wenn viele Analysts pro Domain und Konfiguration gewünscht ist).

---

## Kurzfassung

- **Analysts** = fachliche Sub-Agents pro Domain (Quellen, Tools, enge Aufgaben).
- **Middle Management** = ein **Manager** pro Domain, der Analysts orchestriert und das einheitliche Agent-Result erzeugt.
- **Supervisor** = bestehender CEO/Legacy-Supervisor; ändert sich nicht.
- Durch ein leichtes **Analyst–Manager–Runner-Pattern** lässt sich diese Hierarchie innerhalb der bestehenden 13 Agents etablieren, ohne die Top-Level-API zu verändern. NEWS ist bereits ein funktionales Vorbild; GEOINT und andere können dem gleichen Muster folgen.
