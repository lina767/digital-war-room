# Privacy & DSGVO Governance (DWR)

## Purpose and scope

This document defines the GDPR/DSGVO governance baseline for Digital War Room (DWR), covering:
- roles and responsibilities
- legal bases and processing boundaries
- processor and transfer controls
- references to retention, audit, and DSR procedures

It applies to frontend (`src/`), backend (`backend/`), and supporting operations.

## Controller and contact

- Controller: Lina Braun
- Contact: `social@linabraun.eu`
- Public privacy notice: `src/pages/Privacy.tsx`

## Core privacy principles in DWR

- Data minimization: collect only data required for operation, security, and selected product features.
- Purpose limitation: use data only for declared purposes.
- Storage limitation: apply explicit retention windows and deletion rules.
- Integrity and confidentiality: least-privilege access, hashed secrets, and secure transport.
- Accountability: auditable events and documented procedures.

## Processing inventory reference

The formal record of processing activities is maintained in:
- `docs/ROPA-RECORD-OF-PROCESSING.md`

## Legal bases (high-level)

- Art. 6(1)(f) GDPR: secure service operation, abuse prevention, technical reliability.
- Art. 6(1)(a) GDPR: newsletter subscription and related communication flows (double opt-in).

## Processors and third-country transfers

Current processors used by the application stack include hosting/analytics and email delivery providers.
Third-country transfers must rely on valid transfer mechanisms (e.g., adequacy decision or SCCs where applicable).

Operational tracking of processors and transfer notes is maintained in:
- `docs/ROPA-RECORD-OF-PROCESSING.md`

## Technical and organizational measures (TOMs)

- Tenant-aware auth context in backend middleware.
- API key hashing for tenant API keys.
- Input sanitization on conflict-driven endpoints.
- PII-aware log redaction utilities.
- Audit event schema and retention controls.

Detailed controls:
- `docs/AUDIT-TRAIL-POLICY.md`
- `docs/DATA-RETENTION-POLICY.md`

## Data subject rights (DSR)

DWR supports rights handling through an operational runbook:
- `docs/DSR-RUNBOOK.md`

The runbook defines request intake, identity verification, timeline management, fulfillment, and evidence.

## Review cadence

- Quarterly compliance review (privacy docs, retention rules, processors, DSR sample case).
- Event-driven review on architecture or provider changes.

