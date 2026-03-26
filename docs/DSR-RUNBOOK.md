# Data Subject Rights (DSR) Runbook

## Scope

Operational procedure for handling GDPR/DSGVO rights requests in DWR.

## Supported request types

- Access (Art. 15)
- Rectification (Art. 16)
- Erasure (Art. 17)
- Restriction (Art. 18)
- Data portability (Art. 20)
- Objection/withdrawal (Art. 21 and consent withdrawal)

## Intake and verification

1. Receive request via designated contact (`social@linabraun.eu`).
2. Register request timestamp and request type.
3. Verify requester identity proportionate to risk before data action.
4. Set SLA target and owner.

## Processing steps

1. Identify relevant data domains:
   - newsletter records
   - tenant/auth-linked records
   - audit and processing metadata where legally required
2. Execute data lookup/export/update/delete actions.
3. Log completion evidence in audit trail (`compliance_audit_events`).
4. Send response to requester within legal timeline.

## Timelines and escalation

- Standard response target: within one month.
- Complex cases: document justification for extension and notify requester.
- Escalate blocked requests to controller contact with reason and next step.

## Evidence checklist

- request metadata (type, received_at, verified_at)
- systems checked
- actions performed
- exceptions/legal constraints
- completion timestamp and responder

## Links

- `docs/PRIVACY-GDPR-DSGVO.md`
- `docs/ROPA-RECORD-OF-PROCESSING.md`
- `docs/AUDIT-TRAIL-POLICY.md`
- `docs/DATA-RETENTION-POLICY.md`

