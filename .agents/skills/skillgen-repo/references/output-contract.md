# Generated Skill Output Contract

`scripts/create_skill_from_repo.py` creates a draft documentation skill. Codex should then complete and polish it.

## Directory Layout

```text
docs-<topic>/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   └── update_docs.py
└── references/
    ├── INDEX.md
    ├── manifest.json
    ├── source-map.json
    ├── original/
    ├── source/
    └── inferred/
```

## File Roles

- `SKILL.md`: Trigger description, quick navigation, source-grounding rules, and essential usage patterns.
- `agents/openai.yaml`: UI metadata.
- `references/INDEX.md`: Human-readable generated inventory and authoring worklist.
- `references/manifest.json`: Machine-readable repository identity, classification signals, script limits, copied counts, warnings, and timestamps.
- `references/source-map.json`: Machine-readable list of every generated reference file and its original repository path.
- `references/original/`: Mirrored upstream documentation and examples, transformed only enough to be readable offline.
- `references/source/`: Focused code, config, schema, test, and example capsules.
- `references/inferred/`: AI-authored documentation grounded in `original/` and `source/`.
- `scripts/update_docs.py`: Refresh wrapper that calls `skillgen-repo`.

## Manifest Expectations

`manifest.json` should include:

- generator name and version.
- generated timestamp.
- source repository value supplied by the user.
- resolved local path used during generation.
- Git remote and commit when available.
- classification signals.
- limits used for docs and source evidence.
- counts for mirrored docs, source capsules, inferred placeholders, skipped files, and warnings.

## Source Map Expectations

Each `source-map.json` entry should include:

- generated relative path under the skill.
- original repository-relative path.
- kind: `original`, `source`, or `inferred`.
- transform: `copied`, `markdown-view`, `code-capsule`, or `placeholder`.
- byte count.
- reason.

## Completion Checklist

Before reporting a generated docs skill as complete:

- Run the generator script successfully.
- Read `references/INDEX.md`.
- Inspect `manifest.json` warnings.
- Fill inferred docs that are needed for the repo type.
- Remove placeholder language that is no longer accurate.
- Validate the skill folder.
- Report skipped files or limits that may affect completeness.
