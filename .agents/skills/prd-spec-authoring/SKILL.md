---
name: prd-spec-authoring
description: 'Plan, write, and iterate PRD and SPEC documents for software projects. Use when the user asks to create/rewrite/refactor PRD documents, SPEC documents, technical specifications, product requirements, architecture documentation, or design documents. Handles versioned document migration (e.g., V0→V1), multi-file document suites, cross-document consistency, and proposal-to-PRD consolidation. Produces structured Markdown with mermaid diagrams, data model tables, state machines, and API specifications.'
---

# PRD & SPEC Authoring

## Purpose

Guide the creation of complete, internally consistent PRD (Product Requirements Document) and SPEC (Technical Specification) document suites for software projects. This skill encodes the workflow, formatting standards, quality criteria, and iteration strategy learned from authoring multi-file document suites at scale (~6000+ lines across 19 files).

## When to Use

- Creating a new PRD/SPEC suite from scratch
- Rewriting or versioning existing documents (e.g., V0→V1 migration)
- Consolidating feature proposals into formal PRD/SPEC
- Auditing existing documents for completeness and consistency

## Reference Files

- [PRD writing rules](./references/prd-rules.md) — PRD formatting, content standards, anti-patterns
- [SPEC writing rules](./references/spec-rules.md) — SPEC formatting, content standards, anti-patterns
- [Checklist](./references/checklist.md) — Pre-submission quality checklist

## Procedure

### Phase 1: Scope & Structure Alignment

Before writing any document, align with the user on scope and structure.

1. **Analyze inputs**: Read all source material — existing docs, feature proposals, bug reports, code. Use subagents for large codebases.

2. **Identify architectural changes**: Summarize what changes from the previous version (if versioning) or what the new system requires. Present as a change matrix:
   - What's new
   - What changed
   - What's preserved
   - What's removed

3. **Propose document structure**: List every planned file with a one-line description. For both PRD and SPEC suites:
   - PRD files should map to conceptual domains (topology, collaboration, execution, etc.)
   - SPEC files should map to implementation modules (core types, storage, each subsystem)

4. **Propose functional boundary**: What's in scope vs. out of scope for this version.

5. **Confirm with user**: Present the structure and boundary, get explicit approval before writing. If the user's ask is vague, ask clarifying questions about scope, audience, and priorities.

### Phase 2: Write PRD

Write PRD files in dependency order — overview first, then each domain.

6. **Write overview first** (`00_overview.md`): Project vision, core principles, architecture diagram (mermaid), version evolution summary, terminology table, document index.

7. **Write domain PRDs in order**: Each file should be self-contained but cross-reference related PRDs.

8. **PRD writing rules**: Follow [prd-rules.md](./references/prd-rules.md). Key principles:
   - PRD describes **what** and **why**, never **how** (no code)
   - Use mermaid diagrams liberally (architecture, state machines, sequences, flowcharts)
   - Use tables for data model fields (field, type, required, description) — not TS interfaces
   - Every design decision must have stated rationale or source reference
   - Every new term must appear in the terminology table

9. **Large file strategy**: For files likely to exceed 400 lines, write in parts (`{name}.part1.md`, `{name}.part2.md`) and concatenate with `cat ... > {name}.md && rm *.part*.md`.

10. **Present PRD to user**: After all PRD files are written, present a summary table (file, lines, size, content) and ask the user to review before proceeding to SPEC.

### Phase 3: Write SPEC

Only begin after user approves PRD.

11. **Write core types first** (`01_core-types.md`): All TypeScript interfaces and type definitions that other SPECs reference.

12. **Write storage schema** (`02_storage.md`): Complete SQL DDL with CHECK constraints, indexes, and triggers.

13. **Write remaining SPECs in dependency order**: Each SPEC should be traceable to its corresponding PRD section.

14. **SPEC writing rules**: Follow [spec-rules.md](./references/spec-rules.md). Key principles:
   - SPEC describes **how** — data models, algorithms, interfaces, error codes
   - Use concise pseudocode or TypeScript signatures, not large code blocks
   - Every SPEC must include: data model, processing flow, error codes, configuration
   - State machines as tables (current state, event, target state, condition, side effect)
   - API endpoints as tables (method, path, request, response, errors)

15. **Cross-reference validation**: After all SPECs are written, verify:
    - Every PRD concept has a corresponding SPEC section
    - Every SPEC type is defined in core-types
    - Every SPEC table exists in storage schema
    - Every SPEC error code is documented

### Phase 4: Review & Iterate

16. **Self-audit**: Check document quality against [checklist](./references/checklist.md).
17. **Present to user**: Summary table of all files with statistics.
18. **Iterate**: Address user feedback. For targeted changes, use replace_string_in_file. For major restructuring, rewrite affected files.

## Anti-Patterns

| Anti-pattern | Why it's bad | What to do instead |
|---|---|---|
| PRD contains TS interfaces | Crosses into SPEC territory, makes PRD verbose | Use field tables or natural language |
| SPEC contains large code blocks | Low information density, becomes outdated | Use concise pseudocode or signatures |
| Terms used without definition | Reader confusion, ambiguous meaning | Add to terminology table in overview |
| Mermaid-free PRD | Hard to grasp architecture without visuals | Every major concept gets a diagram |
| Design without stated rationale | "Why this way?" unanswered | State the source (proposal ID, principle, trade-off) |
| Monolithic document | Hard to navigate, hard to update | Split by domain (PRD) or module (SPEC) |
| Writing SPEC before PRD approval | Wasted effort if PRD changes | Always get explicit PRD sign-off first |
| Flat tool-call for huge files | Write truncation risk | Use part-file concatenation strategy |
