# Python-Code verbessern – konkrete Vorschläge

Überblick über sinnvolle Verbesserungen am Backend (Python/FastAPI/Agents), priorisiert nach Aufwand und Nutzen.

---

## 1. Weniger Duplikation: _meta und Timing

**Problem:** Fast jeder Agent wiederholt das gleiche Muster: `start = time.perf_counter()`, `fetched_at = utc_now_iso()`, dann im try/except `duration_ms = ...`, `SourceResult`-Liste bauen, `compute_confidence_from_sources`, `data_freshness = "live" if ok_count >= 2 else ...`, `AgentMetadata(...)`, `out["_meta"] = meta.model_dump(mode="json")`.

**Lösung:** Gemeinsame Hilfsfunktionen in `agents/utils.py` nutzen (bereits ergänzt):

- **`data_freshness_from_sources(source_results, has_any_data=True)`** – leitet `"live" | "recent" | "stale" | "unavailable"` aus den SourceResults ab.
- **`build_agent_meta(agent, fetched_at, duration_ms, source_results, fallback_used=..., error_summary=..., has_any_data=...)`** – baut das komplette `_meta`-Dict (inkl. Confidence und data_freshness).

**Nächster Schritt:** In den Agents (z. B. protest, energy, techint, diplo, cyber, socmint, chokepoint, proximity) die lokale Meta-Logik durch Aufrufe dieser Hilfen ersetzen. Spart viele Zeilen und hält das Verhalten einheitlich.

---

## 2. Stärkere Typisierung

**Problem:** Agent-Entry-Funktionen geben überall `Dict[str, Any]` zurück; der Supervisor und die Contracts wissen nur über Pydantic-Modelle, welches Shape ein Result hat.

**Vorschläge:**

- **Rückgabetyp:** Wo es passt, den konkreten Contract-Typ als „Zieltyp“ dokumentieren oder per TypedDict/Protocol abbilden, z. B. `def run_protest_agent(...) -> Dict[str, Any]:  # ProtestResult-shaped`.
- **Validierung:** Optional beim Eintritt in den Supervisor (oder in Tests) Agent-Result mit dem passenden `*Result`-Modell parsen (`model_validate(result)`), um Fehlfelder früh zu erkennen.
- **Neue Agent-Funktionen** von vornherein so schreiben, dass das zurückgegebene Dict dem jeweiligen `*Result`-Schema entspricht.

So bleibt das API weiterhin dict-basiert (flexibel für _meta, Fehler, etc.), aber die Absicht und das erwartete Shape sind klar.

---

## 3. Konfiguration zentral halten

**Problem:** Einige Agents lesen `os.getenv(...)` direkt im Modul oder in der Run-Funktion; andere nutzen bereits `agents/config.py`.

**Vorschlag:** Alle env-gesteuerten Flags und Werte (API-Keys, Timeouts, Feature-Flags) in `config.py` definieren und die Agents nur noch aus dem Config-Modul importieren. Vorteile: einheitliche Stelle für Defaults, bessere Testbarkeit (Config mocken), Dokumentation in einer Datei (z. B. `.env.example` abgleichen).

---

## 4. Linting und Formatierung

**Problem:** Es gibt kein `pyproject.toml` mit Ruff/Mypy-Konfiguration; Style und statische Checks sind nicht einheitlich.

**Vorschlag:** Im Backend-Root ein `pyproject.toml` anlegen mit z. B.:

- `[tool.ruff]`: line-length 100–120, Zielverzeichnis `backend/`, Regeln für Import-Sortierung, ungenutzte Imports, einfache Fehler.
- `[tool.ruff.lint.per-file-ignores]`: z. B. in Tests oder generierten Dateien Lockdown lockern.
- `[tool.mypy]`: optional, z. B. `python_version = "3.11"`, `strict = true` oder schrittweise schärfer; Agents als erste Kandidaten.

CI/Local: `ruff check .`, `ruff format .`, ggf. `mypy agents/`. So bleibt der Stil konsistent und viele kleine Fehler verschwinden vor dem Commit.

---

## 5. Async durchgängig nutzen

**Problem:** Viele Agents definieren intern `async def _run(): ...` und rufen dann `run_async(_run())` auf, weil der Supervisor und die Routes synchron sind.

**Vorschlag (mittelfristig):** Wenn die Analyse-Routes auf async umgestellt werden können, die Agent-Entrypoints schrittweise auf `async def run_*_agent(...)` umstellen und im Supervisor mit `asyncio.gather` (oder Task-Gruppen) parallel laufen lassen. Dann entfällt der Thread-Pool-Wrapper für diese Aufrufe, und die Laufzeit bleibt bei weniger Overhead besser vorhersehbar. Erster Kandidat: ein einzelner „leichtester“ Agent (z. B. proximity) als Pilot.

---

## 6. Tests gezielt ausbauen

