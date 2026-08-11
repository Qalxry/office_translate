# Enterprise Integration and Capability Architecture

Use for enterprise systems, capability-aligned architecture, vendor products, ERP/CRM integrations, cross-domain workflows, system modernization, and architecture governance.

## First Questions

- Which business capability or value stream is in scope?
- Which systems own the process, data, and decisions today?
- What must remain stable for operations, compliance, customers, and downstream teams?
- Which integrations are API, event, file, batch, ETL, manual handoff, or vendor-specific?
- What governance, security, procurement, vendor, and roadmap constraints exist?
- What is current state, target state, and transition state?

## Design Surfaces

- Capability map and scope boundary.
- Application/component landscape.
- Canonical data objects and source-of-truth ownership.
- Integration catalog.
- Business events and state transitions.
- Security, privacy, compliance, and audit controls.
- Migration and coexistence plan.
- Roadmap themes and governance actions.

## Ubiquitous Language Gate

Enterprise designs often fail because the same word means different things across systems. Before proposing target architecture, capture:

| Term | Meaning | Owning system/domain | Synonyms or conflicts |
| --- | --- | --- | --- |

Run this gate for terms such as customer, account, tenant, order, subscription, entitlement, product, event, case, and project.

## Integration Patterns

- Synchronous API lookup for user-facing freshness.
- Command API for controlled state changes.
- Domain event for decoupled state notification.
- Batch/file for legacy or bulk transfer.
- CDC for low-impact data replication.
- ETL/ELT for analytics and reporting.
- Webhook for external customer or SaaS callbacks.
- Manual workflow when policy, trust, or tooling is not ready.

## Governance and Decisions

- Record principles that constrain future choices.
- Keep product/business and technical decisions traceable in ADRs or decision registers.
- Separate "target architecture" from "solution architecture" and implementation tasks.
- Do not invent enterprise facts. Mark unknown ownership, regulatory, vendor, and roadmap details as open questions.

## Public / Private Context Boundary

When architecture templates, reusable skills, or reference docs are shared publicly, keep real company context in private project repositories:

- Public: generic templates, workflow instructions, diagrams with placeholder names, reusable scripts.
- Private: real system names, people, vendors, incidents, ADRs, data classifications, credentials, topology, and roadmap.

If a generated document might cross this boundary, stop and ask for the target path or mark the document as private-only.

## Review Smells

- Target state ignores current-state operational dependencies.
- Data ownership is described by database location instead of business accountability.
- Integration table lists endpoints but not business purpose, owner, cadence, or failure behavior.
- Migration plan lacks coexistence, rollback, or decommissioning.
- Vendor claims are treated as independent evidence.
- No governance action for decisions that require architecture board, security, legal, or procurement approval.

## Expected Outputs

- Capability and scope summary.
- Current-state and target-state application map.
- Integration catalog.
- Data ownership table.
- Transition architecture and roadmap.
- Risks, dependencies, and open questions.
- ADR or decision-register candidates for durable product, vendor, data, integration, and platform choices.
