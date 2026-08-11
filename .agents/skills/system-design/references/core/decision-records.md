# Decision Records

Use when a choice is hard to reverse, surprising without context, crosses team boundaries, or will otherwise be re-litigated.

## Recordable Decision Signals

Create an ADR candidate or decision-register entry when the design changes:

- Public API, event contract, extension/plugin API, or compatibility policy.
- Data ownership, source of truth, schema lifecycle, retention, or migration path.
- Auth boundary, tenant isolation, trust boundary, privileged workflow, or approval gate.
- Runtime, framework, provider, deployment platform, orchestration model, or managed service.
- Integration pattern: sync API, async event, file/batch, CDC, webhook, or vendor connector.
- Operating model: SLO, incident ownership, rollout/cutover, backup/restore, or governance.

Do not record cheap local implementation choices unless they intentionally set precedent.

## Decision Gate

Before writing the record, classify:

| Gate | Question |
| --- | --- |
| Recordable | Will a future maintainer need the rationale? |
| Risk | What breaks if the choice is wrong? |
| Alternatives | What viable options were rejected? |
| Evidence | Which constraint, source, experiment, or incident drove the choice? |
| Owner | Who can accept, supersede, or revisit it? |

If there is only one technically or legally viable option, mark it as a constraint rather than pretending it was a free choice.

## Local ADR Shape

```markdown
# <Decision>

Status: Proposed | Accepted | Superseded by ADR-NNN
Date: YYYY-MM-DD

## Context
What problem, constraint, risk, or conflict forced a decision now?

## Decision Drivers
- Driver:

## Considered Options
| Option | Pros | Cons | Rejected Because |
| --- | --- | --- | --- |

## Outcome
Chosen option and why.

## Consequences
- Positive:
- Negative:
- Follow-up:
```

## Decision Register Shape

Use a register when decisions span many systems, teams, vendors, or sessions.

| ID | Decision | Scope | Status | Owner | Rationale Source | Supersedes |
| --- | --- | --- | --- | --- | --- | --- |

For remote or MCP-backed decision stores, let the agent provide semantic client hints before calling the service: `recordable`, `risk_level`, `signal_types`, and `classification_reason`. Backend heuristics can validate or override, but the agent should not discard its local context.

## Review Checklist

- The record states the conflict, not just the selected technology.
- At least one real rejected alternative is present, unless the choice is a constraint.
- Negative consequences are explicit.
- The decision has a status, owner, date, and supersession path.
- Product requirements, implementation tasks, and rationale are not mixed together.
