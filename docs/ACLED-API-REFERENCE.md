# ACLED API — Vollständige Referenz

Zusammengetragen aus der offiziellen ACLED-Dokumentation (Stand: März 2026).

**Quellen:** [acleddata.com/api-documentation/getting-started](https://acleddata.com/api-documentation/getting-started), `/acled-endpoint`, `/elements-acleds-api`, `/deleted-endpoint`, `/cast-endpoint`

---

## 1. Übersicht

ACLED (Armed Conflict Location & Event Data) ist ein unabhängiger Konfliktmonitor mit Echtzeit-Daten zu politischer Gewalt und Protesten weltweit. Die API ermöglicht programmatischen Zugriff auf den gesamten Datensatz.

- **Base URL:** `https://acleddata.com/api/`
- **Endpoints:**
  | Endpoint | Pfad | Beschreibung |
  |----------|------|--------------|
  | ACLED | `/api/acled/` | Kern-Datensatz: politische Gewalt, Demonstrationen, strategische Entwicklungen |
  | Deleted | `/api/deleted/` | Gelöschte Event-IDs zum Aktualisieren lokaler Datensätze |
  | CAST | `/api/cast/` | Conflict Alert System — aggregierte Daten |

- **Antwortformate:** JSON (Default), CSV, XML

---

## 2. Authentifizierung

### 2.1 Cookie-basiert (Browser / Postman)

1. Einloggen auf https://acleddata.com
2. Beliebige API-URL im Browser aufrufen, z.B. `https://acleddata.com/api/acled/read?limit=10`
3. Für Postman: `POST https://acleddata.com/user/login?_format=json` mit Body (JSON):
   ```json
   { "name": "DEINE-EMAIL", "pass": "DEIN-PASSWORT" }
   ```
4. Session ist danach aktiv — kein expliziter Token nötig.

### 2.2 OAuth (Programmatischer Zugriff)

**Schritt 1: Access Token anfordern**

```bash
curl -X POST "https://acleddata.com/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=DEINE-EMAIL" \
  -d "password=DEIN_PASSWORT" \
  -d "grant_type=password" \
  -d "client_id=acled"
```

Response:

```json
{
  "token_type": "Bearer",
  "expires_in": 86400,
  "access_token": "ACCESS-TOKEN-HERE",
  "refresh_token": "REFRESH-TOKEN-HERE"
}
```

| Variable   | Wert                          |
|-----------|--------------------------------|
| username  | Deine registrierte E-Mail      |
| password  | Dein myACLED-Passwort          |
| grant_type| `password` (fest)              |
| client_id | `acled` (fest)                 |

- **Access Token:** 24 Stunden gültig  
- **Refresh Token:** 14 Tage gültig  

**Schritt 2: Token im Request verwenden**

```bash
curl -H "Authorization: Bearer ACCESS-TOKEN-HERE" \
     -X GET "https://acleddata.com/api/acled/read?limit=10"
```

**Schritt 3: Token erneuern (optional)**

```bash
curl -X POST "https://acleddata.com/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "refresh_token=DEIN_REFRESH_TOKEN" \
  -d "grant_type=refresh_token" \
  -d "client_id=acled"
```

---

## 3. URL-Aufbau

Schema:

```
https://acleddata.com/api/{endpoint}/read?_format={format}&{filter1}={wert1}&{filter2}={wert2}...
```

Beispiel:

```
https://acleddata.com/api/acled/read?_format=csv&country=Georgia&event_date=2022-01-01|2023-02-01&event_date_where=BETWEEN&limit=3000
```

---

## 4. ACLED Endpoint — Query-Filter

### 4.1 Wichtige Filter

| Filter | Typ | Beschreibung |
|--------|-----|--------------|
| `country` | exakt | Ländername (z.B. `Iran`, `Ukraine`) |
| `event_date` | | Datum des Events |
| `event_date_where` | | `BETWEEN` für Bereich (z.B. `event_date=2025-01-01\|2025-12-31`) |
| `year` | | Jahr |
| `event_type` | LIKE | z.B. Battles, Protests, Riots, Explosions/Remote violence |
| `sub_event_type` | LIKE | Unterkategorie |
| `actor1`, `actor2` | LIKE | Akteure |
| `region` | **numerisch** | 11 = Middle East, 12 = Europe, etc. |
| `latitude`, `longitude` | | Koordinaten |
| `fatalities` | | Anzahl Todesopfer |
| `fatalities_where` | | `>` für „größer als“ |
| `limit` | | Zeilen pro Call (Default 5000) |
| `page` | | Pagination |
| `fields` | | Nur bestimmte Spalten: `fields=event_id_cnty|event_date|event_type|country|fatalities` |

### 4.2 Regionscodes (numerisch im API-Filter)

| Region | Code |
|--------|------|
| Western Africa | 1 |
| Middle Africa | 2 |
| Eastern Africa | 3 |
| Southern Africa | 4 |
| Northern Africa | 5 |
| South Asia | 7 |
| Southeast Asia | 9 |
| **Middle East** | **11** |
| Europe | 12 |
| Caucasus and Central Asia | 13 |
| Central America | 14 |
| South America | 15 |
| Caribbean | 16 |
| East Asia | 17 |
| North America | 18 |
| Oceania | 19 |

### 4.3 Query-Typen

- **LIKE:** Teilstring-Match  
- **Exakt:** `admin1_where=%3D`  
- **Bereich:** `event_date=2022-01-01|2023-12-31&event_date_where=BETWEEN`  
- **Größer/Kleiner:** `fatalities=5&fatalities_where=>`

---

## 5. Rückgabe-Daten (Spalten)

Wichtige Spalten: `event_id_cnty`, `event_date`, `year`, `disorder_type`, `event_type`, `sub_event_type`, `actor1`, `actor2`, `inter1`, `inter2`, `country`, `admin1`, `admin2`, `location`, `latitude`, `longitude`, `geo_precision`, `source`, `notes`, `fatalities`, `tags`, `timestamp`.

Bei JSON: Root enthält `status`, `success`, `count`, `data` (Array der Rows), `messages`.

---

## 6. Limits & Pagination

- Default: 5000 Zeilen pro Call. Anpassbar mit `&limit=X`.
- Pagination: `&page=1`, `&page=2`, … bis weniger Rows als Limit zurückkommen.

---

## 7. Deleted Endpoint

Zum Aktualisieren lokaler Datensätze (ACLED löscht wöchentlich Events bei Korrektur).

- Base: `https://acleddata.com/api/deleted/read?_format=csv`
- Filter: `deleted_timestamp`, `event_id_cnty` (mit `_where=BETWEEN` für Zeitraum).

---

## 8. CAST Endpoint

Conflict Alert System — aggregierte Daten pro Land/Zeitraum.

- Base: `https://acleddata.com/api/cast/read?_format=csv`
- Beispiel: `country=Brazil|Argentina&year=2023`

---

## 9. Fehlermeldungen

| Code | Bedeutung |
|------|-----------|
| 400 | Falsche Credentials (username/password oder OAuth) |
| 401 | Ungültiger/abgelaufener Auth-Token |
| 403 | Consent nicht akzeptiert, Profil unvollständig, oder Access denied |

---

## 10. Python-Beispiel (OAuth + Abruf)

```python
import requests

def get_access_token(username, password, token_url="https://acleddata.com/oauth/token"):
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = {
        'username': username,
        'password': password,
        'grant_type': 'password',
        'client_id': 'acled'
    }
    response = requests.post(token_url, headers=headers, data=data)
    if response.status_code == 200:
        return response.json()['access_token']
    raise Exception(f"Failed: {response.status_code} {response.text}")

token = get_access_token("deine@email.de", "passwort")
response = requests.get(
    "https://acleddata.com/api/acled/read?_format=json&country=Iran&year=2025&limit=100",
    headers={"Authorization": f"Bearer {token}"}
)
data = response.json()
rows = data.get("data", [])
```

---

## 11. Praxisbeispiele

- **Aktuelle Events (letzte 90 Tage):**  
  `event_date=2025-01-01|2025-03-16&event_date_where=BETWEEN`
- **Nur Battles mit Fatalities > 0, Middle East:**  
  `region=11&event_type=Battles&fatalities=0&fatalities_where=>`
- **Proteste in einem Admin-Gebiet:**  
  `country=Iran&event_type=Protests&admin1=Tehran`
- **Schlanke Response:**  
  `fields=event_id_cnty|event_date|event_type|country|latitude|longitude|fatalities|notes`
- **Mehrere Länder (ODER):**  
  `country=Iran|Iraq|Syria|Yemen&year=2025`

---

## 12. Wichtige Hinweise

- **Region:** Im API-Filter **numerisch** (z.B. Middle East = 11), im Datensatz als Text.
- **Sortierung:** Daten werden DESC nach Datum geliefert (neueste zuerst).
- **Updates:** Wöchentliche Aktualisierungen.
- **Attribution:** ACLED muss als Quelle angegeben werden (Attribution Policy).
- **EULA:** End User License Agreement gilt für alle Datennutzung.

---

## 13. Research-Tier, Lag und Troubleshooting

**Research-Zugang:** Die Read-API kann für die **letzten Monate bis „heute“** (wall-clock) **leer** oder stark reduziert sein: Der Datenstand endet bei diesem Tier oft **mit großem Abstand zur Kalender-Aktualität** (intern im Projekt mit ~12 Monaten Verzug beschrieben für Heatmap/Theater-API-Pfad). Abfragen über **längere Zeiträume** (z. B. 12–18 Monate in der Vergangenheit) liefern häufig trotzdem Zeilen.

**Separater Datenweg:** Wöchentliche **Aggregated-XLSX** (Nahost) mit Session-Login kann **aktuellere Wochenaggregationen** liefern; siehe `backend/services/acled_aggregated.py`.

**Diagnose:** `cd backend && python scripts/check_agents.py --test-acled` (OAuth + drei Zeitfenster). Log-Muster und Fallbacks: [ACLED-TROUBLESHOOTING.md](ACLED-TROUBLESHOOTING.md).

---

## Integration im Digital War Room

- **OAuth:** `backend/services/acled_auth.py` — nutzt `ACLED_EMAIL` und `ACLED_PASSWORD`, sendet `username` (=E-Mail), `password`, `grant_type=password`, `client_id=acled`. Token wird gecacht und vor Ablauf erneuert.
- **ACLED-Aufrufe:**  
  - GEOINT (Heatmap/Theater Map): `backend/agents/geoint_agent.py` → `get_conflict_events_for_heatmap()`, `get_conflict_hotspot_news()` (ReliefWeb + ACLED).  
  - CIVIL_UNREST: entfernt; Stub: `backend/agents/civil unrest_stub.py` (kein ACLED-Fetch).
- **Endpoints:**  
  - OAuth: `https://acleddata.com/oauth/token`  
  - Daten: `https://acleddata.com/api/acled/read` (mit `_format=json`, `country`, `limit`; optional `event_date` + `event_date_where=BETWEEN` für aktuelle Zeiträume).
- **Legacy:** Falls kein OAuth genutzt wird, kann optional die Legacy-API mit `ACLED_API_KEY` und `api.acleddata.com` verwendet werden (siehe Code).
- **Betrieb / Logs / Lag:** [ACLED-TROUBLESHOOTING.md](ACLED-TROUBLESHOOTING.md)
