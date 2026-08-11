# Evaluation and Gates

Use when a design needs approval points, readiness checks, evals, or evidence-backed validation before implementation or release.

## Gate Types

| Gate | Use when | Required evidence |
| --- | --- | --- |
| Clarification gate | Scope, terms, or constraints are ambiguous | Shared assumptions, glossary, unresolved questions |
| Design gate | Architecture choices are hard to reverse | Constraint register, alternatives, risks, ADR candidates |
| Validation gate | Output must satisfy a format or safety contract | Schema, checklist, test fixture, rendered diagram, lint |
| Deployment gate | Change affects production, cloud, data, or network | Plan, prechecks, rollback, ownership, observability |
| Completion gate | Agent claims work is done | Requirement traceability, commands run, evidence, residual risk |

Do not turn gates into ceremony. A gate earns its cost when skipping it could cause expensive rework, unsafe deployment, or unverifiable output.

## Evidence Patterns

- **Traceability table**: requirement or decision ID, source, check, evidence, verdict.
- **Scenario eval**: realistic prompt or workflow, expected behavior, rubric, baseline comparison.
- **Schema validation**: single source of truth for structured outputs plus semantic checks where schema is insufficient.
- **Behavioral fixture**: input prompt, expected artifact properties, validator command, known failure signals.
- **Adversarial validation**: separate finding from verification; ask the verifier to disprove the claim.

## Architecture Scenario Evals

For a reusable architecture skill or workflow, create 3-5 cases:

| Case | Expected uplift |
| --- | --- |
| Small CRUD SaaS | Avoid over-architecture; produce modular monolith and tenant/security basics. |
| Webhook receiver | Require signature verification, idempotency, retries, DLQ, and SSRF controls. |
| RAG assistant | Separate retrieval, memory, tools, eval, permission, and provider boundaries. |
| Cloud migration | Require current-state, coexistence, cutover, rollback, identity, and cost plan. |
| Architecture review | Lead with risks, severity, evidence, and required changes. |

Compare baseline vs treatment when possible. A good skill may show no uplift on easy cases; record that honestly rather than expanding instructions blindly.

## Readiness Checks

Before handoff:

- Every heavyweight building block maps to a constraint.
- Every critical failure mode has a recovery, fallback, or explicit acceptance.
- Every externally observable workflow has telemetry.
- Every public or cross-team contract has compatibility and ownership.
- Every deployment or migration has rollback or a named reason rollback is impossible.
- Unknowns are labeled as assumptions or open questions.

## Anti-Patterns

- Validation checks only format, while the design can still be factually wrong.
- The same agent invents a risk and then confirms it without fresh evidence.
- A gate asks for user approval without explaining the trade-off.
- Scenario evals assert a golden prose answer instead of checking design behavior.
- "Done" has no command output, trace, screenshot, diagram render, or review evidence.
