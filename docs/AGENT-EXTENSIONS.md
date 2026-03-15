# Agents erweitern und optimieren

Überblick: Wie man die Intelligence-Agents funktional erweitern kann (neue Quellen, neue Ausgaben, Konfiguration, neuer Agent).

---

## 1. Bestehende Agents um neue Tools/Quellen erweitern

Jeder Agent hat eine feste Tool-Liste und eine regelbasierte Fallback-Kette. Erweiterung = neues Tool hinzufügen und in beiden Pfaden berücksichtigen.

| Agent | Aktuelle Tools/Quellen | Mögliche Erweiterungen |
|-------|------------------------|------------------------|
| **FININT** | Brent, WTI (Alpha Vantage), Polymarket, Tracked Wallets | Weitere Rohstoff-Indizes (Gas, Gold), weitere Prediction Markets (z. B. Kalshi), Sanctions/Treasury-Listen (OFAC) als Tool |
| **SIGINT** | ADS-B (Flugzeuge), VesselFinder, Conflict Reports RSS | MarineTraffic API (wenn Key), NOTAM-Integration (iaea_tracker hat NOTAMs), weitere RSS/Intel-Feeds; **Tool-Kette parallel** (wie FININT/NEWS) für Latenz |
| **NEWS** | NewsAPI, GDELT, RSS | Weitere Sprachen (GDELT filter), regionale Nachrichten-APIs, Alert-System (Keyword-Webhook) |
| **GEOINT** | NASA FIRMS, ReliefWeb, UCDP (optional), ACLED (optional), EO Browser Links | **Liveuamap API** (kostenpflichtig, in DEPLOYMENT erwähnt), **Sentinel Hub Process API** (SENTINELHUB_CLIENT_ID/SECRET für automatische Tiles), weitere Regionen in `REGION_BBOX` |
| **SOCMINT** | Telegram, Nitter, Reddit, RSS, ReliefWeb | Weitere Telegram-Kanäle/Regionen in `TELEGRAM_CHANNELS`, Mastodon/Bluesky als Tool (wenn stabile API), mehr Subreddits pro Region |
| **TECHINT** | Alpha Vantage (ETFs), NewsAPI (Export Control), IODA, OONI, Cloudflare Radar, Shodan | Weitere Shodan-Queries (z. B. Industrie-Protokolle), GreyNoise (Botnet/Scanning), Censys; optional mehr Länder in `CONFLICT_COUNTRY_CODES` |

**Vorgehen pro Agent:**

1. Neues `@tool` in `backend/agents/<name>_agent.py` definieren (z. B. `get_ofac_sanctions(conflict: str)`).
2. Tool zur Liste hinzufügen: `FININT_TOOLS.append(get_ofac_sanctions)` (bzw. in der jeweiligen `*_TOOLS`-Liste).
3. Im **regelbasierten Fallback**: Tool in der festen Kette aufrufen (bei FININT z. B. im `ThreadPoolExecutor`-Block mit den anderen parallel).
4. Score-/Summary-Logik anpassen, damit das neue Tool in `summary` und ggf. im Score berücksichtigt wird.
5. Optional: Supervisor/Frontend erweitern, wenn das Agent-Ergebnis neue Felder hat (z. B. `finint_result["ofac_entries"]`), siehe Abschnitt 2.

---

## 2. Neue Ausgaben/Felder (Agent → Supervisor → Frontend)

Agents liefern ein Dict mit mindestens **Score** und **Summary**; der Supervisor erwartet die bekannten Keys (z. B. `sigint_score`, `aircraft`, `ships`, …) und baut daraus `key_findings` und `summary`. Erweiterungen:

- **Neue Listen/Felder im Agent-Dict:** z. B. `finint_result["sanctions_highlights"]`. Der Supervisor ignoriert unbekannte Keys nicht; sie landen im finalen `analyze_conflict()`-Return unter `finint_result`. Das Frontend kann sie nutzen, wenn die Typen/Anzeige angepasst werden (`useConflictWebSocket`, Dashboard-Komponenten, PDF-Export).
- **Key Findings aus neuem Feld:** In `supervisor.py` in der Fallback-Synthese (regelbasierter Supervisor) und im LLM-Prompt erwähnen, welche neuen Felder zu `key_findings` beitragen sollen (z. B. „FININT sanctions: …“).
- **PDF-Export:** In `api/pdf_export.py` (bzw. `backend/api/pdf_export.py`) die Request-Modelle und die Story um neue Felder ergänzen, wenn sie im Report erscheinen sollen.

---

## 3. Konfigurierbarkeit (ohne Code-Änderung)

