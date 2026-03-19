# Docker Compose für lokale Entwicklung

Lokale Entwicklung mit Docker: Backend, Frontend und PostgreSQL (pgvector) laufen in Containern.

## Voraussetzungen

- Docker und Docker Compose (v2)
- `backend/.env` (von `backend/.env.example` kopieren, API-Keys eintragen)

## Starten

```bash
# Aus Projektroot
docker compose up -d
```

Oder mit Dev-Override (z. B. `ENVIRONMENT=development` für structlog-Konsolenausgabe):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

## Dienste und URLs

| Service   | Port | URL / Hinweis |
|----------|------|----------------|
| Backend  | 8000 | http://localhost:8000 |
| Frontend | 8080 | http://localhost:8080 |
| PostgreSQL | 5432 | `postgresql://dwr:dwr@localhost:5432/dwr` (von Host) |

- **Health:** http://localhost:8000/health (Liveness)  
- **Readiness (inkl. DB-Check):** http://localhost:8000/health/ready  
- **Agent Health (Quellen/Agents):** http://localhost:8000/api/agents/health  
- **API-Docs:** http://localhost:8000/docs  

## Backend

- `backend/.env` wird per `env_file` geladen; `DATABASE_URL` wird im Compose auf `postgresql://dwr:dwr@db:5432/dwr` gesetzt.
- Code liegt als Volume gemountet (`./backend:/app`), Änderungen werden mit `--reload` vom Backend übernommen.

## Datenbank

- Volume `pgdata` persistiert Daten. Reset: `docker compose down -v` (löscht alle Volumes).
- Migrationen manuell, z. B.:  
  `docker compose exec backend sh -c 'psql "$DATABASE_URL" -f /app/migrations/001_pgvector_setup.sql'`  
  (falls Migrationsdatei im Image/Volume vorhanden.)

## Nur Backend + DB (ohne Frontend)

```bash
docker compose up -d db backend
```

Frontend dann lokal mit `npm run dev` (`.env` mit `VITE_API_URL=http://localhost:8000`).

## Logs

```bash
docker compose logs -f backend
docker compose logs -f frontend
```
