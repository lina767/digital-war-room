# MCP (Cursor)

## RapidAPI – ADSBexchange.com

Die Datei `mcp.json` startet den MCP-Server **RapidAPI Hub - ADSBexchange.com** über das Wrapper-Skript `scripts/mcp-adsbexchange.mjs`.

**Key und Host aus `backend/.env`:**

- Das Skript liest **ADSBEXCHANGE_RAPIDAPI_KEY** und **ADSBEXCHANGE_RAPIDAPI_HOST** aus `backend/.env` (oder aus der Umgebung).
- Es gibt **keinen Key in `mcp.json`** – alles kommt aus der .env, eine Quelle für Backend und MCP.
- Host-Default: `adsbexchange-com1.p.rapidapi.com`.
