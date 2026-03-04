# Handoff für neuen Agenten – Digital War Room

Kurzfassung für den ersten Prompt an einen neuen Agenten (z. B. neuen Chat).

---

## Aktueller Stand

**Projekt:** Digital War Room – Multi-Source-Konfliktanalyse mit 6 Intelligence-Agenten und einem Supervisor.

- **Backend:** FastAPI (`backend/main.py`), CORS `*`, Routen unter `/api/*` (u. a. `POST /api/analyze`, `POST /api/export/pdf`). Alle Agents laufen im **Supervisor** per `ThreadPoolExecutor` parallel; danach synthetisiert **Claude Sonnet** ein Gesamtergebnis (Score, Threat Level, Key Findings, Scenarios, Summary).
- **Agents (je `run_*_agent(conflict: str) -> Dict`):**
  - **FININT:** Öl (Brent/WTI, Alpha Vantage), Polymarket (Gamma + Data API), getrackte Wallets (z. B. rundeep). Optional: `POLYMARKET_BUILDER_API_KEY`.
  - **SIGINT:** Militärflugzeuge (ADSB: opendata.adsb.fi, api.adsb.lol; /v2/mil + Regionen), Schiffe (VesselFinder-BBoxes), Conflict Reports (RSS: CriticalThreats, LongWarJournal, UnderstandingWar). Rückgabe: `aircraft`, `ships`, `conflict_reports`, `sigint_score`, `alerts`, `summary`.
  - **NEWS:** NewsAPI, konfliktbezogene Queries, Sentiment, `news_score`.
  - **GEOINT:** NASA FIRMS (Thermal Anomalies), Middle East BBox, `geoint_score`, `hotspots`.
  - **SOCMINT:** Telegram, Reddit, RSS; `socmint_score`, `top_signals`.
  - **TECHINT:** Tech-Indikatoren (Alpha Vantage), Export Controls (NewsAPI), IODA Events, OONI (Telegram/Signal blocked Iran), Cloudflare Radar Outages, Shodan. `techint_score`, `ooni`, `cloudflare_outages`, `shodan`, `ioda_events`.
- **Composite Score:** Gewichtet (z. B. FININT 18 %, SIGINT 22 %, NEWS 18 %, GEOINT 12 %, SOCMINT 18 %, TECHINT 12 %). Supervisor gibt `escalation_score`, `threat_level`, `key_findings`, `scenarios`, `summary` und die Roh-Ergebnisse aller Agents zurück.
- **Frontend:** React/TS, Dashboard mit Run Analysis (REST `/api/analyze`), Export PDF, Key Findings, Karte (ConflictMap). API-Basis über `VITE_API_URL` (Fallback Production-URL).
- **Cursor Rules:** `.cursor/rules/` (project-overview, backend-agents, frontend-react). Projekt-Konventionen dort nachlesen.

---

## Getroffene Entscheidungen

1. **Agent-Schnittstelle:** Jeder Agent: synchroner Einstieg `run_*_agent(conflict: str) -> Dict[str, Any]`; interne HTTP-Calls mit `httpx` + `asyncio.run()`. Keine hart codierten API-Keys; alles über `os.getenv` (`.env` im Backend).
2. **Robustheit:** Bei LLM-Parse-Fehlern: Fallback = Tools direkt aufrufen und aus Rohdaten Score/Summary bauen (FININT, SIGINT so umgesetzt). Externe APIs: Fehler abfangen, leere Listen oder `{"error": "..."}` statt Crash.
3. **Supervisor-Integration:** Neuer Agent = neues Modul `backend/agents/<name>_agent.py` mit `run_<name>_agent(conflict)`. In `supervisor.py`: Import, `AnalysisState` um `<name>_result` erweitern, in `collection_node` mit `executor.submit(run_<name>_agent, conflict)` starten, Score extrahieren, Gewichtung anpassen, in `user_payload` und System-Prompt aufnehmen, Key Findings um typische Ausgaben des Agents ergänzen, in `analyze_conflict()` das neue Ergebnis im Return-Dict zurückgeben.
4. **Frontend:** Neue Felder in `ConflictData` (z. B. in `useConflictWebSocket.ts`) ergänzen, wenn das Backend neue Top-Level-Keys liefert; Anzeige in Dashboard/Key Findings je nach Bedarf.

---

## Nächste Schritte (für den neuen Agenten)

1. **Neuen Agenten definieren:** Name, Datenquellen (APIs/Feeds), gewünschtes Rückgabe-Dict (mind. Score, Summary, fachliche Listen). Optional: Gewichtung im Composite Score und welche Key Findings daraus generiert werden sollen.
2. **Implementierung:** `backend/agents/<name>_agent.py` anlegen (Tools, Fallback-Logik, `run_<name>_agent`), dann Supervisor wie oben erweitern.
3. **Test:** `backend/scripts/check_agents.py` um den neuen Agenten ergänzen (und ggf. `AGENT_ENV`), dann `cd backend && source venv/bin/activate && python scripts/check_agents.py -v`.
4. **Optional:** Frontend-Typen und -Anzeige anpassen, wenn der neue Agent neue Felder im Analyse-JSON liefert.

---

*Dieses Dokument als ersten Prompt an den neuen Agenten kopieren und ggf. den gewünschten neuen Agenten (Name, Quellen, Gewichtung) konkret beschreiben.*
