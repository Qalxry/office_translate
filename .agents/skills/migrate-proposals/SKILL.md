---
name: migrate-proposals
description: 'Audit and migrate versioned proposal files during major version transitions (V0→V1, V1→V2, etc.). Use when the user has completed prd-spec-authoring and refactoring-planner for a new version and needs to reconcile old proposals (proposals.p0.md, proposals.p1.md, proposals.p2.md, proposals.feat.md, proposals.feat.fp*.md, proposals.postponed.md, docs.updates.md) against the new PRD/SPEC/PLAN — archiving resolved items, carrying forward still-relevant items with fresh numbering, and identifying gaps. Produces clean new proposal files in the project root and archived originals under docs/v{N}/proposals/.'
---

# Migrate Proposals Across Versions

## Purpose

After a major version's PRD, SPEC, and PLAN have been written, the old version's proposal files need reconciliation. Some proposals were absorbed into the new documents, some were implemented, some are still relevant, and some are obsolete. This skill provides a systematic process to audit every old proposal item, decide its fate, archive the originals, and produce clean new proposal files.

## When to Use

- After completing `prd-spec-authoring` and `refactoring-planner` for a new version
- When old proposals (p0/p1/p2/feat/postponed) reference issues that may or may not have been addressed by the new design
- When `docs.updates.md` entries need reconciliation with updated PRD/SPEC

## Procedure

### Phase 1: Inventory

1. **List all proposal files** in the project root. Typical files:
   - `proposals.p0.md` — critical defects
   - `proposals.p1.md` — major contract deviations
   - `proposals.p2.md` — minor improvements
   - `proposals.feat.md` — feature proposals (overview)
   - `proposals.feat.fp*.md` — detailed feature proposals
   - `proposals.postponed.md` — deferred items
   - `docs.updates.md` — documentation sync items

2. **Read every item** in every file. For each item, record:
   - ID (e.g., P0-01, P1-03, FP-02, PP-01, DU-05)
   - Title
   - Current status (✅ fixed / open / postponed)
   - Brief summary of what it asks for

3. **Read the new version's documents** to understand what has been absorbed:
   - New PRD files (`docs/prd/*.md`)
   - New SPEC files (`docs/specs/*.md`)
   - New PLAN file (`PLAN.v{N}.md`)

### Phase 2: Triage

For each old proposal item, classify it into exactly one category:

| Category | Meaning | Action |
|----------|---------|--------|
| **absorbed** | The new PRD/SPEC/PLAN explicitly addresses this item's concern | Archive only. Note which new document section covers it. |
| **implemented** | Already marked ✅ in the old file and code reflects it | Archive only. |
| **still-relevant** | Not addressed by new docs, still a valid concern or feature idea | Carry forward to new proposal files. |
| **obsolete** | No longer applicable due to architecture changes (e.g., removed adapter) | Archive only. Note why obsolete. |
| **superseded** | Replaced by a different/better approach in the new design | Archive only. Note what supersedes it. |

**Decision rules for borderline cases:**
- If the new PLAN has a task that will fix it → `absorbed` (the PLAN covers it)
- If the new PRD describes the correct behavior but code doesn't yet match → `still-relevant` as a p1/p2 item (implementation gap)
- If a feat proposal was partially absorbed (some ideas taken, others not) → split: absorbed parts archive, remaining ideas carry forward
- If a docs.updates.md entry refers to V0 docs that no longer exist → `obsolete`
- If a postponed item's prerequisites are now met by V1 design → `still-relevant` (upgrade priority)

### Phase 3: Archive

1. **Create archive directory**: `docs/v{N-1}/proposals/`
2. **Move all old proposal files** from project root to archive:
   ```
   mv proposals.p0.md docs/v{N-1}/proposals/
   mv proposals.p1.md docs/v{N-1}/proposals/
   mv proposals.p2.md docs/v{N-1}/proposals/
   mv proposals.feat.md docs/v{N-1}/proposals/
   mv proposals.feat.fp*.md docs/v{N-1}/proposals/
   mv proposals.postponed.md docs/v{N-1}/proposals/
   mv docs.updates.md docs/v{N-1}/proposals/
   ```
3. Files are moved **intact** — no content modification. The archive is a historical record.

### Phase 4: Write New Proposal Files

Create fresh proposal files in the project root with:
- **Continued numbering** from the old files' last number (e.g., if old P1 ended at P1-19, new P1 starts at P1-20)
- Only **still-relevant** items from the triage
- Each item rewritten for the new version's context (reference new PRD/SPEC sections, not old ones)
- Severity/priority re-evaluated against the new architecture

**File structure:**

```markdown
# P{0|1|2} — {severity description}

> 最后审计日期: {today}
> 最后编号: P{0|1|2}-{NN}
> 承继自: V{N-1} proposals（已归档至 docs/v{N-1}/proposals/）

---

## {severity} P{X}-{NN}. {title}

> 严重程度: {level}
> 影响范围: {scope}
> 承继来源: V{N-1} {original ID}（{absorbed/still-relevant reason}）

### 问题描述
{rewritten for V1 context — reference new PRD/SPEC sections}

### 位置
{updated file paths and line numbers}

### 推荐修复方案
{updated to reflect V1 architecture}

### 最终修复情况
待修复。

---
```

For feature proposals: similar structure but use the feat format from AGENTS.md.

For `docs.updates.md`: create fresh file tracking any V1 code-vs-doc gaps discovered in the audit.

For `proposals.postponed.md`: carry forward items that are still valid deferrals; drop items whose prerequisites changed.

### Phase 5: Summary Report

Present a triage summary table to the user:

```markdown
| Old ID | Title | Category | New ID / Destination |
|--------|-------|----------|---------------------|
| P0-01 | ... | implemented | archived |
| P1-03 | ... | absorbed | covered by SPEC 03 §2 |
| P1-05 | ... | still-relevant | → new P1-20 |
| FP-07 | ... | obsolete | removed adapter |
```

## Anti-Patterns

| Anti-pattern | Why it's bad | What to do instead |
|---|---|---|
| Deleting old proposals without archiving | Loses historical context | Always move intact to docs/v{N}/proposals/ |
| Copying items verbatim to new files | References old docs/code that no longer exist | Rewrite each item for the new version's context |
| Resetting numbering to 1 | Breaks cross-references in git history and discussions | Continue from the old file's last number |
| Marking "absorbed" without citing the new doc section | Unverifiable claim | Always note which PRD/SPEC/PLAN section covers it |
| Carrying forward items without re-evaluating severity | Old severity may not apply to new architecture | Re-triage severity against V1 |
