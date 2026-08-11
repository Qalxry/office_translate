# Architecture Review Checklist

Lead with findings. A review is useful only if it identifies decisions that are unsafe, unsupported, vague, or impossible to validate.

## Severity

- **Critical**: blocks design approval or creates major security, data-loss, reliability, compliance, or product risk.
- **High**: likely causes rework, wrong implementation, operational failure, or unbounded cost.
- **Medium**: weakens quality but can be resolved during implementation.
- **Low**: wording, organization, or minor completeness issue.

## Checklist

### Scope and Requirements

- Problem, users/operators, workflows, scope, non-goals, assumptions, and constraints are stated.
- Product scope is not silently expanded by architecture choices.
- Unknowns are visible and answerable.

### Constraints and Quality Attributes

- Scale, latency, availability, durability, consistency, cost, compliance, platform, and team constraints are measurable or explicitly assumptions.
- Capacity estimates exist where they affect decisions.
- SLOs, RPO/RTO, and performance budgets exist where relevant.

### Boundaries

- Actors, external systems, services/modules, data owners, trust boundaries, and integration boundaries are clear.
- Components are split by ownership and change/failure reasons, not just technical layers.
- Existing ADRs are respected or explicitly challenged with evidence.

### Building Blocks

- Compute/runtime, traffic, storage, cache, async/eventing, API style, coordination, resilience, observability, and deployment choices are justified.
- Heavyweight choices such as microservices, Kubernetes, Kafka, event sourcing, CQRS, multiple datastores, or custom orchestration are tied to constraints.
- Simpler alternatives were considered.

### Data and Contracts

- Data ownership, schema lifecycle, migration, retention, deletion, and backfill are addressed.
- API/event/file contracts have ownership, compatibility, error, retry, and idempotency rules.
- Multi-tenant access is enforced server-side.

### Security and Privacy

- Threat model covers untrusted inputs, authN/authZ, tenant isolation, secrets, audit, SSRF, injection, supply chain, and privileged operations.
- Sensitive data in logs, traces, prompts, backups, analytics, and vendors is controlled.
- AI/agentic systems have prompt-injection and tool-permission controls.

### Reliability and Operations

- Failure modes, retries, timeouts, circuit breakers, graceful degradation, DLQs, backup/restore, rollback, and incident ownership are defined where relevant.
- Observability can connect symptoms to user impact.
- Migration and cutover plans include coexistence and rollback.

### AI, Data, and Agentic Systems

- LLM is not a magic box: retrieval, memory, tools, evals, context budget, provider boundary, safety, and cost are first-class when relevant.
- Data systems define source of truth, query patterns, freshness, lineage, quality, and governance.

### Evidence and Validation

- Claims are backed by repo evidence, primary sources, or explicit assumptions.
- Hard-to-parse design inputs were normalized or parsed with a deterministic path before relying on freeform inference.
- Structured outputs such as findings, event catalogs, API contracts, or decision registers have a schema or review checklist.
- High-risk findings are independently verified or adversarially challenged.
- Current-source claims such as cloud SKUs, model capabilities, security standards, and product limits were verified recently.

## Output Format

```markdown
| Severity | Area | Finding | Required Change |
| --- | --- | --- | --- |

## Blocking Questions

## Assumptions To Confirm

## Recommended Revisions

## Residual Risk
```
