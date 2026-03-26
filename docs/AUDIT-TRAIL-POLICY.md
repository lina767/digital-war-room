# Audit Trail Policy (DWR)

## Purpose

Define which data-processing actions are auditable in DWR, how audit events are structured, and how long they are retained.

## Audit event schema

All compliance-relevant audit events follow a common schema:

- `event_type`: machine-readable action key (for example `analysis.audit.persisted`)
- `actor_type`: `system`, `user`, or `service`
- `actor_id_pseudonymized`: hashed actor identifier (or `null`)
- `tenant_id`: UUID string when available
- `object_type`: target domain (`analysis_run`, `subscriber`, `retention_job`, `document_cache`)
- `object_id_hash`: hashed object identifier (or `null`)
- `outcome`: `success` or `failure`
- `reason_code`: optional short code (for example `retention_window`, `webhook_complaint`)
- `timestamp`: UTC ISO timestamp
- `meta`: non-sensitive structured context

## Mandatory audited activities

- analysis audit persistence and retrieval lifecycle events (where applicable)
- newsletter compliance events (unsubscribe, complaint/bounce handling)
- retention maintenance runs and deletion counts
- explicit data deletion operations triggered for compliance reasons

## Storage and integrity

- Primary store: `compliance_audit_events` table (when `DATABASE_URL` is configured).
- Fallback: structured logs if DB persistence is unavailable.
- Event payload must avoid raw PII in keys and values whenever possible.

## Access control

- Audit records are operational/compliance artifacts and should be available only to authorized maintainers.
- Use least-privilege principles for read access.

## Retention

- Default retention for compliance audit events: 365 days.
- See `docs/DATA-RETENTION-POLICY.md` for authoritative values.

## Verification

- Quarterly sample checks: event completeness, schema consistency, retention execution evidence.
- Any schema change requires updates to this policy and related implementation.

