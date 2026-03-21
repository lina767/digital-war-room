# Source Directory

The Source Directory is the transparency layer for all external inputs used by Digital War Room. The former standalone `/sources` page is now **embedded in the documentation hub** below the Markdown intro when you open [Documentation → Source Directory](https://digital-war-room.com/docs/documentation?doc=source-directory).

## Purpose

- expose every primary data source in use
- show which agents consume each source
- communicate reliability and access characteristics

## Reliability tiers

- **Official**: government, intergovernmental, or institutional sources
- **Curated**: established APIs/datasets with explicit operational contracts
- **Community**: open-source/community feeds and crowd-driven OSINT streams
- **Supplementary**: optional auxiliary or enrichment sources

## Source metadata

Each directory entry may include:

- source name and description
- reliability tier
- agent mappings
- key requirement flags
- free/paid marker
- registration or documentation URL

## Generation model

The directory is generated from source metadata and agent-to-source mappings in the frontend codebase (`src/lib/sourceDirectory.ts`, `agentsConfig`). In the documentation UI it is rendered as a **searchable, filterable** list so provenance stays auditable.

## Related

- [How It Works](https://digital-war-room.com/docs/documentation?doc=how-it-works)
- [Methodology](https://digital-war-room.com/docs/documentation?doc=methodology)
- [Documentation hub](https://digital-war-room.com/docs/documentation)
