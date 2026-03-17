# Copy Guidelines — Nischen-SEO & Longtail-Keywords

In allen **öffentlichen Texten** (Blog, Social Posts, Meta-Descriptions, Erwähnungen) die **Nischen-Phrasen zuerst** verwenden. Der Markenname „Digital War Room“ kann danach oder im gleichen Satz folgen. So treffen semantische und AI-Suchen die Plattform, nicht den eDiscovery-Konkurrenten.

## Kernphrasen (immer vor dem Markennamen nutzen)

- **AI-powered OSINT conflict monitoring platform**
- **multi-agent geopolitical intelligence dashboard**
- **real-time Iran conflict OSINT tracker**

## Regeln

1. **Titel / Headlines:** `[Longtail-Phrase oder Seitenthema] | Digital War Room` — Marke am Ende.
2. **Meta-Description / og:description:** Erster Satz = passende Longtail-Phrase, dann kurzer Nutzen; Marke optional am Ende.
3. **Social / Blog:** Erster Satz enthält eine der drei Phrasen; „Digital War Room“ im zweiten Satz oder als Zusatz (z. B. „… — the Digital War Room“).
4. **JSON-LD / Share-Texte:** Gleiche Phrasen in `name`/`description`; Marke nur wo nötig (z. B. `og:site_name`).

Technische Umsetzung: [src/lib/seoCopy.ts](../../src/lib/seoCopy.ts) — alle SEO-Texte zentral, damit Änderungen einmalig gepflegt werden.
