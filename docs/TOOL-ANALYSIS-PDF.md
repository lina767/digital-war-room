# Tool-Analyse: Aktueller Stand vs. PDF „Digital War Room“ & Erweiterungsvorschläge

Stand: März 2025. Gegenüberstellung der **aktuell im Projekt integrierten Tools** mit den in der PDF genannten **OSINT-Tools** sowie konkrete **Empfehlungen** basierend auf API-Recherche.

---

## 1. Aktuelle Tools im Projekt (Kurzüberblick)

| Agent | Integrierte Quellen |
|-------|---------------------|
| **FININT** | Alpha Vantage (Brent, WTI), Polymarket (Odds + Tracked Wallets via Data API) |
| **SIGINT** | ADS-B (adsb.fi, adsb.lol), VesselFinder (public map API), Spire Maritime (optional), Conflict Reports RSS |
| **GEOINT** | NASA FIRMS, ReliefWeb, UCDP (optional), ACLED (optional), Sentinel Hub EO Browser Links |
| **SOCMINT** | Telegram, Nitter (X), Reddit, RSS, ReliefWeb |
| **TECHINT** | Alpha Vantage (ETFs), NewsAPI (Export Control), IODA, OONI, Cloudflare Radar, Shodan |
| **CYBER** | CISA KEV, Threat RSS (Mandiant/CrowdStrike), AlienVault OTX, GreyNoise |
| **ENERGY** | AGSI+ (Gasspeicher), Alpha Vantage (Commodities) |
| **PROTEST** | ACLED (Protests/Riots), GDELT |
| **DIPLO** | OFAC SDN, EU Consolidated List, UN/ICJ RSS |
| **PROXIMITY** | NASA FIRMS, Overpass (Schulen/Krankenhäuser), optional Tunnel-GeoJSON |

---

## 2. PDF-Tools vs. Projekt – Zuordnung

### GEOINT/IMINT (PDF)

| PDF-Tool | Im Projekt? | Anmerkung |
|----------|-------------|-----------|
| Sentinel-2 (Free/Low Res) | Teilweise | EO Browser **Links** (manuell); kein automatischer Tile-Download |
| Planet Labs / Maxar (High Res) | ❌ | Kommerziell, teuer; für „Panzer/Seriennummern“ – eher manuell |
| SAR (Schiffs-Tracking) | ❌ | Kein SAR-Stream integriert |
| **NASA FIRMS** | ✅ | Thermal-Anomalien (GEOINT + PROXIMITY) |
| Google Maps (Street View, Stau/Pizza-Index) | ❌ | Kein API-Tool; eher manuelle Recherche |
| Google Earth Pro (Stützpunkt-Veränderung) | ❌ | Desktop-Tool, kein Backend-API |
| **Sentinel Hub EO Browser** | ✅ | Links zu Infrarot-Analysen; Process API optional (SENTINELHUB_*) |

### SIGINT-lite (PDF)

| PDF-Tool | Im Projekt? | Anmerkung |
|----------|-------------|-----------|
| **ADSB-Exchange / Flightradar24** | ✅ Äquivalent | Stattdessen: **adsb.fi** + **adsb.lol** (Military + Region) |
| **MarineTraffic / VesselFinder** | ✅ VesselFinder | `get_naval_vessels` nutzt VesselFinder public map API; optional Spire |
| WebSDR (Militär-Funk) | ❌ | Audio-Streams, kaum automatisierbar als „Tool“ |
| SkyGlass (Flugrouten visualisieren) | ❌ | Visuelles Tool, keine Standard-API für Backend |

### SOCMINT (PDF)

| PDF-Tool | Im Projekt? | Anmerkung |
|----------|-------------|-----------|
| **Telegram** | ✅ | `scrape_telegram_channels` |
| **X (Bot, nicht API)** | ✅ Nähe | Nitter-Scraping für X-Inhalte (ohne offizielle X-API) |

### TECHINT (PDF)

| PDF-Tool | Im Projekt? | Anmerkung |
|----------|-------------|-----------|
| **Shodan** | ✅ | `_fetch_shodan_activity` (optional SHODAN_API_KEY) |
| **Wayback Machine** | ❌ | PDF: „archiviert gelöschte Webseiten/Tweets“ – API vorhanden |
| WHOIS/DNS-Analysen | ❌ | „Wer registriert welche Server?“ – gut automatisierbar |
| wigle.net (WLAN-DB) | ❌ | Nischen-Tool; API verfügbar |

