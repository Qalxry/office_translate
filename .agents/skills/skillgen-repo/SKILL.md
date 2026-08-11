---
name: skillgen-repo
description: Generate or refresh documentation-style Codex skills from GitHub repositories or local Git clones. Use when a user wants to turn a repository into an offline docs skill by mirroring existing docs, extracting MD/MDX docs sites, indexing examples and source evidence, or writing clearly marked source-grounded inferred documentation for sparse or undocumented repositories. Also use when evaluating whether repo docs require a build step, llms.txt reuse, or AI-authored reference material.
---

# Repository To Documentation Skill

## Overview

Use this skill to create documentation skills from repositories, especially when the upstream project does not publish `llms.txt` or a clean docs website. The generator does mechanical work; Codex remains responsible for judgment, deep reading, and final inferred documentation.

## Workflow

1. Identify the source repository: GitHub URL, other Git URL, or local clone.
2. Run compact analysis first:
   ```bash
   python3 .agents/skills/skillgen-repo/scripts/analyze_repo.py <repo-url-or-path>
   ```
3. Classify the repository using `references/repo-classification.md`.
4. If the repo has `llms.txt`, prefer `$skillgen-llms-txt` unless the user specifically wants repo-derived source evidence too.
5. If the repo is a documentation site that appears to require dependency installation or a build, ask the user before running any install/build command. Without confirmation, extract source `.md`, `.mdx`, examples, and source evidence only.
6. Generate the draft docs skill:
   ```bash
   python3 .agents/skills/skillgen-repo/scripts/create_skill_from_repo.py <repo-url-or-path> --name docs-<topic>
   ```
7. Read the generated `references/INDEX.md`, `references/manifest.json`, and `references/source-map.json`.
8. Fill or revise `references/inferred/*.md` from the mirrored docs, examples, tests, and source evidence. Follow `references/authoring-policy.md`.
9. Finalize the generated `SKILL.md` so it gives concise navigation, evidence rules, and the most important usage patterns.
10. Validate both this generator skill and the generated docs skill with the skill validator.

## Repository Cases

- Existing `llms.txt`: route to `skillgen-llms-txt` by default, or combine with this skill when source evidence is needed.
- Docs directory plus examples: mirror docs, mirror examples, add focused source capsules, then write missing guides.
- MDX documentation site: extract `.mdx` sources into Markdown views; build only after user confirmation.
- Sparse docs: copy README and examples, then infer architecture/API/usage docs from source and tests.
- No docs: create a source-grounded documentation skill. Copy enough source evidence to support the inferred docs and label all inferred pages explicitly.

Read `references/repo-classification.md` for the decision tree.

## Scripts

`scripts/analyze_repo.py` inspects a local or remote Git repository and reports docs, examples, tests, languages, package managers, doc-site frameworks, build hints, and source evidence candidates. It does not install dependencies or run builds. The default output is a compact LLM-readable summary; use full output only when the top candidates and counts are not enough.

`scripts/create_skill_from_repo.py` creates a draft `docs-*` skill. It shallow-clones remote repositories, mirrors relevant documentation into `references/original/`, writes source capsules into `references/source/`, creates inferred-document placeholders, writes manifests, and adds a refresh script.

Useful commands:

```bash
python3 .agents/skills/skillgen-repo/scripts/analyze_repo.py https://github.com/org/repo
python3 .agents/skills/skillgen-repo/scripts/analyze_repo.py https://github.com/org/repo --candidate-limit 15
python3 .agents/skills/skillgen-repo/scripts/analyze_repo.py https://github.com/org/repo --full-output /tmp/repo-analysis.json
python3 .agents/skills/skillgen-repo/scripts/analyze_repo.py https://github.com/org/repo --json --full
python3 .agents/skills/skillgen-repo/scripts/create_skill_from_repo.py https://github.com/org/repo --name docs-repo --dry-run
python3 .agents/skills/skillgen-repo/scripts/create_skill_from_repo.py https://github.com/org/repo --name docs-repo --dry-run --full
python3 .agents/skills/skillgen-repo/scripts/create_skill_from_repo.py ./repo --skill-dir .agents/skills/docs-repo
```

## Output Contract

Generated skills should contain:

- `SKILL.md`: concise entry point for using the offline docs.
- `agents/openai.yaml`: UI metadata.
- `references/INDEX.md`: generated navigation and worklist.
- `references/manifest.json`: repository identity, classification, copied file counts, limits, and warnings.
- `references/source-map.json`: every mirrored or copied evidence file and its original path.
- `references/original/`: mirrored upstream docs and examples.
- `references/source/`: focused code/config/test/example evidence capsules.
- `references/inferred/`: AI-authored docs grounded in `original/` and `source/`.
- `scripts/update_docs.py`: refresh wrapper.

See `references/output-contract.md` before changing this structure.

## Inferred Documentation Rules

- Treat inferred docs as source-derived, not upstream-authored.
- Cite supporting repository paths in each inferred page.
- Prefer examples and tests over guessing intended behavior.
- Do not claim feature support unless there is evidence in docs, tests, public API, config, or implementation.
- When evidence is partial, say what is known and add an open question.
- Keep large source files out of generated docs; copy focused evidence capsules instead.

Read `references/authoring-policy.md` before writing inferred docs.

## Build Policy

Do not install dependencies, run package managers, or execute docs-site builds without explicit user confirmation. Many docs sites can be converted without building by reading source `.md`/`.mdx`; building usually produces HTML that must be converted back to Markdown and may lose MDX component semantics.
