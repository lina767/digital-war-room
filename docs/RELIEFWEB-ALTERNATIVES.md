# ReliefWeb-Alternativen

ReliefWeb (UN OCHA) liefert im Projekt humanitäre **Reports nach Land** für GEOINT und SOCMINT. Ab 1. November 2025 ist ein **vorgenehmigter appname** nötig; bei 403 nutzt das Backend bereits ein **RSS-Fallback**. Hier Alternativen, falls ReliefWeb dauerhaft eingeschränkt wird oder ergänzt werden soll.

---

## 1. HDX HAPI (Humanitarian Data Exchange API)

| Aspekt | Details |
|--------|--------|
| **Zweck** | Standardisierte humanitäre Indikatoren, mehrere Quellen, für Workflows/Visualisierungen. |
| **Dokumentation** | [HDX HAPI Docs](https://hdx-hapi.readthedocs.io/en/latest/) · [API](https://hapi.humdata.org/) |
| **Auth** | **App Identifier** (Registrierung/Anfrage: hdx@un.org). |
| **Format** | JSON, filterbar nach Land (ISO3), Thema, Admin-Level (0/1/2). |
| **Status** | Beta (2024/2025). |

**Endpoint-Beispiel (länderbezogen):**

```http
GET https://hapi.humdata.org/api/v1/{THEME}?output_format=json&location_code={ISO3}&app_identifier={APP_ID}
```

- `{THEME}`: z. B. `coordination-context/operational-presence` oder andere [Subcategories](https://hdx-hapi.readthedocs.io/en/latest/).
- `{ISO3}`: z. B. `IRN`, `UKR`, `PSE`.
- Pagination: `limit` / `offset`, max. 1000 pro Request.

**Einsatz:** Gut als Ergänzung oder Ersatz für strukturierte Indikatoren/„Reports“ nach Land; kein 1:1-Ersatz für ReliefWeb-Report-Texte (title/body), aber thematisch passend.

---

## 2. GDACS (Global Disaster Alert and Coordination System)

| Aspekt | Details |
|--------|--------|
| **Zweck** | Echtzeit-Katastrophenmeldungen (Erdbeben, Zyklone, Fluten, Dürren, Vulkane, Waldbrände). |
| **Dokumentation** | [GDACS API](https://www.gdacs.org/gdacsapi/api/events/) · [Quickstart PDF](https://www.gdacs.org/Documents/2025/GDACS_API_quickstart_v1.pdf) |
| **Auth** | Keine. |
| **Format** | GeoJSON, XML, KML. |

**Endpoint-Beispiel:**

```http
GET https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH
```

Filter u. a. nach Datum, Alert-Level, Typ (TC, EQ, FL, VO, WF, DR). Max. 100 Einträge pro Request.

**Einsatz:** Ergänzung für **GEOINT** (disaster events mit Koordinaten), weniger für klassische „humanitarian reports“ wie ReliefWeb.

---

## 3. ReliefWeb RSS (bereits im Projekt)

| Aspekt | Details |
|--------|--------|
| **URL** | `https://reliefweb.int/updates/rss.xml` |
| **Auth** | Keine. |
| **Nutzung** | Wird in `geoint_agent.py` und `socmint_agent.py` als **Fallback** genutzt, wenn die ReliefWeb-API 403 liefert. |

Die RSS-Feed-Logik kann als **primäre Quelle** ausgebaut werden (z. B. mehr Filter nach Land/Keyword), wenn die API dauerhaft nicht nutzbar ist.

---

## 4. Weitere Optionen (im Projekt teils schon vorhanden)

- **ACLED** (GEOINT): Konfliktdaten nach Land, OAuth (ACLED_EMAIL/ACLED_PASSWORD). **Aktuelle Daten**; stärkerer Fokus auf Konflikt-Events als auf „Reports“. Primäre Alternative zu UCDP für Konflikt-Events.
- **UCDP** wurde aus dem Projekt entfernt: GED-Daten enden mit **31.12.2024**; für laufende Analysen bringen sie keinen Nutzen. Stattdessen: ACLED und HDX HAPI (conflict-events).
- **RSS-Aggregation** (SOCMINT/NEWS): Crisis Group, UN, Think-Tanks – liefern Meldungen, aber nicht landesgefiltert wie ReliefWeb Reports.
- **GDELT** (NEWS/GEOINT): Nachrichten-/Orts-Mentions; könnte für landesbezogene „Report“-Aggregation genutzt werden, Aufwand höher.

---

## Empfehlung

- **Kurzfristig:** Am **ReliefWeb-RSS-Fallback** festhalten; ggf. RSS als primäre Quelle, wenn 403 bleibt.
- **Mittelfristig:** **HDX HAPI** prüfen (App Identifier anfragen) und als zusätzliche oder Ersatz-Quelle für länderbezogene humanitäre Daten integrieren.
- **GEOINT-spezifisch:** **GDACS** für Disaster-Events mit Koordinaten ergänzen, parallel zu ReliefWeb/HDX.

Die konkrete Integration (Env-Vars, neue Funktionen in `geoint_agent.py` / `socmint_agent.py`) kann bei Bedarf an diese Liste anknüpfen.
