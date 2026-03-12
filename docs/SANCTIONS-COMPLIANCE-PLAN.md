# Sanctions Compliance Layer – Plan (überarbeitet)

Erweiterung des Digital War Room um Sanctions-Compliance: Echtzeit-Sanktionschecks (inkl. 50%-Rule), Geofencing für Schiffe/Flüge, Supply-Chain-Monitoring und Compliance-Risiko-Scores. **Fokus: Iran (territoriale Gewässer, Hormuz, Öl-Sanktionsumgehung); Architektur so schlank und konfigurierbar wie möglich.**

---

## 1. Voraussetzung: Konfigurierbare Zonen im SIGINT-Agent

**Bevor** Geofencing oder Compliance-Layer gebaut werden, muss die Zone-Logik im SIGINT-Agent konfigurierbar sein.

- **Aktuell:** In [backend/agents/sigint_agent.py](backend/agents/sigint_agent.py) ist `_in_conflict_zone(lat, lon)` hardcoded auf `(10 <= lat <= 42) and (25 <= lon <= 65)` – nur Naher Osten.
- **Ziel:** Für Sanctions-Monitoring werden u.a. benötigt: **Schwarzmeer, Venezuela-Gewässer, Nordkorea**, sowie explizit **iranische Territorialgewässer + Hormuz-Straße**. Das darf nicht mehr fest verdrahtet sein.
- **Umsetzung:** Zonen als Konfiguration (z. B. Liste von Bounding-Boxen oder benannten Regionen aus YAML/JSON/Env), eine zentrale Funktion `_in_configured_zone(lat, lon, zone_set?)` die gegen diese Liste prüft. `_in_conflict_zone` wird zum Wrapper, der die konfigurierten „conflict“-Zonen nutzt; ein späterer Geofencing-Service nutzt dieselbe Konfiguration für „sanctions“-Zonen (inkl. Iran, Hormuz).

---

## 2. Sanctions Search – Firmen/Partner-Check

### 2.1 Datenquellen & Matching

- Anbindung offizieller Listen (OFAC, EU, UN); periodischer Abzug + lokaler Index für schnelle Suchen.
- **50%-Rule (Ownership Chains):** Sanctions Search muss von Anfang an nicht nur **Direct Matches** (Name = Listeneintrag), sondern **Ownership-Chains** abbilden können (z. B. „Firma X wird von Entity Y kontrolliert, Y ist sanktioniert“). Das erfordert ein Modell für Relationen (Parent/Subsidiary, Ownership-Prozent) und Abfragen der Art „ist diese Firma direkt oder über Beteiligungsstrukturen (≥50 %) mit einer sanktionierten Entity verbunden?“.
- **Fuzzy Matching – Schwellenwert-Policy (von Anfang an):**
  - OFAC allein hat oft **15+ Aliase pro Entity**; Firmennamen in Listen sind oft **Transliteration** (kyrillisch → latein, arabisch → latein) mit vielen Varianten. Ohne klare Policy explodieren False Positives.
  - **rapidfuzz** als technische Basis, aber:
    - **Kein einzelner magischer Schwellenwert.** Konfigurierbare, dokumentierte Policy, z. B.:
      - Strikte Schwelle für „MATCH“ (z. B. nur bei sehr hoher Ähnlichkeit + konsistentem Kontext).
      - Separat „REVIEW“-Stufe (möglicher Treffer, manuelle Prüfung empfohlen).
    - Dokumentation: Welche Schwellen für welche Listen? Wie gehen wir mit Transliteration um (normierte Formen, optional externe Normalisierung)?
  - Alle Treffer mit **Match-Level** und **Quelle** ausweisen; keine automatische Blockierung nur aufgrund von Fuzzy – immer Hinweis auf manuelle Due Diligence.

### 2.2 API & UI

