# GDELT API – Referenz & Nutzung im Digital War Room

Kostenlose APIs, **kein API-Key** nötig. Globale Nachrichtenlandschaft, **alle 15 Minuten** aktualisiert.

**Übersicht:** [The GDELT Project – Data](https://www.gdeltproject.org/data.html)

---

## 1. GDELT DOC API (2.0) – Nachrichten & Tonalität

**Endpoint:** `https://api.gdeltproject.org/api/v2/doc/doc`

**Einsatz:** News Agent (Artikel-Listen), Chokepoint (Trefferzahlen, Eskalationsindikatoren), PROTEST, TECHINT-Fallback.

### Parameter (GET)

| Parameter      | Beschreibung |
|----------------|--------------|
| **query**      | Suchbegriffe, boolesch: AND, OR, NOT (z.B. `"Strait of Hormuz" OR "Hormuz"`) |
| **mode**       | `ArtList` = Artikel-Liste, `TimelineVol` = Zeitreihe Volumen, **`ToneChart`** = Tonalitäts-Zeitreihe (für Eskalations-Tracking) |
| **timespan**   | Zeitfenster: `15min`, `24h`, `48h`, `72h`, `3m` usw. |
| **format**     | `JSON`, `CSV`, `HTML` |
| **maxrecords** | Max. Anzahl Treffer (z.B. 25, 50) |
| **sourcelang** | Optional: Sprachfilter |
| **sourcecountry** | Optional: Quellenland |

Die API durchsucht die globale Nachrichtenlandschaft in Echtzeit und liefert je nach **mode**:
- **ArtList:** Liste von Artikeln (Titel, URL, Domain, Seendate, ggf. sourcecountry).
- **TimelineVol:** Zeitreihe des Berichtsvolumens.
- **ToneChart:** Tonalitäts-Zeitreihe (Durchschnittston über die Zeit) – **gut für Eskalationsindikatoren** (z.B. Strait of Hormuz: sinkender Ton = zunehmend negative/konfliktreichere Berichterstattung).

### Im Projekt

- **News Agent** ([news_agent.py](backend/agents/news_agent.py)): `search_gdelt_news` – `mode=artlist`, `timespan=48H`, Konflikt-Query, max 25 Artikel.
- **Chokepoint** ([chokepoint_agent.py](backend/agents/chokepoint_agent.py)): `_fetch_gdelt_one` – `mode=artlist`, Trefferzahlen für 24H/72H/6H und Closure-Query; optional **ToneChart** für Tonalitäts-Tracking (Eskalation Hormuz).
- **PROTEST** ([protest_agent.py](backend/agents/protest_agent.py)): GDELT DOC für Protest-Artikel.
- **TECHINT** ([techint_agent.py](backend/agents/techint_agent.py)): Fallback für Export-Control-Artikel.

---

## 2. GDELT GEO API (2.0) – Geodaten für Karten

**Endpoint:** `https://api.gdeltproject.org/api/v2/geo/geo`

**Einsatz:** GEOINT, Proximity Agent, TheaterMap – geogetaggte Ergebnisse mit **Lat/Lon**, direkt auf der Karte plottbar.

- Gleiche **query**-Syntax wie DOC API, Ausgabe ist **geospatial** strukturiert (Koordinaten, ggf. ADM1, Country).
- Modi: Country-Level, ADM1, PointData, SourceCountry, Image-Suchen (im Projekt aktuell v.a. Country-Level bzw. DOC-basierte Auswertung).
- **Hinweis:** In einigen Umgebungen war der GEO 2.0 Endpoint zeitweise 404; dann nutzt GEOINT die DOC API und leitet aus `sourcecountry`/Domain eine Länderverteilung ab ([geoint_agent.py](backend/agents/geoint_agent.py) – `get_gdelt_geo_countries`). Wenn GEO 2.0 wieder erreichbar ist, kann auf echten Geo-Output (Lat/Lon) für die TheaterMap umgestellt werden.

---

## 3. GDELT Events Database (1.0 / 2.0)

- **CAMEO**-Kodierung (Conflict and Mediation Event Observations): Jedes Event hat **Actor1**, **Actor2**, **EventCode** (z.B. 14 = Protest, 19 = Fight), **GoldsteinScale** (-10 bis +10 Konfliktintensität), **AvgTone**, Geokoordinaten.
- Rohdaten: Google BigQuery oder tägliche/15-Minuten-Dateien auf [data.gdeltproject.org](https://data.gdeltproject.org/).
- **Nicht** über den DOC/GEO HTTP-API-Endpoint abrufbar; für Event-basierte Auswertung müsste BigQuery oder File-Download integriert werden.

---

## 4. GDELT GKG (Global Knowledge Graph)

- Pro Artikel: **Entitäten** (Personen, Organisationen, Orte), **Themen**, **Emotionen** (GCAM-Scores), **Beziehungen**.
- Nützlich für SOCMINT- und DIPLO-Agenten (Akteursnetzwerke, Beziehungstracking).
- Zugang typischerweise über BigQuery oder GKG-Rohdateien, nicht über die einfache DOC/GEO REST-API.

---

## 5. Tonalitäts-Tracking (Eskalationsindikatoren)

Für **Tonalitäts-Tracking** (z.B. Eskalation im Strait-of-Hormuz-Modul):

- **DOC API** mit **`mode=ToneChart`** (ggf. `timelinetone` je nach API-Version) liefert eine Zeitreihe des durchschnittlichen Tons der Berichterstattung.
- Nutzung: Sinkender/negativer Ton über die Zeit kann als zusätzlicher Eskalationsindikator genutzt werden (z.B. in [chokepoint_agent.py](backend/agents/chokepoint_agent.py) neben Trefferzahlen 24H/72H/6H).
- Optional: Ergebnis in Agent-Output speichern (z.B. `gdelt_tone_timeline`) und im Frontend für Chokepoint-Panel oder Alerts anzeigen.

---

## 6. Kurzüberblick – Wo was genutzt wird

| API / Daten     | Agent(e)        | Zweck |
|-----------------|-----------------|--------|
| **DOC 2.0** (ArtList) | NEWS, PROTEST, TECHINT, Chokepoint | Artikel-Listen, Trefferzahlen |
| **DOC 2.0** (ToneChart) | Chokepoint (optional) | Tonalität/Eskalation Hormuz |
| **GEO 2.0**    | GEOINT, Proximity | Lat/Lon für TheaterMap (oder DOC-Fallback: Länderverteilung) |
| **Events DB**  | NEWS, GEOINT, Chokepoint (optional) | CAMEO-Events über **BigQuery** `gdelt-bq.gdeltv2.events` → Aggregat nach `EventRootCode` ([gdelt_bigquery.py](backend/services/gdelt_bigquery.py)); Fallback ohne GCP-Credentials |
| **GKG**        | –               | Entitäten/Netzwerke; nur über BigQuery/Files |

---

## 7. Integration im Digital War Room

- **News:** [news_agent.py](backend/agents/news_agent.py) – `GDELT_URL`, `search_gdelt_news(conflict)` (query, mode=artlist, timespan=48H).
- **Chokepoint:** [chokepoint_agent.py](backend/agents/chokepoint_agent.py) – `GDELT_QUERIES`, `GDELT_QUERIES_CLOSURE`, `_fetch_gdelt_one`, `_fetch_gdelt_chokepoint_events`; Risk-Floors abhängig von hits_24h/hits_closure_24h/hits_6h. ToneChart optional für Eskalation.
- **GEOINT:** [geoint_agent.py](backend/agents/geoint_agent.py) – `get_gdelt_geo_countries(conflict)` (aktuell DOC-basiert; GEO 2.0 wenn erreichbar); optional **`gdelt_bigquery`** (EventRoot-Aggregate).
- **NEWS:** [news_agent.py](backend/agents/news_agent.py) – optional **`gdelt_bigquery`** parallel zur Fusion (gleiches Konflikt-Keyword-Fenster).
- **CHOKEPOINT:** [chokepoint_agent.py](backend/agents/chokepoint_agent.py) – optional **`gdelt_bigquery`** mit Keywords Hormuz/Mandeb/Suez/Kanal.
- **PROTEST:** [protest_agent.py](backend/agents/protest_agent.py) – `_fetch_gdelt_protest(conflict)` (DOC, Protest-Query).

Alle Aufrufe **ohne API-Key**; Rate-Limits beachten (429 → Retry mit Backoff).
