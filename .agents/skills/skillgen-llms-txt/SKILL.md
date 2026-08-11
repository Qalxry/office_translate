---
name: skillgen-llms-txt
description: Generate or refresh Codex skills from llms.txt documentation indexes. Use when a user provides an llms.txt URL or local llms.txt file and wants an offline documentation skill with mirrored Markdown references, an index, manifest, optional llms-full fallback, and an updater script.
---

# LLMS.txt To Skill

## Overview

Use this skill to turn an upstream `llms.txt` index into a reusable offline documentation skill. The generated skill follows the same pattern as `docs-*` documentation skills: a concise `SKILL.md`, focused Markdown files under `references/`, source `llms.txt`, optional `llms-full.txt`, `manifest.json`, and `scripts/update_docs.py`.

## Generation Workflow

1. Choose the generated skill name. If the user did not specify one, infer it from the `#` heading in `llms.txt` and normalize it to `docs-<topic>` lowercase hyphen-case (e.g. `docs-primevue4`, `docs-a2a`).
2. Run `scripts/create_skill_from_llms.py` with the user's `llms.txt` URL or local file.
3. Inspect the generated `references/index.md` and `references/manifest.json` for downloaded page count and failures.
4. Run the skill validator on the generated skill.
5. Report the generated skill path, page count, validation result, and any failed URLs.

Default placement: create generated skills in the current repository's `.agents/skills/` directory when it exists. Otherwise use `$CODEX_HOME/skills`, falling back to `~/.codex/skills`.

## Quick Start

Create a skill from a remote `llms.txt`:

```bash
python3 .agents/skills/skillgen-llms-txt/scripts/create_skill_from_llms.py \
  https://example.com/llms.txt \
  --name docs-example
```

Create in an exact directory:

```bash
python3 .agents/skills/skillgen-llms-txt/scripts/create_skill_from_llms.py \
  https://example.com/llms.txt \
  --skill-dir .agents/skills/docs-example \
  --name docs-example
```

Refresh an existing generated skill:

```bash
python3 .agents/skills/docs-example/scripts/update_docs.py
```

## Script Behavior

`scripts/create_skill_from_llms.py`:

- Parses Markdown links in the source `llms.txt`, grouped by `##` sections.
- Downloads the linked documents as Markdown where possible.
- Tries the listed URL first, then appends `.md` to extensionless HTTP URLs by default.
- Rewrites mirrored Markdown links to local relative paths when the linked target was also mirrored.
- Writes references atomically, refusing to replace an existing skill unless `--overwrite` is passed.
- Preserves existing `SKILL.md`, `agents/openai.yaml`, and updater script during refresh unless `--overwrite-skill` is passed.
- Infers `llms-full.txt` from a `llms-full` link or sibling `llms-full.txt` URL unless `--skip-full` is passed.

Useful options:

```bash
python3 .agents/skills/skillgen-llms-txt/scripts/create_skill_from_llms.py URL --dry-run
python3 .agents/skills/skillgen-llms-txt/scripts/create_skill_from_llms.py URL --workers 12
python3 .agents/skills/skillgen-llms-txt/scripts/create_skill_from_llms.py URL --recursive
python3 .agents/skills/skillgen-llms-txt/scripts/create_skill_from_llms.py URL --allow-html
python3 .agents/skills/skillgen-llms-txt/scripts/create_skill_from_llms.py URL --append-suffix ""
python3 .agents/skills/skillgen-llms-txt/scripts/create_skill_from_llms.py URL --skip-full
python3 .agents/skills/skillgen-llms-txt/scripts/create_skill_from_llms.py URL --overwrite
```

Use `--recursive` only when the upstream `llms.txt` is incomplete and same-origin links inside mirrored pages should also be mirrored. Use `--allow-html` only for sites that do not expose Markdown pages; the generated skill will still work, but HTML references are less token-efficient.

## Generated Skill Expectations

After generation, the target skill should contain:

- `SKILL.md`: concise instructions for using the offline docs.
- `agents/openai.yaml`: UI metadata with a default prompt.
- `references/index.md`: rewritten local navigation index.
- `references/**.md`: mirrored focused documentation pages.
- `references/llms.txt`: original source index.
- `references/llms-full.txt`: optional full bundle fallback.
- `references/manifest.json`: source URL, fetched URL, local path, content type, and failures.
- `scripts/update_docs.py`: refresh wrapper that calls this generator.

## Validation

Validate this generator skill after editing it:

```bash
python3 /home/takagisan/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  .agents/skills/skillgen-llms-txt
```

Validate a generated skill the same way:

```bash
python3 /home/takagisan/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  .agents/skills/docs-example
```