**Bereits vorhanden:** z. B. `conftest.py`, Tests für Divisions, DAG, Rate-Limit-Pool, Base-Agent.

**Sinnvolle Ergänzungen:**

- **Unit:** `build_context_from_results` mit verschiedenen `wave1_results` (leer, fehlerhafte Koordinaten, gemischt) – prüfen, dass kein Crash und sinnvolle focus_regions/peer_summaries.
- **Unit:** `get_agent_fallback(agent_name)` für alle registrierten Agent-Namen – Rückgabe ist nicht leer und enthält erwartete Keys.
- **Unit:** `domain_runner.run_domain_with_analysts` mit Dummy-Analysts (einer timeout, einer Exception, einer ok) – Manager bekommt partielle Ergebnisse, kein Abbruch.
- **Integration:** Ein Agent end-to-end (z. B. protest oder news) mit gemockten HTTP-Antworten – prüfen, dass Rückgabe-Dict die erwarteten Keys und _meta enthält.

So bleiben Refactorings (z. B. _meta-Hilfen, Config-Zentralisierung) sicher.

---

## 7. Fehlerfall-Dicts einheitlich bauen

**Problem:** Bei Exceptions bauen manche Agents das Fallback-Dict und _meta nochmal von Hand (duration_ms, leere Listen, error_summary).

**Vorschlag:** Wo möglich das gleiche `build_agent_meta(..., fallback_used=True, error_summary=str(e))` nutzen und das Fallback-Dict aus dem Contract holen: `fallback = get_agent_fallback("protest")` (oder dem jeweiligen Agent-Namen), dann `fallback["_meta"] = build_agent_meta(...)` und `return fallback`. So ist das Fallback-Shape immer konsistent mit den Contracts und weniger Duplikation.

---

## Priorisierung (Kurz)

| Priorität | Maßnahme | Aufwand | Nutzen |
|-----------|----------|---------|--------|
| Hoch | Agents auf `build_agent_meta` / `data_freshness_from_sources` umstellen | Mittel | Weniger Duplikation, einheitliches _meta |
| Hoch | `pyproject.toml` + Ruff (evtl. Mypy) einführen | Gering | Konsistenter Style, weniger kleine Fehler |
| Mittel | Config in `config.py` zentralisieren | Gering–Mittel | Übersicht, Tests, .env.example aktuell |
| Mittel | Unit-Tests für context, domain_runner, get_agent_fallback | Gering | Sicherheit bei Refactorings |
| Niedrig | Stärkere Typen (TypedDict/Result-Shape) und optionale Validierung | Mittel | Bessere IDE-Unterstützung, weniger Shape-Fehler |
| Niedrig | Async-Endpoints + async Agent-Runner | Hoch | Sauberere Concurrency, weniger Thread-Pool |

---

## Umgesetzt (Stand Implementierung)

- **pyproject.toml:** Ruff (line-length 120, I, E, F, B, C4) + optionale Mypy-Sektion; Ziel `backend/`.
- **Config:** `NEWS_MAX_PER_SOURCE`, `NEWS_TOP_K`, `RELIEFWEB_APPNAME` in `config.py`; NEWS-, GEOINT- und SOCMINT-Agents nutzen sie.
- **build_agent_meta / get_agent_fallback:** Protest-, Energy-, Diplo- und Proximity-Agent bauen `_meta` über `build_agent_meta()` und nutzen im Fehlerfall `get_agent_fallback(agent_name)` + `build_agent_meta(..., fallback_used=True, error_summary=...)`.
- **Unit-Tests:** `tests/test_context.py` (build_context_from_results: leer, peer_summaries, focus_regions, bad coords, escalation_signals), `tests/test_contracts_fallback.py` (get_agent_fallback für alle Registry-Agents), `tests/test_domain_runner.py` (partielle Ergebnisse, Manager erhält error-Einträge).
- **Typisierung:** Modul-Docstring in `contracts.py` beschreibt Result-Shape; `get_agent_fallback`-Docstring ergänzt.

**CI:** `.github/workflows/ci.yml` – bei Push/PR: `ruff check`, `ruff format --check`, `pytest tests/`; Mypy-Basis für `api/routes_*.py` + `models/*.py` optional (`continue-on-error`) und zusätzlicher **strict**-Job für `api/routes_compliance.py`, `api/routes_analyze.py` + `models/analysis.py`. Installation nutzt `requirements-dev.txt` statt `pip install -e ".[dev]"` (robuster bei eingeschränktem Netzwerk).

**Lokal:** `cd backend && pip install -r requirements-dev.txt && ruff check . && ruff format --check . && pytest tests/ -q`.

**Ergänzung:** SIGINT, GEOINT, NEWS, TECHINT, CYBER, SOCMINT, CHOKEPOINT und FININT nutzen jetzt durchgängig `build_agent_meta` (bzw. optional `confidence=` bei FININT). Fehlerpfade: `get_agent_fallback` wo sinnvoll (sigint, news, socmint, chokepoint).