| Bereich | Env / Konfiguration | Nutzen |
|---------|---------------------|--------|
| **Konflikt** | `AUTO_ANALYZE_CONFLICT` | Welcher Konflikt im Hintergrund läuft. |
| **Intervall** | `AUTO_ANALYZE_INTERVAL_SEC` | Wie oft der Supervisor läuft (Default 6h). |
| **Zeitfenster** | Noch fest im Code | `hours_back` (NEWS), `days` (GEOINT FIRMS), TECHINT 7d: als Env auslagern (z. B. `NEWS_HOURS_BACK=48`, `FIRMS_DAYS=3`) für „mehr Echtzeit“ vs. „mehr Kontext“. |
| **Gewichtung** | `supervisor.py` | Composite Score: Gewichte FININT/SIGINT/… aktuell fest; könnten als Env (z. B. `AGENT_WEIGHT_FININT=0.18`) gelesen werden. |
| **Optionale APIs** | Bereits Env | UCDP, ACLED, Shodan, Cloudflare Radar, Sentinel Hub, etc. – wenn gesetzt, nutzt der Agent die Quelle. |
| **Regelbasiert vs. LLM** | `USE_RULE_BASED_AGENTS`, `USE_RULE_BASED_SUPERVISOR` | Kosten vs. Flexibilität. |

Erweiterung „Funktionen“ im Sinne Konfiguration: Neue Env-Variablen für Zeitfenster und Gewichtung einführen, in den Agents bzw. im Supervisor auslesen und verwenden.

---

## 4. Neuen Agent hinzufügen

Vollständig in [AGENT-HANDOFF.md](AGENT-HANDOFF.md) beschrieben. Kurz:

1. **Modul** `backend/agents/<name>_agent.py` mit `run_<name>_agent(conflict: str) -> Dict[str, Any]`.
2. **Supervisor:** Import, `AnalysisState` um `<name>_result` erweitern, in `collection_node` mit `executor.submit(run_<name>_agent, conflict)` starten, Fallback-Dict für Timeout/Fehler.
3. **Supervisor Node:** Score extrahieren (z. B. `xxx_score`), in gewichteten Composite Score aufnehmen, im System-Prompt und in der Fallback-Synthese die neuen Daten (z. B. `key_findings`) einbauen.
4. **`analyze_conflict()`:** Neues Ergebnis ins Return-Dict (z. B. `xxx_result`).
5. **Tests:** `scripts/check_agents.py` um den neuen Agenten und ggf. erforderliche Env-Keys erweitern.
6. **Frontend:** Typen und UI anpassen, wenn neue Top-Level-Keys oder Strukturen genutzt werden sollen.

Mögliche neue Agenten-Ideen: **HUMINT/OSINT** (z. B. strukturierte Leak-/Report-Datenbank), **CYBER** (eigener Fokus auf Vulkits, APT-Reports), **DIPLO** (Termine, Erklärungen, UN-Dokumente als strukturierte Quelle).

---

## 5. Technische Optimierungen (bereits geplant/teilweise umgesetzt)

- **Parallelisierung:** FININT, NEWS, SOCMINT, GEOINT (FIRMS) nutzen bereits parallele Tool-Ausführung; SIGINT könnte seine vier Tools ebenfalls parallel ausführen (ThreadPoolExecutor oder async).
- **Caching:** Response-Caching mit TTL pro Quelle (z. B. Ölpreise 15 Min, News 30 Min) würde API-Last und Latenz senken; Run-Context könnte doppelte Calls (Alpha Vantage, NewsAPI, ReliefWeb) pro Lauf reduzieren.
- **Shared HttpClient:** Zentrale `services/http_client.py` in den Agents nutzen (heute nur in Routes), um Connections/Keep-Alive zu bündeln.
- **Konfigurierbare Zeitfenster:** Siehe Abschnitt 3.

---

## 6. Schnellreferenz: Wo was anpassen

| Ziel | Datei(en) |
|------|------------|
| Neues Tool / neue Quelle | `backend/agents/<agent>_agent.py` (Tool + Fallback-Kette + Score/Summary) |
| Agent-Ausgabe erweitern | Ebenfalls `<agent>_agent.py`; dann ggf. Supervisor + Frontend + PDF |
| Key Findings aus neuem Feld | `backend/agents/supervisor.py` (Fallback-Synthese + ggf. System-Prompt) |
| Gewichtung / Intervall / Zeitfenster | `backend/agents/supervisor.py`, `backend/main.py`, ggf. Env in Agents |
| Neuer Agent | Neues Modul + `supervisor.py` (State, collection_node, supervisor_node, analyze_conflict) + `check_agents.py` |
| Frontend-Anzeige | Typen (z. B. in Hooks), Dashboard-Komponenten, `api.ts` |
| PDF-Export | `backend/api/pdf_export.py` |

Wenn du eine konkrete Erweiterung (z. B. „FININT um OFAC-Tool“ oder „SIGINT parallel“) umsetzen willst, reicht die Angabe des Ziels; die Schritte folgen dann aus dieser Struktur.
