# Source Directory

The Source Directory is the transparency layer for all external inputs used by Digital War Room.

Interactive page: <https://digital-war-room.com/sources>

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

The directory is generated from source metadata and agent-to-source mappings in the frontend codebase, then rendered as a searchable, filterable page.

This keeps source attribution auditable and ensures the dashboard can be traced back to source provenance.

Related pages:

- How It Works: <https://digital-war-room.com/how-it-works>
- Methodology: <https://digital-war-room.com/methodology>
- Documentation hub: <https://digital-war-room.com/docs/documentation>
