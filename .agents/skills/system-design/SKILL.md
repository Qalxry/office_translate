---
name: system-design
description: Design, review, or refine software and networked system architectures before implementation. Use when Codex is asked to architect a web service, API, distributed system, cloud platform, event-driven workflow, data or AI/LLM system, agentic system, enterprise integration, network/service topology, major technical design, architecture document, C4 diagram, ADR set, or architecture review. Focuses on constraints, quality attributes, trade-offs, boundaries, language/runtime choices, diagrams, decision records, and implementation handoff; not for small local code fixes.
---

# System Design

Use this skill to turn a product or engineering intent into a decision-grade architecture. The skill should make constraints, quality attributes, trade-offs, and hard-to-reverse decisions explicit before code is written.

## Boundaries

Prefer `ideate` first when the product direction or user workflow has not reached a `Direction Lock`. Use this skill once product intent is stable enough that architecture is the load-bearing question: system boundaries, data ownership, APIs, services, infrastructure, quality attributes, language/runtime choices, or durable technical decisions.

Do not implement production code from this skill. Produce an architecture brief, review findings, ADR candidates, diagrams, or an implementation handoff. Handoff to implementation only after the user confirms the design direction.

## Context To Read

1. Read project guidance first when present: `AGENTS.md`, `.agents/memory/MEMORY.md`, strategy docs, README, existing specs, proposal files, architecture docs, C4 diagrams, ADRs, and code structure relevant to the requested system.
2. Read `references/index.md` and load only the references that match the system type and risk profile. Do not load every reference file.
3. Read `references/core/quality-attributes.md` for any non-trivial production system.
4. Read `references/cross-cutting/language-runtime-selection.md` when language, runtime, framework, deployment target, or team skill could materially affect the architecture.
5. Read `references/core/architecture-artifacts.md` before writing persistent design docs, C4 diagrams, or implementation handoffs.
6. Read `references/core/decision-records.md` when an ADR, decision register, provider choice, API contract, data ownership boundary, or architecture governance question is material.
7. Read `references/cross-cutting/evaluation-and-gates.md` when the design needs explicit approval gates, scenario evals, production readiness checks, or evidence-backed validation.
8. Read `references/cross-cutting/source-provenance.md` when recommendations depend on vendor docs, field practice, local inference, or low-confidence research.
9. Read `references/research/reference-repo-lessons.md` when improving this skill, designing agentic architecture workflows, or looking for patterns from the indexed `ref_repos/` collection.
10. For cloud services, current provider products, AI/LLM systems, security guidance, regulations, or rapidly changing standards, verify current primary sources before recommending specifics; use `references/research/external-references.md` as the research map.

## Operating Modes

- **Design**: create a new architecture from an idea, product brief, requirements, or desired capability.
- **Review**: critique an existing architecture, design doc, PRD/SPEC, diagram, ADR, or codebase architecture.
- **Refine**: update an existing design after new constraints, review findings, implementation feedback, or product changes.
- **Decision support**: compare architecture options, language/runtime choices, storage choices, integration patterns, deployment models, or vendor/platform choices.

If the mode is unclear, infer it from the user's wording and state your assumption. Ask only when the answer would materially change the design.

## Workflow

1. **Frame the job**
   - State the intended outcome, system type, operators/users, primary workflows, and biggest assumption.
   - Decide which domain references to load from `references/index.md`.
   - If the system type is mixed, load the primary domain plus one adjacent domain, not the whole library.

2. **Gather load-bearing constraints**
   - Build a concise constraint register before choosing architecture.
   - Cover scale, latency, availability, consistency, data sensitivity, compliance, cost, team/ops capacity, platform constraints, migration constraints, and delivery timeline.
   - Use explicit assumptions or "baseline to measure" when numbers are unknown.

3. **Choose architecture boundaries**
   - Identify actors, external systems, bounded contexts or ownership domains, deployable units, data owners, trust boundaries, and integration boundaries.
   - Prefer the simplest architecture that satisfies the constraint register.
   - Treat microservices, Kubernetes, event streaming, multiple datastores, distributed transactions, and custom orchestration as complexity that must earn its keep.

