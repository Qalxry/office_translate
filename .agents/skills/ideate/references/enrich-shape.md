# Enrich And Shape

Use this flow after a direction is selected. The job is to make that direction coherent, distinctive, bounded, and ready for a planning, architecture, proposal, implementation, or stop decision.

Enrichment is not another round of unconstrained exploration. Preserve the `Direction Lock` unless new evidence or the user explicitly reopens it.

## Contents

- [Outcome](#outcome)
- [Workflow](#workflow)
- [Reopening The Direction](#reopening-the-direction)
- [Suggested Concept Shape](#suggested-concept-shape)
- [Anti-Patterns](#anti-patterns)

## Outcome

Finish with:

- a coherent experience or workflow
- explicit non-goals and trade-offs
- a real first end-to-end product slice
- acceptance evidence
- visible expensive decisions and open questions
- a `Ready Gate` decision and recommended handoff

Do not turn the result into a file-by-file implementation plan.

## Workflow

### 1. Re-establish The Lock

Restate or reconstruct the current `Direction Lock`:

- selected direction
- creative posture
- core mechanism
- qualities and constraints to preserve
- what may still change
- main sacrifice

If no direction has actually been selected, return to `explore-select.md` instead of pretending the lock exists.

### 2. Walk A Concrete Experience

Describe the most informative real scenario end to end:

- who acts and in what situation
- what input or context is available
- the first meaningful action
- how the system responds
- what changes for the user
- what proves the outcome occurred

For web, app, or workflow ideas, work backward from the strongest honest 30-second demonstration.

For AI or research ideas, use the smallest complete experiment loop: real input, actual processing or training, evaluation, metric or qualitative evidence, and a sanity check such as a single-batch overfit when relevant.

### 3. Add Substance Without Feature Piling

Enrich the selected mechanism through the parts that change whether it works:

- key states and transitions
- inputs, outputs, feedback, and persistence
- permissions, trust, and user control where relevant
- empty, messy, failure, and misuse cases where relevant
- language, tone, or interaction details that create the intended character
- one or two signature design moves worth preserving

Prefer a few consequential details over a large feature list.

### 4. Expose Scope And Trade-offs

State:

- non-goals
- attractive capabilities deliberately deferred
- the main bet
- the main sacrifice
- one or two decisions that are expensive to reverse

Treat public APIs, persistent data representation, permission boundaries, destructive behavior, external integrations, and user-trust commitments as expensive decisions. Leave cheap choices simple.

### 5. Derive The First Product Slice

A valid first slice is narrow, not shallow. It must:

- work end to end on one chosen path
- contain real behavior rather than placeholders
- be independently demoable or verifiable
- exercise the concept's main bet
- have clear acceptance checks
- defer optional breadth without blocking the core outcome

Define:

- end-to-end behavior
- acceptance checks
- evidence to show after implementation
- likely product or system areas involved, without turning them into an implementation task list
- deferred work

### 6. Stress Only What Matters

Use a bounded stress pass when the direction is fragile or high-stakes:

- **Assumption audit**: what must, should, and might be true
- **Premortem**: why this could feel like wasted work later
- **Edge walkthrough**: normal, empty, messy, and misuse cases
- **Reversibility check**: two-way, heavy, or one-way decisions

Convert findings into a smaller slice, a non-goal, an acceptance check, or an explicit open decision. Do not let stress testing become endless redesign.

### 7. Apply The Ready Gate

Use the `Ready Gate` from `SKILL.md`.

Recommend one next action:

- direct implementation for a small, concrete slice
- `quick-build` for a medium-sized cohesive feature that needs a lightweight Build Brief and optional immediate implementation
- `system-design` when architecture is now the load-bearing question
- `create-proposals` for durable future tracking
- another enrichment pass when a decision still changes the slice
- stop with the shaped concept

## Reopening The Direction

Do not silently redesign the concept during enrichment.

Propose reopening exploration when new information would change one or more of:

- primary user or job
- core value mechanism
- signature product promise
- hard constraint
- first slice's central behavior

Explain what invalidated the lock and ask whether to reopen it. Local details, naming, UI arrangement, or cheap implementation choices do not justify returning to exploration.

## Suggested Concept Shape

Use only the sections that help:

```markdown
**Direction Lock**
- Selected direction:
- Creative posture:
- Core mechanism:
- Preserve:
- Main sacrifice:

**Experience**
- Primary scenario:
- Signature moves:
- States and boundaries:
- Failure and user control:

**First Slice**
- End-to-end behavior:
- Acceptance checks:
- Evidence:
- Deferred work:

**Readiness**
- Expensive decisions:
- Open decisions:
- Recommended handoff:
```

This is a conversation artifact, not a mandatory persistent document.

## Anti-Patterns

- Reopening the entire idea space because one detail is uncertain.
- Quietly replacing the selected mechanism with a different concept.
- Treating enrichment as a request for more features.
- Producing UI shells, API stubs, schemas, or TODO scaffolds as the first slice.
- Hiding the main sacrifice to make the recommendation sound universally good.
- Writing an implementation plan before the user chooses that handoff.
