---
name: quick-build
description: Create a lightweight, repository-grounded Build Brief and, when the user has authorized implementation, immediately build a direction-locked, medium-sized, high-cohesion feature without requiring PRD, SPEC, PLAN, or tracked proposal artifacts. Use after ideate's Ready Gate or when the user already provides clear behavior and constraints and asks to plan quickly, plan then implement, fast-track a feature, or review a compact implementation approach before coding. Supports plan-only, plan-and-build, and delegated quick-build modes. Do not use for ideas that still need creative direction, tiny obvious fixes, load-bearing architecture decisions, large migrations, multiple weakly coupled initiatives, or implementation of existing tracked proposals.
---

# Quick Build

Use this skill as the fast path between a build-ready idea and working code.

Produce a compact Build Brief grounded in the actual repository. Do not require PRD, SPEC, PLAN, or proposal files when the work is one cohesive feature and those artifacts would add more ceremony than value.

Do not repeat product ideation. Consume the selected direction, first product slice, constraints, and acceptance evidence as inputs. If those inputs are not stable, return to `ideate`.

## Boundaries

Use `quick-build` when:

- the product direction has passed `ideate`'s `Direction Lock` and `Ready Gate`, or the user supplied an equivalent clear brief
- the change is medium-sized: too substantial to implement safely from a one-line request, but small enough for one cohesive build effort
- repository inspection can resolve most implementation questions
- the user wants a lightweight plan, a fast implementation, or both
- no durable product or governance document is required

Route elsewhere when:

- product behavior, user value, or the first product slice is still open → `ideate`
- the task is a tiny, obvious fix → implement directly without this skill
- architecture boundaries, data ownership, security, or quality attributes are the load-bearing question → `system-design`
- the work is a major version migration or multi-phase refactor → `refactoring-planner`
- several weakly coupled initiatives need durable tracking → `create-proposals`
- the user wants to implement an existing tracked proposal → `implement-proposals`
- the user explicitly wants PRD or SPEC artifacts → `prd-spec-authoring`

Do not stretch `quick-build` to avoid a heavier workflow when the heavier workflow is justified.

## Authority Modes

Infer the mode from the user's wording and state it briefly when useful.

### Plan Only

Use when the user asks to plan, discuss implementation, inspect impact, or avoid code changes.

- inspect the repository
- produce the Build Brief
- do not edit files
- end with the recommended implementation action

### Plan And Build

Use when the user explicitly asks to plan and implement, build the feature, or continue through coding.

- produce a concise Build Brief
- continue into implementation in the same turn
- validate the agreed scope
- do not request another confirmation unless a material product decision, risky external effect, or scope expansion appears

### Delegated Quick Build

Use when the user says "直接做", "你决定", "快速实现", or otherwise delegates local implementation judgment.

- choose reasonable repository-local defaults
- label assumptions that affect behavior or compatibility
- keep the Build Brief very short
- implement immediately when the product direction and authority are clear

Delegation covers local implementation choices, not permission to change the product direction, ignore hard constraints, or expand scope.

## Hard Gate

A Build Brief is not implementation permission by itself.

Edit code only when the user has authorized implementation in the current request or prior confirmed context. If the user requested plan-only work, stop after the brief even when implementation appears straightforward.

When implementation is authorized, do not create an extra approval round merely because this skill contains a planning step.

## Context To Read

1. Read `.agents/memory/MEMORY.md` first when present; read relevant linked entries such as `taste.md`.
2. Read `AGENTS.md` and repository-specific contribution or validation instructions.
3. Recover the `Direction Lock`, Ready output, or equivalent user brief. Preserve its selected direction, constraints, non-goals, and acceptance evidence.
4. Inspect only the repository areas needed to make the brief executable:
   - entry points and neighboring implementation
   - existing types, storage, APIs, state, and UI patterns
   - relevant tests and validation commands
   - current worktree changes that overlap the task
5. Check proposals or docs-update files only when overlap or durable tracking is plausible. Do not turn every quick build into a proposal audit.

## Workflow

### 1. Confirm The Build Contract

State or infer:

- behavior to deliver
- scope guard and non-goals
- acceptance evidence
- authority mode
- biggest implementation assumption

Do not reopen product alternatives unless repository evidence invalidates the selected direction.

### 2. Inspect The Repository

Locate the smallest set of files and existing patterns that constrain implementation.

Prefer evidence over speculative planning. Identify:

- the current extension point
- reusable local patterns
- affected contracts or persistence
- relevant tests
- overlapping user changes

If repository inspection reveals a product decision that changes the first slice, stop and return that decision to `ideate`.

### 3. Produce The Build Brief

Keep the brief proportional to the work. For an ordinary quick build, target three to seven implementation steps.

Include:

- selected behavior and scope guard
- existing pattern to follow
- affected files, modules, or contracts
- implementation sequence and dependencies
- validation commands and user-visible evidence
- compatibility, migration, rollback, or risk notes when relevant
- assumptions that remain

Do not repeat the full product rationale, compare product directions, or create a formal roadmap.

### 4. Check That The Fast Path Still Fits

Before coding, verify:

- one cohesive implementation thread still exists
- the brief does not hide a major architecture decision
- the work can be validated in one bounded effort
- no durable multi-initiative tracking artifact is needed

If the scope no longer fits, recommend the correct heavier workflow and stop before partial implementation creates sunk cost.

### 5. Act According To Authority

For plan-only mode, stop after the Build Brief.

For authorized implementation:

1. use the Build Brief as the working implementation plan
2. implement the smallest complete end-to-end behavior that satisfies the agreed scope
3. preserve unrelated worktree changes
4. validate with the strongest proportionate checks
5. continue through straightforward fixes revealed by validation
6. stop only for a genuine blocker, a material product decision, or a meaningful scope expansion

Do not implement horizontal scaffolding, placeholder logic, or APIs with no real consumer merely to match the brief mechanically.

### 6. Report The Result

Report:

- behavior delivered or plan produced
- files and contracts affected
- validation performed and outcomes
- assumptions or residual risks
- deferred breadth

Do not automatically create proposal, PRD, SPEC, or PLAN files after a successful quick build.

## Build Brief Shape

Use only the fields that add value:

```markdown
**Build Brief**
- Behavior:
- Scope guard:
- Existing pattern:
- Affected areas:
- Contract/data changes:

**Implementation Path**
1. ...
2. ...
3. ...

**Validation**
- Commands:
- User-visible evidence:

**Risk**
- Compatibility/migration/rollback:
- Remaining assumptions:
```

The Build Brief is normally a conversation artifact. Write it to the repository only when the user explicitly asks for a persistent document.

## Planning Rules

- Prefer vertical, end-to-end behavior over layer-by-layer scaffolding.
- Follow existing repository patterns unless the selected direction explicitly requires changing them.
- Name concrete files or modules when repository evidence supports it; do not invent paths before inspection.
- Make validation executable: commands, assertions, rendered output, smoke behavior, or other observable evidence.
- Keep local two-way-door choices simple and expose only expensive or behavior-changing decisions.
- Avoid speculative abstractions and compatibility layers without a demonstrated need.
- Do not turn later optional breadth into mandatory phases.

## Self-Review

Before finishing, check:

- Was the product direction already stable enough for quick build?
- Did I choose the correct authority mode from the user's request?
- Did I inspect the repository before naming implementation details?
- Is the Build Brief materially lighter than PRD/SPEC/proposal workflows?
- Did I avoid repeating `ideate`'s product reasoning?
- If authorized, did I proceed to implementation without an unnecessary confirmation loop?
- Did I preserve unrelated worktree changes?
- Does validation prove real behavior rather than the existence of scaffolding?

## Anti-Patterns

- Re-running ideation inside the Build Brief.
- Writing a miniature PRD or SPEC under a different heading.
- Requiring a persistent plan file for a one-session build.
- Asking for approval twice after the user already authorized implementation.
- Editing code after a plan-only request.
- Using quick build for a large migration because formal planning feels slow.
- Producing a file list without inspecting the repository.
- Declaring success after adding placeholders or untested shells.