4. **Select building blocks**
   - Choose compute/runtime, traffic path, storage, cache, async/eventing, API style, coordination, resilience, observability, and deployment model only where the system needs them.
   - For each important choice, name at least one rejected alternative and the constraint that drove the choice.
   - Read domain-specific references for specialized blocks such as RAG, agent tools, webhook delivery, data warehouses, cloud identity, or network segmentation.

5. **Treat language/runtime as an architecture decision when load-bearing**
   - Do not start with language debates.
   - Evaluate language/runtime only when it affects concurrency, latency, deployment, ecosystem, type safety, hiring/team skill, platform support, data/AI libraries, memory safety, or long-term maintainability.
   - If the repo already has a coherent stack and the choice is not load-bearing, follow the existing stack.

6. **Design quality attributes and failure behavior**
   - Define reliability, security, privacy, observability, performance, scalability, cost, operability, evolvability, and testability targets.
   - Use quality-attribute scenarios for critical attributes: stimulus, environment, response, and measurable response.
   - Name failure modes, fallback behavior, retry/idempotency strategy, data-loss tolerance, recovery target, and operational owner.

7. **Create diagrams and records**
   - For most software systems, produce C4 Context and Container views; add Component, Deployment, Dynamic, or data-flow views only when they clarify real decisions.
   - Record ADR candidates for hard-to-reverse, surprising, trade-off-based decisions.
   - Keep product requirements, architecture decisions, implementation tasks, and glossary/domain terms in separate artifacts.

8. **Review before handoff**
   - Run `references/core/review-checklist.md`.
   - Lead review results with blocking findings, then open questions, assumptions, recommended revisions, and residual risk.
   - Do not hide unknowns by inventing facts.

9. **Handoff**
   - Provide the recommended architecture, the main bet, the main sacrifice, non-goals, the first implementation slice, acceptance checks, and ADRs or docs to write.
   - If the user wants persistent docs, confirm the target path and write them using the repo's existing documentation layout. Default to `docs/architecture/` and `docs/adr/` only when the repo has no convention.

## Subagents

Use subagents only when the environment permits and the task benefits from independent research or review.

- Use read-only explorers for large codebases, existing architecture docs, reference repos, or provider docs.
- Use specialist reviewers for security, data, reliability, cloud/platform, or API surfaces when those areas are material.
- Give subagents raw artifacts and constraints, not your preferred answer. Ask for evidence paths, risks, option comparisons, and low-confidence areas.
- The main agent owns synthesis and final recommendations.

## Output Shapes

For lightweight design discussion, use:

```markdown
**Architecture Brief**
- Intent:
- System type:
- Constraints:
- Proposed architecture:
- Key boundaries:
- Data ownership:
- Quality attributes:
- Main decisions:
- Main trade-offs:
- Open questions:
- First implementation slice:
- ADR candidates:
```

For architecture review, lead with findings:

```markdown
| Severity | Area | Finding | Required Change |
| --- | --- | --- | --- |
```

Then include blocking questions, assumptions to confirm, recommended revisions, and residual risk.

For persistent documents, use `references/core/architecture-artifacts.md`.

## Anti-Patterns

- Designing from a diagram before constraints are known.
- Treating "scalable", "secure", "reliable", or "cloud-native" as requirements without measurable evidence.
- Choosing microservices, Kafka, Kubernetes, CQRS, event sourcing, GraphQL, or a polyglot datastore stack by default.
- Drawing the LLM, agent, webhook gateway, or data warehouse as one magic box.
- Loading the whole reference library instead of routing by system type, risk, and output artifact.
- Mixing product scope, architecture decisions, implementation tasks, and ADR rationale into one blob.
- Re-litigating existing ADRs without concrete friction.
- Asking a questionnaire instead of making explicit assumptions and producing a useful first pass.
- Recommending current cloud, AI, security, legal, or compliance specifics without checking primary sources.
