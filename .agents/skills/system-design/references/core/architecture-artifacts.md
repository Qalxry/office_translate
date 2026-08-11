# Architecture Artifacts

Use these shapes when the user wants durable output. Adapt to the repository's existing doc layout first.

## Default Paths

- Architecture docs: `docs/architecture/`
- ADRs: `docs/adr/`
- API contracts: `docs/api/`
- Detailed implementation specs: `docs/specs/`

Do not impose these paths when the repo already has conventions.

## Architecture Brief

```markdown
# <System> Architecture Brief

## Intent
- Outcome:
- Users / operators:
- Primary workflows:
- Non-goals:

## Constraints
| Area | Target or Assumption | Validation |
| --- | --- | --- |

## Proposed Architecture
- Summary:
- Main boundaries:
- Deployment model:
- Data ownership:
- Trust boundaries:

## Building-Block Decisions
| Layer | Choice | Alternative | Constraint Served | Trade-off |
| --- | --- | --- | --- | --- |

## Quality Attributes
| Attribute | Scenario / Target | Design Response | Validation |
| --- | --- | --- | --- |

## Risks and Open Questions
| Risk or Question | Impact | Owner / Next Step |
| --- | --- | --- |

## First Implementation Slice
- End-to-end behavior:
- Acceptance checks:
- Observability / evidence:
- Deferred work:

## ADR Candidates
| Decision | Why ADR-worthy | Status |
| --- | --- | --- |
```

## C4 Views

Use C4 Context and Container for most systems. Add Component, Deployment, Dynamic, or data-flow views only when they clarify a decision.

Rules:

- Every view needs a title, scope, audience, assumptions, and legend.
- Every node needs a responsibility. Containers/components also need technology when known.
- Every relationship needs concrete intent and protocol where relevant. Avoid labels such as "uses" or "calls".
- Do not mix abstraction levels in one diagram.
- Keep diagrams reviewable. Split dense diagrams rather than producing a wall of boxes.

## Diagram Selection

| Need | Prefer |
| --- | --- |
| Explain system scope and external actors | C4 Context |
| Explain deployable units and data stores | C4 Container |
| Explain internals of one high-risk service | C4 Component |
| Explain async, saga, webhook, or agent loop behavior | Dynamic or sequence diagram |
| Explain data lineage, RAG ingestion, or ETL | Data-flow diagram |
| Explain cloud or network placement | Deployment/topology diagram |

Context and Container views are usually enough. Component and Code views should earn their cost by clarifying a real boundary, ownership, or failure mode.

## Diagram-To-ADR Loop

When a diagram introduces or changes a hard-to-reverse boundary, propose an ADR. When an ADR changes a boundary, deployment unit, data owner, or trust boundary, update the diagram.

Examples:

- Splitting a service into independently deployed units.
- Introducing a queue, stream, saga, or event sourcing boundary.
- Moving from static secrets to workload identity.
- Choosing a public API style or compatibility policy.
- Adding an agent tool with write permissions.

## ADR Gate

Write or propose an ADR only when all are true:

- Hard to reverse: migration, public API, data model, auth boundary, provider, deployment platform, or persistent operating model.
- Surprising without context: a future engineer would otherwise "fix" or re-debate it.
- Real trade-off: at least one viable alternative was considered.

For fuller guidance, read `decision-records.md`. Minimal ADR:

```markdown
# <Decision>

Status: Proposed | Accepted | Superseded by ADR-NNN
Date: YYYY-MM-DD

## Context
What problem, constraint, or conflict forced a decision now?

## Decision
What was chosen?

## Alternatives Considered
- Option:
- Rejected because:

## Consequences
- Positive:
- Negative / cost:
- Follow-up:
```

## Implementation Handoff

Keep handoffs narrow and testable:

```markdown
## First Slice
- Behavior:
- Touched areas:
- Interfaces:
- Data changes:
- Risks:
- Acceptance checks:
- Tests / validation:
- Telemetry:
```

Avoid horizontal phases that produce only stubs, shells, or placeholder infrastructure.
