

## Realistische Weltkarte fuer die ConflictMap

### Was wird geaendert
Die handgezeichneten SVG-Pfade werden durch eine echte geographische Weltkarte ersetzt, die mit der Bibliothek **react-simple-maps** gerendert wird. Diese nutzt echte TopoJSON-Geodaten und erzeugt realistische Laenderumrisse.

### Ansatz

**1. Neue Abhaengigkeit installieren**
- `react-simple-maps` -- rendert TopoJSON/GeoJSON als SVG-Pfade mit korrekter Projektion
- Nutzt die frei verfuegbare Natural Earth TopoJSON-Datei (110m Aufloesung, ca. 100KB)

**2. ConflictMap komplett umbauen (`src/components/dashboard/ConflictMap.tsx`)**
- `ComposableMap` + `Geographies` + `Geography` fuer die Weltkarte
- Laender werden als echte SVG-Pfade gerendert mit dem bestehenden Styling (dunkle Fuellfarbe, Primary-Stroke, niedriger Opacity)
- Konflikt-Marker werden auf **Laengengrad/Breitengrad** umgestellt statt Pixel-Koordinaten, z.B.:
  - Ukraine: [31, 49] statt x:570, y:160
  - US-Iran: [53, 32] statt x:620, y:230
- Der Kuestenlinien-Glow-Effekt bleibt als SVG-Filter erhalten
- Pulse-Animation und Hover-Labels bleiben unveraendert
- Legende bleibt am unteren Rand

**3. Marker-Positionierung**
- react-simple-maps stellt eine `Marker`-Komponente bereit, die automatisch Geo-Koordinaten in SVG-Positionen umrechnet
- Alle 12 Konfliktzonen behalten ihre Labels und Severity-Stufen

### Technische Details
- Die TopoJSON-Daten werden von einem CDN geladen (unpkg.com/world-atlas) -- kein lokaler Download noetig
- Die Projektion wird auf `geoMercator` oder `geoNaturalEarth1` gesetzt fuer ein natuerliches Erscheinungsbild
- Viewport und preserveAspectRatio werden beibehalten fuer responsive Darstellung
- Performance: Laender-Pfade werden nur einmal gerendert, nur Marker animieren
