# Record of Processing Activities (ROPA)

## Controller

- Controller: Lina Braun
- Product: Digital War Room (DWR)
- Contact: `social@linabraun.eu`

## Processing activities

| Activity | Data categories | Purpose | Legal basis | Recipients/processors | Retention reference |
|---|---|---|---|---|---|
| Website and API operation | IP, request metadata, user-agent, route metadata | Security, reliability, abuse prevention | Art. 6(1)(f) | Hosting/infra providers | `docs/DATA-RETENTION-POLICY.md` |
| Authentication and tenant access | User identifier, tenant identifier, auth headers/tokens, API key hashes | Access control and authorization | Art. 6(1)(f) | Auth/infra providers | `docs/DATA-RETENTION-POLICY.md` |
| Newsletter subscription | Email address, opt-in metadata, confirm/unsubscribe tokens | Daily briefing delivery and consent proof | Art. 6(1)(a) | Email delivery provider(s) | `docs/DATA-RETENTION-POLICY.md` |
| AI-assisted analysis outputs | Analysis metadata, provenance snapshots, quality flags | Product intelligence outputs and traceability | Art. 6(1)(f) | Model/API providers as configured | `docs/DATA-RETENTION-POLICY.md` |
| Document ingest and QA | Provided URLs, extracted document text/chunks, embeddings metadata | Compliance/document QA feature | Art. 6(1)(f) | Download targets and model/vector providers | `docs/DATA-RETENTION-POLICY.md` |
| Analytics (consent-gated) | Event metadata (no account profile required) | Product reliability and UX improvement | Art. 6(1)(a) | Analytics provider(s) | `docs/DATA-RETENTION-POLICY.md` |

## International transfers

Where providers process data outside EU/EEA, DWR uses appropriate safeguards where required by law.
Transfer mechanism details are reviewed during quarterly compliance checks.

## Security/TOM summary

- Transport security via HTTPS in production.
- Request sanitization for conflict and endpoint inputs.
- Tenant context isolation controls.
- Pseudonymization/hashing for selected identifiers.
- Audit trail events and retention job evidence.

## DSR and governance references

- `docs/PRIVACY-GDPR-DSGVO.md`
- `docs/DSR-RUNBOOK.md`
- `docs/AUDIT-TRAIL-POLICY.md`
- `docs/DATA-RETENTION-POLICY.md`

