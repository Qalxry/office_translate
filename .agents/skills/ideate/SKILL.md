---
name: ideate
description: Route open-ended product, workflow, UX, architecture, research, feature, or 0-to-1 ideas through either exploration-and-selection or enrichment-and-shaping, using an explicit or inferred creative posture (faithful, exploratory, or inventive). Use when the user asks to brainstorm, invent, ideate, compare directions, make an idea more original, refine a chosen direction, add substance, stress-test early product intent, define a first product slice, or decide whether an idea is ready for planning, proposal tracking, architecture design, or implementation. Respect user-specified creativity and direction constraints; infer them from context when absent. Do not use for small unambiguous fixes, implementation of an accepted proposal, detailed implementation planning, or review/alignment of existing proposal files.
---

# Ideate

Use this skill as one stable entry point for early idea work without forcing every request through the same workflow.

Make two independent decisions:

1. **Phase**: explore and select a direction, or enrich and shape a selected direction.
2. **Creative posture**: faithful, exploratory, or inventive.

Phase determines what job to do. Creative posture determines how far to challenge the obvious answer. Do not confuse idea maturity with desired creativity.

## Boundaries

Use `ideate` while product intent, user workflow, concept direction, experience, or first product slice could still change materially.

Do not use `ideate` merely because implementation contains choices. Route directly when the user's requested action is already clear:

- use direct implementation for a small, concrete change
- use `quick-build` for a direction-locked, medium-sized, cohesive feature that should move through a lightweight Build Brief and optionally into same-turn implementation
- use `system-design` when product direction is locked and architecture decisions are now primary
- use `create-proposals` when the user wants durable backlog or proposal tracking
- use `implement-proposals` when the user wants to implement an existing accepted proposal
- use `review-align-proposals` when existing proposal files need discussion or correction

## Hard Gate

Do not write implementation code, scaffold directories, create proposal entries, or alter project files while the product direction is unconfirmed.

You may inspect the repository, read docs and memory, sketch text-only examples, and discuss trade-offs. A `Direction Lock` permits enrichment, not implementation. Move to implementation or persistent file edits only after the `Ready Gate` passes and the user chooses that handoff. If the user explicitly changes the task to proposal tracking before readiness, hand off to `create-proposals` and follow that skill's own alignment rules instead of writing from `ideate`.

## Context To Read

1. Read `.agents/memory/MEMORY.md` first when present. If it points to `.agents/memory/taste.md`, read it and treat durable preferences as context, not law.
2. For 0-to-1, product, workflow, architecture, innovative, or taste-sensitive work, inspect a cheap project strategy source such as `PROJECT-STRATEGY.md` when present. If none exists, make a provisional distinction between opinionated product core, conventional support areas, and deliberately simple edges.
3. Inspect `AGENTS.md`, README/spec docs, proposals, or relevant code only when they materially constrain the idea or can answer a question cheaply.
4. Read `references/creative-postures.md` whenever ideation is still needed.
5. Select exactly one primary phase reference:
   - read `references/explore-select.md` when no direction is selected or the user wants alternatives
   - read `references/enrich-shape.md` when a direction is selected and needs substance or a first product slice
6. Read both phase references in one response only when the user explicitly asks for end-to-end ideation and has delegated selection to you. Mark the `Direction Lock` before crossing phases.

## User Control

Apply this priority order:

1. Honor explicit user instructions about phase, creative posture, fixed constraints, selected direction, and desired next action.
2. Otherwise infer phase and posture from the request, repo context, risk, and durable taste memory.
3. If posture is unspecified, default to `exploratory`.
4. If two interpretations would materially change the result and neither is clearly preferable, ask one focused question with a recommended default.
5. Let the user change posture at any time with language such as "push stranger", "be more ambitious", "make it safer", or "keep the direction fixed".

Do not treat silence as approval. Do not repeatedly argue against an explicit veto. Challenge only soft assumptions; preserve hard constraints and clearly stated non-goals.

## Phase Routing

### Explore And Select

Choose this phase when one or more are true:

- the request is a wish, problem, theme, complaint, aesthetic ambition, or 0-to-1 opportunity
- no core direction or mechanism has been selected
- the user asks for alternatives, invention, surprise, reframing, or a stronger point of view
- the current idea appears anchored on an obvious artifact and the user permits premise changes

