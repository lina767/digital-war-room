# Chokepoint Monitor: AISStream (aisstream.io) WebSocket-Integration

Aktualisierter Plan mit **exakter API-Referenz** von [aisstream.io/documentation](https://aisstream.io/documentation).

---

## API-Details (aisstream.io)

| Parameter | Wert |
|-----------|------|
| **WebSocket-URL** | `wss://stream.aisstream.io/v0/stream` |
| **Authentifizierung** | API-Key im Subscription-Message (nicht in der URL). |
| **Subscription** | Muss **innerhalb von 3 Sekunden** nach Verbindungsaufbau gesendet werden, sonst wird die Verbindung geschlossen. |
| **Env-Variable** | `AIRSTREAM_API_KEY` (Key von [aisstream.io/apikeys](https://aisstream.io/apikeys)) |

### Subscription-Message (JSON)

```json
{
  "APIKey": "<your api key>",
  "BoundingBoxes": [
    [[lat1, lon1], [lat2, lon2]],
    ...
  ],
  "FiltersShipMMSI": ["..."],
  "FilterMessageTypes": ["PositionReport"]
}
```

- **BoundingBoxes:** Array von Rechtecken. Jedes Rechteck = **zwei Ecken** als `[lat, lon]`. Reihenfolge der Ecken egal.
- **FilterMessageTypes:** Optional. Empfohlen `["PositionReport"]` für Positionen; optional `"ShipStaticData"` wenn Schiffs**typ** (z. B. Tanker 80–89) aus der API genutzt werden soll (dann Merge PositionReport + ShipStaticData nach MMSI/UserID).

### Nachrichtenformat (vom Server)

Jede eingehende Nachricht (JSON):

```json
{
  "MessageType": "PositionReport",
  "MetaData": {
    "MMSI": 259000420,
    "ShipName": "AUGUSTSON",
    "latitude": 66.02695,
    "longitude": 12.253821666666665,
    "time_utc": "2022-12-29 18:22:32.318353 +0000 UTC"
  },
  "Message": {
    "PositionReport": {
      "UserID": 259000420,
      "Latitude": 66.02695,
      "Longitude": 12.253821666666665,
      ...
    }
  }
}
```

- **Position:** aus `MetaData.latitude` / `MetaData.longitude` oder `Message.PositionReport.Latitude` / `Longitude`.
- **Schiffsname:** `MetaData.ShipName`.
- **Schiffstyp (Tanker):** In **PositionReport** nicht enthalten. Entweder nur Name-basiert mit `TANKER_KEYWORDS` filtern, oder zusätzlich **ShipStaticData** abonnieren (`Message.ShipStaticData.Type` 80–89 = Tanker) und nach UserID/MMSI mergen.

### BBox-Umrechnung Agent → AISStream

Aktuell in `CHOKEPOINT_BASELINES` (chokepoint_agent.py):

- Format: `"lon_min, lat_min, lon_max, lat_max"` (String, z. B. `"55,25,58,27.5"`).
- AISStream erwartet: `[[lat_min, lon_min], [lat_max, lon_max]]` (zwei Ecken als [lat, lon]).

Beispiel Hormuz: `"55,25,58,27.5"` → `[[25, 55], [27.5, 58]]`.

---

## Implementierung (kurz)

1. **Env & Doku**
   - `.env.example`: `AIRSTREAM_API_KEY=`, optional `AIRSTREAM_COLLECT_SECONDS=15`.
   - `docs/API-KEYS.md`: Eintrag für AISStream (aisstream.io), Link zur Doku.

2. **Client-Modul** (z. B. `backend/agents/airstream_client.py`)
   - Verbindung zu `wss://stream.aisstream.io/v0/stream`.
   - Subscription sofort nach `open`: alle drei BBoxen (Hormuz, Bab el-Mandeb, Suez) in **einem** Array `BoundingBoxes` (laut Doku können mehrere Boxen überlappen, keine Duplikate).
   - `FilterMessageTypes`: `["PositionReport"]` (mind.); optional `["PositionReport", "ShipStaticData"]` für Typ-basierte Tanker-Erkennung.
   - Nachrichten für `AIRSTREAM_COLLECT_SECONDS` Sekunden sammeln.
   - Jede Nachricht einer Chokepoint-BBox zuordnen (lat/lon in Box?), dann Tanker-Filter (Name + ggf. Type aus ShipStaticData).
   - Rückgabe: `Dict[cp_name, List[{name, type, lat, lon, source: "airstream"}]]`.

3. **Integration im Agent**
   - Wenn `AIRSTREAM_API_KEY` gesetzt: zuerst Airstream-WebSocket-Session (eine Verbindung, eine Subscription mit drei BBoxen), Ergebnis pro Chokepoint für `tanker_count` / `tanker_details` / `data_quality = "live_ais"` nutzen.
   - Bei Fehler/Timeout: Fallback auf MarineTraffic → AISHub wie bisher.

4. **Keine Frontend-Änderungen** – gleiches Agent-Output-Format.

---

## Wichtige Hinweise (aus Doku)

- **Nur wss:** Alle Verbindungen mit API-Key über wss (nicht ws).
- **Subscription-Timeout:** Subscription innerhalb von 3 Sekunden nach Connect senden.
- **Throttling:** Max. 1 Subscription-Update pro Sekunde (Update = erneutes Senden der Subscription auf derselben Verbindung).
- **Verbindung am Leben:** Hohe Nachrichtenrate (z. B. weltweit ~300 msg/s). Bei zu langsamer Verarbeitung kann die Verbindung geschlossen werden. Bei nur drei kleinen BBoxen (Hormuz, Bab el-Mandeb, Suez) ist die Last überschaubar.
- **Beta:** API als Beta ohne SLA dokumentiert.

---

## Konkreter Implementierungsplan (elegant)

### Prinzip

- **Eine** WebSocket-Session pro Agent-Lauf: Connect → sofort Subscribe (alle 3 BBoxen) → Nachrichten für N Sekunden sammeln → sauber schließen.
- AISStream liefert **alle** Schiffe in den Boxen; Zuordnung zu Chokepoint über Punkt-in-BBox; Tanker-Filter über **Namen** (TANKER_KEYWORDS), ohne ShipStaticData (später erweiterbar).
- Agent-API unverändert: weiterhin `Dict[cp_name, tanker_count, tanker_details, data_quality, ...]`. Fallback MarineTraffic/AISHub nur, wenn AISStream nicht konfiguriert oder Fehler.

### Schritt 1: Konfiguration

- **[backend/.env.example](backend/.env.example)**  
  - Zeile im Abschnitt Chokepoint/Maritime ergänzen:  
    `AIRSTREAM_API_KEY=`  
    Optional: `# AIRSTREAM_COLLECT_SECONDS=15` (Default 15 im Code).
- **[docs/API-KEYS.md](docs/API-KEYS.md)**  
  - Neuer Eintrag (z. B. nach AISHUB_USERNAME):  
    **AIRSTREAM_API_KEY** – Chokepoint-Agent, AISStream (aisstream.io), WebSocket-Echtzeit-AIS mit BoundingBox (Hormuz, Bab el-Mandeb, Suez). Key: [aisstream.io/apikeys](https://aisstream.io/apikeys). Doku: [aisstream.io/documentation](https://aisstream.io/documentation).

### Schritt 2: BBox-Helfer (im Chokepoint-Agent)

- **Eine** reine Hilfsfunktion in `chokepoint_agent.py`:
  - Input: `bbox: str` wie `"55,25,58,27.5"` (lon_min, lat_min, lon_max, lat_max).
  - Output:  
    - `airstream_box: List[List[float]]` = `[[lat_min, lon_min], [lat_max, lon_max]]` für die Subscription.  
    - `bounds: (lat_min, lat_max, lon_min, lon_max)` als float-Tupel für „Punkt in Box?“.
- Der **Agent** iteriert über `CHOKEPOINT_BASELINES`, ruft den Helfer pro Eintrag auf und baut:
  - `bounding_boxes: List[List[List[float]]]` für die Subscription (3 Boxen),
  - `cp_bounds: Dict[str, Tuple[float, float, float, float]]` (cp_name → (lat_min, lat_max, lon_min, lon_max)) für die Zuordnung.
- Diese beiden Strukturen übergibt der Agent an den AISStream-Client (kein Import von CHOKEPOINT_BASELINES im Client → kein Zirkelimport).

### Schritt 3: AISStream-Client (eigenes Modul)

- **Neue Datei:** `backend/agents/airstream_client.py`.
- **Konstanten:**  
  - `AISTREAM_WS_URL = "wss://stream.aisstream.io/v0/stream"`.  
  - Default `COLLECT_SECONDS = 15` (env `AIRSTREAM_COLLECT_SECONDS`).
- **Signatur (elegant, keine Agent-Abhängigkeit):**
  - `async def collect_tankers_by_chokepoint(  
      bounding_boxes: List[List[List[float]]],  
      cp_bounds: Dict[str, Tuple[float, float, float, float]],  
      tanker_keywords: List[str],  
      api_key: Optional[str] = None,  
      collect_seconds: float = 15,  
    ) -> Optional[Dict[str, List[Dict[str, Any]]]]`  
  - Der Agent ruft mit aus `CHOKEPOINT_BASELINES` abgeleiteten `bounding_boxes`, `cp_bounds` und `TANKER_KEYWORDS` auf; `api_key` aus Env, falls nicht übergeben.
- **Ablauf im Client:**  
  - Wenn `api_key` leer: `return None`.  
  - WebSocket zu `AISTREAM_WS_URL` öffnen, **sofort** (innerhalb 3 s) Subscription senden: `{"APIKey": api_key, "BoundingBoxes": bounding_boxes, "FilterMessageTypes": ["PositionReport"]}`.  
  - Nachrichten für `collect_seconds` Sekunden sammeln; Nachrichten mit `"error"` ignorieren. Bei `MessageType == "PositionReport"`: Lat/Lon aus MetaData, Name aus MetaData.ShipName; Tanker wenn `any(kw in (name or "").lower() for kw in tanker_keywords)`; Punkt-in-Box über `cp_bounds` (lat_min <= lat <= lat_max, lon_min <= lon <= lon_max). Pro Chokepoint MMSI/UserID deduplizieren.  
  - Rückgabe: `Dict[cp_name, List[{"name", "type", "lat", "lon", "source": "airstream"}]]`. Bei Fehler: loggen, `return None`.
- Nur `websockets` nutzen (bereits in requirements.txt).

### Schritt 4: Integration im Chokepoint-Agent

- **[backend/agents/chokepoint_agent.py](backend/agents/chokepoint_agent.py)**  
  - Am Anfang von `_run()` (nach den bestehenden awaits für EIA/GDELT/External):  
    - `tankers_by_cp = await collect_tankers_by_chokepoint()` aufrufen (Import aus `airstream_client`).  
    - Wenn `tankers_by_cp is None`, bleibt `tankers_by_cp = {}` (oder nicht setzen und im Loop nur Fallback nutzen).
  - In der **for-Schleife** über `CHOKEPOINT_BASELINES`:  
    - Statt zuerst MarineTraffic/AISHub:  
      - Wenn `tankers_by_cp` vorhanden und `cp_name in tankers_by_cp`:  
        - `tankers = tankers_by_cp[cp_name]`  
        - `data_quality = "live_ais"`  
      - Sonst: bestehende Kaskade `_fetch_marinetraffic_tankers(bbox)` → `_fetch_aishub_tankers(bbox)` wie bisher.
  - Rest der Schleife unverändert (tanker_count, oil_flow, cp_entry, etc.).
- **Docstring** des Moduls anpassen: Tier 1 um „AISStream (aisstream.io), wenn AIRSTREAM_API_KEY gesetzt“ ergänzen.

### Schritt 5: Tanker-Deduplizierung und -Format

- Im AISStream-Client: Pro Chokepoint die Liste von Vessels nach **UserID/MMSI** deduplizieren (letzte Position pro MMSI behalten), dann Tanker-Filter anwenden; Ausgabeformat identisch zu den anderen Quellen: `{"name", "type", "lat", "lon", "source": "airstream"}`.
- `TANKER_KEYWORDS` aus chokepoint_agent importieren und für Name-Matching nutzen (kein ShipStaticData nötig für erste Version).

### Ablauf (Kurz)

1. Env + API-KEYS.md anpassen.  
2. BBox-Helfer (string → AISStream-Box + bounds).  
3. `airstream_client.py`: Connect → Subscribe (3 BBoxen, PositionReport) → Sammeln (N s) → Zuordnung zu CP + Tanker-Filter + Dedup → Return `Dict[cp_name, List[tanker]]`.  
4. In `chokepoint_agent._run()`: einmalig `tankers_by_cp = await collect_tankers_by_chokepoint()`; im Loop zuerst AISStream-Ergebnis nutzen, sonst Fallback.  
5. Keine Änderung an Frontend oder Supervisor.

### Dateien-Übersicht

| Datei | Änderung |
|-------|----------|
| `backend/.env.example` | `AIRSTREAM_API_KEY=`, optional `AIRSTREAM_COLLECT_SECONDS` |
| `docs/API-KEYS.md` | Eintrag AISStream |
| `backend/agents/airstream_client.py` | **Neu**: `collect_tankers_by_chokepoint(bounding_boxes, cp_bounds, tanker_keywords, ...)` – WebSocket, Subscription, Parsing, Tanker-Filter, Dedup; keine Imports aus chokepoint_agent |
| `backend/agents/chokepoint_agent.py` | BBox-Helfer (string → airstream_box + bounds); zu Beginn von `_run()` aus BASELINES `bounding_boxes` und `cp_bounds` bauen, `collect_tankers_by_chokepoint(..., TANKER_KEYWORDS)` aufrufen; in der for-Schleife zuerst `tankers_by_cp.get(cp_name)`, sonst Fallback MarineTraffic/AISHub |

### Warum diese Lösung elegant ist

- **Eine** WebSocket-Runde pro Lauf, **eine** Subscription mit drei BBoxen (kein dreifaches Polling).
- **Kein Zirkelimport:** Client kennt nur BBox-Listen und Keywords; der Agent stellt sie aus `CHOKEPOINT_BASELINES` / `TANKER_KEYWORDS` bereit.
- **Gleiche Datenform:** Rückgabe wie bei AISHub (`name`, `type`, `lat`, `lon`, `source`); bestehende Scoring- und Enrich-Logik bleibt unverändert.
- **Klare Fallback-Kette:** AISStream → MarineTraffic → AISHub; bei Fehlern oder fehlendem Key automatisch nächstes Tier.

---

## Referenzen

- [aisstream.io/documentation](https://aisstream.io/documentation)
- [API Keys](https://aisstream.io/apikeys)
- [OpenAPI / Message Models](https://github.com/aisstream/ais-message-models)
- [Beispiele (Python, JS, etc.)](https://github.com/aisstream/example)