- REST: `POST /api/compliance/sanctions-check` mit `{ query: string, include_ownership_chains?: boolean }`.
- Response: Treffer inkl. 50%-Chain wenn angefragt, Match-Level (EXACT / STRONG_FUZZY / WEAK_FUZZY / REVIEW), Quelle, Link zu Original.
- UI: Suchfeld + Ergebnisliste; klare Kennzeichnung von „REVIEW“ und Hinweis, dass es sich um Intelligence-Signale handelt (siehe Abschnitt Disclaimer).

---

## 3. Geofencing – AIS/ADSB vs. Sanktionszonen

### 3.1 Kein separater „geo_tracking_service“

- **SIGINT-Agent ist bereits der Tracking-Layer** (Schiffe, Flugzeuge, Positionen). Phase 1 braucht **keinen** neuen separaten Service für Tracking.
- Stattdessen: **dünner Geofencing-Wrapper** um die **bestehenden SIGINT-Outputs**:
  - Nach dem Lauf des SIGINT-Agents: vorhandene Listen (ships, aircraft) mit Positionen durchgehen.
  - Für jede Position prüfen: liegt sie in einer **konfigurierten Sanctions-/Risiko-Zone** (siehe Zonenkonfiguration oben)?
  - Wenn ja → **GeofencingAlert** erzeugen (Asset-ID, Zone, Timestamp) und an API/WebSocket ausliefern.

### 3.2 Iran: Kernfeature, nicht Nice-to-have

- **Iranische Territorialgewässer + Straße von Hormuz** sind explizit **Kernfeature** des Geofencings:
  - Zonen in der Konfiguration klar benennen (z. B. `IRAN_TERRITORIAL_WATERS`, `STRAIT_OF_HORMUZ`).
  - Alerts bei Einfahrt von getrackten Schiffen/Flugzeugen in diese Zonen – zentral für Öl-Sanktions-Compliance und Due Diligence.
- OFAC veröffentlicht **seit April 2025** aktiv **Guidance speziell für Shipping und Maritime Stakeholders** zur iranischen Öl-Sanktionsumgehung. Die Umsetzung soll diese Anforderungen berücksichtigen (z. B. Dokumentation/Links zu OFAC-Maritime-Guidance im UI oder in Doku).

### 3.3 Zonenmodell

- `SanctionsZone`: Name, Typ (sanktionsgebiet / hochrisiko / embargo), Geometrie (zunächst Bounding-Boxen, später optional Polygone), Quelle (EU/OFAC/UN/eigene Policy).
- Konfiguration **eine** Quelle der Wahrheit (shared mit SIGINT-Zonen), damit keine Doppelpflege.

---

## 4. AIS-Anomalie-Erkennung (Spoofing, Dark Activity)

- **Differentiator** gegenüber reinen Listen-Tools (z. B. Dow Jones Risk & Compliance, World-Check): Nutzung von **AIS-Daten** nicht nur für Position, sondern für **Anomalien**.
  - **Spoofing:** Verdacht auf manipulierte AIS-Positionen (z. B. Schiff „springt“ unrealistisch, oder sendet in Sanktionszone, während andere Quellen woanders zeigen).
  - **Dark Activity:** Schiffe mit AIS ausgeschaltet in sensiblen Zonen (z. B. Hormuz), Korrelation mit anderen Quellen (Satellit, Radar-Meldungen) wo möglich.
- Heuristiken und Datenquellen (z. B. Spire, SatAIS) in einem eigenen Unterabschnitt der Architektur planen; Ausgabe als **Anomalie-Flag** pro Asset, optional Integration in Compliance-Risiko-Score und Alerts.

---

## 5. Supply-Chain-Monitoring & Mittelsmänner

- **Routen-Screening:** TradeRoute mit Knoten (Hafen/Flughafen/Koordinate) gegen SanctionsZonen prüfen; Flag „touches sanctions zone“ + Liste betroffener Zonen.
- **Mittelsmänner-Heuristik – konfigurierbar, nicht hardcoded:**
  - Muster wie „Umleitung über bestimmte Drehkreuze“ (z. B. Dubai, Türkei, Belarus) sind **politisch sensibel** – man kategorisiert keine Länder pauschal als „suspicious hubs“ im Code.
  - Stattdessen: **konfigurierbare, dokumentierte Policy** (z. B. YAML/JSON: welche Transitländer unter welchen Bedingungen als „Review empfohlen“ gelten; Begründung und Quellen in Doku). Keine fest verdrahtete Länderliste im Code.