### FININT (PDF)

| PDF-Tool | Im Projekt? | Anmerkung |
|----------|-------------|-----------|
| **Blockchain Explorer (Etherscan, Solscan)** | ⚠️ Teilweise | „Tracked Wallets“ = Polymarket Data API (Positions), **nicht** Etherscan/Solscan für On-Chain |
| **Prognosemärkte: Polymarket, Metaculus** | Polymarket ✅, Metaculus ❌ | Metaculus hat offizielle API (metaculus.com/api) |
| **Warenterminbörsen (Brent/WTI, Gold)** | Brent/WTI ✅ | **Gold** (und ggf. Gas) fehlt – Alpha Vantage kann das |
| **Zapper.fi** | ❌ | Dashboard für Krypto-Portfolios; GraphQL-API (build.zapper.xyz) |

---

## 3. Konkrete Erweiterungsvorschläge (priorisiert)

### Hoher Nutzen, API verfügbar, gut integrierbar

1. **FININT: Metaculus**
   - **Zweck:** Zweiter Prognosemarkt neben Polymarket (geopolitische Fragen).
   - **API:** [metaculus.com/api](https://www.metaculus.com/api/), Python z. B. über `forecasting-tools` oder direkte REST-Calls.
   - **Aufwand:** 1 Tool `get_metaculus_conflict_questions(conflict)` (oder ähnlich), in FININT_TOOLS + Fallback-Kette. Optional Env: `METACULUS_API_KEY` falls nötig.

2. **FININT: Etherscan (On-Chain Wallets)**
   - **Zweck:** Whale-Wallets, Sanktionsumgehungen (PDF); Ergänzung zu „Tracked Wallets“ (derzeit nur Polymarket-Positionen).
   - **API:** Etherscan Free Tier (z. B. 100k calls/day, 3/s), [etherscan.io/apis](https://etherscan.io/apis). Endpoints: balance, txlist, token balance.
   - **Aufwand:** Neues Tool z. B. `get_tracked_chain_wallets()` mit konfigurierbaren Adressen (wie TRACKED_WALLETS), optional `ETHEREUM_ETHERSCAN_API_KEY`. Evtl. Solscan für Solana ergänzbar.

3. **TECHINT: Wayback Machine (Archive.org CDX)**
   - **Zweck:** Prüfen, ob offizielle Tweets/Seiten gelöscht oder geändert wurden (PDF).
   - **API:** CDX Server: `https://web.archive.org/cdx/search/cdx?url=...&output=json` – keine Auth für Abfragen. Save-API für neue Archivierungen optional (LOW Auth).
   - **Aufwand:** Tool z. B. `get_wayback_snapshots(url: str, conflict: str)` oder Liste wichtiger URLs pro Konflikt; Ergebnis: letzte Snapshots, Timestamps. In TECHINT als zusätzliche Quelle.

4. **FININT: Gold (und ggf. Gas)**
   - **Zweck:** PDF nennt explizit Gold; Warenterminbörsen bereits da (Brent/WTI).
   - **API:** Bereits Alpha Vantage im Einsatz – Commodity-Endpoints (z. B. WTI, Brent) um Gold (z. B. XAU) erweiterbar.
   - **Aufwand:** Gering – neues Tool `get_gold_price()` analog zu Brent/WTI, in FININT Fallback parallel zu den anderen.

### Mittlerer Nutzen, API vorhanden

5. **FININT: Zapper.fi**
   - **Zweck:** Krypto-Portfolios visuell/aggregiert (PDF); für „Whale“- und Sanktionskontext.
   - **API:** [build.zapper.xyz](https://build.zapper.xyz/docs/api/) – GraphQL, API-Key. Portfolio-Daten über viele Chains.
   - **Aufwand:** Mittelhoch (GraphQL, evtl. andere Datenstruktur). Sinnvoll wenn ihr neben Polymarket-Positionen auch reine On-Chain-Portfolios braucht; sonst Etherscan zuerst.

6. **TECHINT: WHOIS/DNS**
   - **Zweck:** „Wer registriert welche Server?“ (PDF) – Domain-/Infra-Attribution.
   - **API:** whois über System-Call oder Bibliothek (python-whois); DNS über Standard-Resolve oder z. B. SecurityTrails/WhoisXML (kostenpflichtig). Einfachste Variante: whois + DNS-Abfrage für konfliktbezogene Domains (Liste in Config).
   - **Aufwand:** 1 Tool `get_domain_whois(domains: List[str])` oder pro Konflikt vordefinierte Domains; Ergebnis: Registrar, Creation/Expiry, Nameserver.

7. **SIGINT: MarineTraffic (optional zu VesselFinder)**
   - **Zweck:** PDF nennt beide; MarineTraffic größeres Netz, oft „bessere“ Abdeckung.
   - **API:** MarineTraffic API existiert (Basic/Essential/Enterprise), Preise oft auf Anfrage. VesselFinder bereits im Einsatz (public map).
   - **Aufwand:** Nur lohnend wenn ihr MarineTraffic-Key habt; dann zweite Quelle parallel zu VesselFinder (wie Spire), Deduplizierung nach MMSI/Name.

### Geringerer Nutzen / Nische / manuell

8. **GEOINT: Sentinel Hub Process API (Tiles)**
   - Bereits in Doku (SENTINELHUB_CLIENT_ID/SECRET); automatische Tiles statt nur EO-Browser-Links – erhöhter Aufwand, großer Mehrwert für automatische Bildanalyse.

9. **TECHINT: wigle.net**
   - WLAN-Datenbank; API verfügbar, Nische für Standort-/Infrastruktur-OSINT. Nur empfehlenswert bei konkretem Bedarf (z. B. „WLAN-Netzwerke in Konfliktzone“).

10. **WebSDR / SkyGlass**
    - Kein klassisches Backend-API-Tool; WebSDR = Audio-Streams, SkyGlass = Visualisierung. Eher Referenz in Doku oder manuelle Nutzung.

---

## 4. Schnell umsetzbare Erweiterungen (aus AGENT-EXTENSIONS.md)

Diese waren bereits in der Doku genannt; passen gut zur PDF:

- **FININT:** OFAC/Treasury-Listen als Tool – **umgesetzt:** `get_ofac_sanctions_highlights(conflict)` (gleiche Treasury-CSV wie DIPLO, FININT-Fokus Märkte/Sanktionen).
- **GEOINT:** Sentinel Hub Process API voll nutzen (wenn Keys vorhanden); mehr Regionen in `REGION_BBOX`.
- **SIGINT:** NOTAM-Integration – **umgesetzt:** `fetch_notams` aus iaea_tracker im SIGINT-Fallback, Ergebnis `notams`.
- **TECHINT:** Erweiterte Shodan-Queries – **umgesetzt:** zusätzliche Industrie-Protokolle (502 Modbus, 44818 EtherNet/IP, 47808 BACnet, 1911 Niagara, 102 S7); Censys optional später.

---

## 5. Empfohlene Reihenfolge (Priorität)

| Priorität | Erweiterung | Agent | Status |
|-----------|-------------|--------|--------|
| 1 | Metaculus | FININT | **Umgesetzt** – `get_metaculus_conflict_questions(conflict)` |
| 2 | Gold | FININT | **Umgesetzt** – `get_gold_price()` (METALS_API_KEY, metals-api.com) |
| 3 | Wayback Machine (CDX) | TECHINT | **Umgesetzt** – `_fetch_wayback_snapshots(conflict)` |
| 4 | Etherscan (On-Chain Wallets) | FININT | **Umgesetzt** – `get_tracked_chain_wallets()` (TRACKED_ETH_ADDRESSES) |
| 5 | WHOIS/DNS | TECHINT | Offen |
| 6 | Zapper.fi (optional) | FININT | Offen |
| 7 | MarineTraffic (optional) | SIGINT | Offen |

---

## 6. Referenzen

- **Projekt:** `docs/AGENT-EXTENSIONS.md`, `docs/AGENT-TOOL-CHAIN.md`, `docs/API-KEYS.md`
- **PDF:** „Digital War Room“ – OSINT-Tools (GEOINT, SIGINT, SOCMINT, TECHINT, FININT), Workflow (Lovable, Cursor, LangSmith)
- **APIs:** Metaculus (metaculus.com/api), Etherscan (etherscan.io/apis), Archive.org CDX (archive.org/developers/wayback-cdx-server.html), Zapper (build.zapper.xyz/docs/api/)

Wenn du möchtest, kann als Nächstes eine konkrete Implementierung für **Metaculus** oder **Wayback (CDX)** in den jeweiligen Agenten skizziert werden (inkl. Tool-Signatur, Env-Variablen und Fallback-Kette).
