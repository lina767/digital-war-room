# ACLED – Diagnose, Log-Muster, Research-Lag

Kurzanleitung wenn ACLED „leer“ wirkt oder die letzten Monate fehlen. Vollständige API-Parameter: [ACLED-API-REFERENCE.md](ACLED-API-REFERENCE.md).

## 1. Schnelltest (ohne laufendes Backend)

Aus dem Verzeichnis `backend/` (mit aktiviertem venv oder `uv run`), nachdem `backend/.env` gesetzt ist:

```bash
cd backend && python scripts/check_agents.py --test-acled
```

- **OAuth `Status: 200` und ältere Fenster mit Daten, „Recent (90d)“ leer** → API funktioniert; siehe [Research-Lag](#3-research-tier--12-monats-lücke) (erwartetes Verhalten für Research-Zugang).
- **`FAIL: Set ACLED_EMAIL + ACLED_PASSWORD`** → Zugangsdaten in `backend/.env` ergänzen (myACLED wie in [Getting started](https://acleddata.com/api-documentation/getting-started)).
- **OAuth `400` / `401`** → Passwort/E-Mail, ggf. EULA/Profil auf acleddata.com prüfen (siehe [API-REFERENCE §9 Fehlermeldungen](ACLED-API-REFERENCE.md#9-fehlermeldungen)).

## 2. Logs durchsuchen (`read-logs`)

Backend-Logs (Stdout, Docker, Railway, …) nach diesen Mustern filtern:

| Thema | Suchbegriffe / typische Meldungen |
|-------|-----------------------------------|
| OAuth | `ACLED OAuth`, `OAuth token failed`, `no credentials`, `Check ACLED_EMAIL` |
| REST API | `ACLED HTTP`, `ACLED API returned HTTP`, `ACLED returned no rows`, `GEOINT heatmap ACLED` |
| Aggregated XLSX | `ACLED aggregated`, `cookie login failed`, `no XLSX link`, `XLSX download failed`, `page scrape error` |
| Startup | `ACLED aggregated startup refresh`, `ACLED aggregated data checked` |
| Theater / CEO | `Theater: ACLED`, `ACLED reference fetch failed` |
| PROTEST-Agent | `ACLED aggregated CSV not found`, `ACLED: no OAuth credentials`, `ACLED: fetched` |

**Ripgrep im Repo** (nur für Entwickler, um Meldungen im Code zu finden):

```bash
rg 'logger\.(warning|info).*ACLED' backend/
```

## 3. Research-Tier / „12-Monats-Lücke“

Für **Research-Level** liefert die **ACLED Read-API** oft **keine** oder kaum Ereignisse im **kalenderaktuellen** Kurzfenster (z. B. letzte 90 Tage bis „heute“): Der öffentlichkeitswirksame Cutoff kann **rund ein Jahr** hinter dem heutigen Datum liegen. Der Code arbeitet deshalb mit längeren Abfragefenstern (z. B. 540 Tage) und älteren Teilfenstern – **Daten liegen dann in der Vergangenheit**, nicht „von letzter Woche“.

Das ist **kein Bug im War Room**, sondern ein **Zugangs-/Tier-Thema** bei ACLED. Aktuellere **regionale** Signale kommen zusätzlich aus:

- **Wöchentliche Aggregated-Downloads** (Nahost-XLSX, Cookie-Login mit denselben Credentials) – siehe `backend/services/acled_aggregated.py`
- **Fallbacks** in GEOINT/PROTEST: ReliefWeb, GDELT, HDX HAPI (siehe `geoint_fetchers.py`, `protest_agent.py`)

## 4. Was ACLED im War Room trotzdem liefert

- **Event-Raster** (Lat/Lon, Typen) für Heatmap und Theater, soweit die API Zeilen zurückgibt.
- **Wöchentliche Aggregates** für PROTEST-Scoring und `ACLED-Aggregated` auf der Karte (wenn Download und Parsing gelingen).
- **Referenz-Analysen** (gecuratete acleddata.com-Seiten für die CEO-Synthese, unabhängig von der Event-API).
- **Ergänzung** zu rein medialen oder Report-Feeds (strukturierte Ereigniscodierung).

## 5. Weiterführend

- [ACLED-API-REFERENCE.md](ACLED-API-REFERENCE.md) – Endpunkte, OAuth, Filter
- [DEPLOYMENT.md](DEPLOYMENT.md) – env-Vars in Produktion
- [RELIEFWEB-ALTERNATIVES.md](RELIEFWEB-ALTERNATIVES.md) – Einordnung ACLED vs. andere Quellen
