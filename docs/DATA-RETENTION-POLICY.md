# Data Retention Policy (DWR)

## Policy objective

DWR retains personal or personal-adjacent data only as long as necessary for explicit purposes.
Deletion or anonymization must be technically enforceable and auditable.

## Retention matrix

| Data class | Storage surface | Purpose | Retention | Deletion method | Owner |
|---|---|---|---|---|---|
| Newsletter pending subscriptions | `newsletter_subscribers` (`confirmed_at IS NULL`) | Double opt-in completion | 30 days | Hard delete | Backend |
| Newsletter confirmed subscriptions | `newsletter_subscribers` (`confirmed_at IS NOT NULL`) | Delivery until withdrawal | Until unsubscribe + required proof period | Hard delete or compliance-safe proof retention | Backend |
| Analysis provenance audit rows | `analysis_audit` table | Traceability and quality evidence | 180 days | Time-based delete | Backend |
| Compliance audit events | `compliance_audit_events` table | Accountability/audit trail | 365 days | Time-based delete | Backend |
| In-memory document cache | `pdf_ingest_service._documents` | Document QA performance | 72 hours | In-memory purge | Backend |
| Embeddings (document-derived) | `embeddings` table | Retrieval for QA/search | 180 days (by recency) | Time-based delete (best effort) | Backend |
| Monitoring error details | In-memory monitoring store | Operational debugging | Process-lifetime bounded buffer | Automatic prune/overwrite | Backend |
| Analytics events | Analytics provider | UX and reliability insights | Provider defaults + consent-based collection | Provider controls | Frontend/Ops |

## Enforcement

- Retention cleanup runs as scheduled background maintenance in backend.
- Each retention run writes a structured audit event with counts and status.
- Failures must be logged with non-sensitive detail and retried in next cycle.

## Exceptions

If legal obligations require longer retention for specific records, the exception and legal basis must be documented in this file before implementation.

## Review cadence

- Quarterly review of all rows in this matrix.
- Immediate review when a new data source, storage location, or processor is introduced.