- Ausgabe: „suspicious hops“ pro Route mit Verweis auf die Policy und klare Erklärung („Pattern X aus Policy Y erfüllt“).

---

## 6. Compliance Risk Score & Scope-Disclaimer

### 6.1 Score-Engine

- Ordinaler Score (LOW / MEDIUM / HIGH / CRITICAL) + optionale Bandbreite; Treiber: Legal Exposure (Listen, Zonen), Operational Exposure (Eskalation/Predictive), Verhaltensmuster (Supply-Chain, AIS-Anomalien).
- Heuristiken und Regeln dokumentieren; z. B. „direkter OFAC-Hit → mindestens HIGH“.

### 6.2 Liability: Disclaimer in jeder Ausgabe (ab Tag 1)

- **Nicht in Phase 3, sondern in jeder UI-Ausgabe von Anfang an:**
  - Klarer **Scope-Disclaimer**: „Dieses Tool liefert **Intelligence-Signale**, keine Rechtsberatung. Es unterstützt Due Diligence, ersetzt aber keine rechtliche Prüfung. Kein Legal Advice.“
  - Sichtbar bei: Sanctions Search Ergebnissen, Geofencing-Alerts, Supply-Chain-Status, **Compliance Risk Score** (z. B. unter jeder Score-Anzeige und im Briefing).
- So wird für Nutzer mit echten Handelsentscheidungen das **Liability-Risiko** von vornherein begrenzt.

---

## 7. Fokus Iran & Eleganz

- Die Umsetzung ist **bewusst Iran-fokussiert** (Territorialgewässer, Hormuz, Öl-Sanktionsumgehung, OFAC-Maritime-Guidance 2025). Andere Regionen (Schwarzmeer, Venezuela, Nordkorea) werden über **dieselbe konfigurierbare Zonen- und Geofencing-Architektur** abgedeckt – keine Sonderpfade, sondern eine elegante, erweiterbare Konfiguration.
- Phasen:
  - **Phase 1:** Konfigurierbare Zonen im SIGINT-Agent; Sanctions Search (inkl. 50%-Rule-Grundlage) mit Schwellenwert-Policy; dünner Geofencing-Wrapper auf SIGINT-Outputs; Iran/Hormuz-Zonen + Alerts; Disclaimer in allen relevanten UIs.
  - **Phase 2:** Supply-Chain-Modell, konfigurierbare Mittelsmänner-Policy; Compliance Risk Score mit Disclaimer.
  - **Phase 3:** AIS-Anomalie-Erkennung; feinere Geometrien; OFAC-Maritime-Guidance-Integration in Doku/UI.

---

## 8. Konkrete Implementierungsschritte (Priorität)

1. **SIGINT-Agent:** `_in_conflict_zone(lat, lon)` durch konfigurierbare Zonen ersetzen (z. B. `CONFLICT_ZONES` / `SANCTIONS_ZONES` aus Config), inkl. Iran, Hormuz, Schwarzmeer, Venezuela, Nordkorea.
2. **Zonen-Config:** Einheitliche Definition von SanctionsZones (u. a. Iran territorial, Hormuz) und Anbindung an SIGINT + Geofencing-Wrapper.
3. **Geofencing-Wrapper:** Nach SIGINT-Lauf Schiffe/Flugzeuge gegen SanctionsZones prüfen, Alerts generieren; keine neue Tracking-Pipeline.
4. **Sanctions Search:** Index OFAC/EU/UN; Matching mit dokumentierter Schwellenwert-Policy; 50%-Rule (Ownership) im Datenmodell und in der API.
5. **Disclaimer:** In jeder Compliance-UI-Komponente und im Briefing den Scope-Disclaimer fest einbauen.
6. **Supply-Chain & Risk Score:** Nach Phase 1; Mittelsmänner nur über konfigurierbare Policy.