Read and follow `references/explore-select.md`.

### Enrich And Shape

Choose this phase when one or more are true:

- the user has selected a direction, or you selected one under explicit delegation and recorded a `Direction Lock`
- the user says not to change the direction and wants details, scenarios, boundaries, states, or acceptance checks
- the core mechanism is known but the product experience or first end-to-end slice is still thin
- exploration already produced a valid `Direction Lock`

Read and follow `references/enrich-shape.md`.

### Ready Route

Skip ideation or leave it as soon as the `Ready Gate` passes and the user wants action. Do not reopen the design space merely because planning or implementation has local choices.

## Routing Examples

| User signal | Phase | Creative posture |
|---|---|---|
| "Invent a surprising new direction; do not make me design it" | Explore and select | Inventive |
| "Compare a few strong approaches and recommend one" | Explore and select | Exploratory |
| "Keep this direction fixed and fill in the missing experience" | Enrich and shape | Faithful |
| "Choose for me, then flesh out your choice" | Explore, lock, then enrich | Infer from context; usually exploratory |
| "This direction is ready; plan it lightly and build it" | Leave ideation for `quick-build` | Not applicable |

## Direction Lock

Use a `Direction Lock` as the soft, reversible boundary between exploration and enrichment.

The lock passes when:

- one direction or deliberate combination has been selected
- the intended outcome and core mechanism can each be stated in one sentence
- hard constraints and preserved qualities are known
- the main bet or sacrifice is visible
- no unresolved fork would change the core experience

A lock may come from an explicit user choice, the user's acceptance of your recommendation, or the user's explicit delegation of the choice. It never comes from silence.

For non-trivial work, record it concisely:

```markdown
**Direction Lock**
- Selected direction:
- Creative posture:
- Core mechanism:
- Preserve:
- Allowed to change:
- Main sacrifice:
```

If new evidence invalidates the lock or the user asks to reopen the premise, return to exploration. Otherwise, enrichment must preserve it.

## Ready Gate

An idea is ready for handoff when:

- the outcome and user/operator are clear
- a direction and core mechanism are selected
- important constraints and non-goals are explicit
- the first end-to-end product slice is real, narrow, and testable
- acceptance evidence is known
- no unresolved decision would materially change that slice

At the gate, recommend one next action:

1. implement directly when the slice is small, concrete, and the user wants it now
2. use `quick-build` when implementation is medium-sized, cohesive, and should avoid unnecessary PRD/SPEC/proposal ceremony
3. use `system-design` when architecture boundaries or quality attributes are the next load-bearing decisions
4. use `create-proposals` when the work should be recorded for later
5. stop with the shaped concept when the user wants no further action

## Question Discipline

- Default to one focused question at a time.
- Do not begin with a questionnaire or ask the user to invent the answer from a blank page.
- Make a defensible guess, label it, and let the user correct it.
- Ask for selection only when the user has not chosen or delegated a direction.
- If the user says "whatever you think", treat that as delegated judgment only when the surrounding request clearly authorizes you to choose. State the chosen direction and its sacrifice.

## Preference Capture

When the user makes a durable taste or workflow preference explicit, ask whether to record it. If confirmed, use `distill-experience`; do not edit taste memory directly from this skill.

## Self-Review

Before responding, check:

- Did the user's explicit phase and creative posture override inference?
- Did I load the correct primary phase reference rather than blending both by default?
- Did I preserve hard constraints while challenging only soft assumptions?
- In exploration, are the directions structurally different rather than renamed variants?
- In enrichment, did I preserve the `Direction Lock` rather than silently redesigning the premise?
- Did I avoid implementation details before the `Ready Gate`?
- Is the next phase or handoff clear without forcing the user through an unnecessary workflow?

## Anti-Patterns

- Treating every vague request as a requirement-gathering exercise.
- Treating creativity as a synonym for adding more features.
- Running one fixed Baseline/Sharp/Strange template for every idea.
- Enriching every candidate before one is selected.
- Quietly changing a selected direction during enrichment.
- Letting an `inventive` posture override facts, safety, explicit constraints, or user vetoes.
- Reopening product ideation inside implementation planning without new evidence.
- Treating a proposal as permission to implement.
