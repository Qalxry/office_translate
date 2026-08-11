---
name: skillgen-go-package
description: Generate or refresh documentation-style Codex skills from Go modules, import paths, pkg.go.dev package pages, GitHub Go repository URLs, or local Go repos. Use when a user wants an offline docs skill for a Go library/package with pkg.go.dev API docs, exported symbols, examples, README, versions, dependencies, vulnerabilities, and version-pinned references produced via godig.
---

# Go Package To Documentation Skill

## Overview

Use this skill to create offline `docs-*` skills for Go packages and modules using `godig` as the primary pkg.go.dev client. This is for Go package-index documentation, not HTML docs-site scraping and not general repository documentation synthesis.

## Workflow

1. Normalize the source:
   - Import path: `github.com/fsnotify/fsnotify`
   - Package URL: `https://pkg.go.dev/github.com/fsnotify/fsnotify`
   - GitHub repo URL: `https://github.com/fsnotify/fsnotify`
   - Local repo: read `go.mod` and use its `module` path.
2. Confirm `godig` is available before generation:
   ```bash
   godig version
   ```
   If it is missing, ask before installing it with `go install github.com/samber/godig/cmd/godig@latest`.
3. Generate the docs skill:
   ```bash
   python3 .agents/skills/skillgen-go-package/scripts/create_skill_from_go_package.py \
     github.com/fsnotify/fsnotify \
     --name docs-fsnotify
   ```
4. Inspect `references/INDEX.md` first. It must show the resolved concrete version near the top.
5. Check `references/manifest.json` for the source path, resolved version, `godig` commands, warnings, and skipped facets.
6. Validate both this generator skill and the generated docs skill with the skill validator.

## Version Policy

- Default to `--version latest`.
- Resolve `latest` to the concrete current version reported by pkg.go.dev before collecting package docs.
- Write the resolved version in obvious places: generated `SKILL.md`, `references/INDEX.md`, every generated reference page header, and `references/manifest.json`.
- Keep the original requested version in the manifest. If the generated skill is refreshed later and the request was `latest`, the refresh may intentionally move to a newer version.
- Use `--version vX.Y.Z` when the user wants a stable, pinned docs skill.

## Output Contract

Generated skills contain:

- `SKILL.md`: concise entry point for using the offline package docs.
- `agents/openai.yaml`: UI metadata.
- `references/INDEX.md`: navigation with module, package, and resolved version.
- `references/manifest.json`: generation metadata, commands, warnings, and version provenance.
- `references/source-map.json`: mapping from local reference files to `godig` commands.
- `references/pkg-go-dev/`: pkg.go.dev-derived Markdown references.
- `scripts/update_docs.py`: refresh wrapper.

Read `references/output-contract.md` before changing generated layout or manifest fields.

## Data Source Boundaries

- Use `$skillgen-go-package` for pkg.go.dev / Go package-index docs.
- Use `$skillgen-repo` for repository docs, source evidence, examples, tests, and inferred documentation from a repo.
- Use `$skillgen-website` for scraping HTML documentation websites.
- Use `$golang-pkg-go-dev` for one-off online lookup during normal coding; use this skill when the result should become a reusable offline docs skill.

## Commands

Create a docs skill in the current repo's `.agents/skills/` directory:

```bash
python3 .agents/skills/skillgen-go-package/scripts/create_skill_from_go_package.py \
  github.com/fsnotify/fsnotify
```

Pin a version:

```bash
python3 .agents/skills/skillgen-go-package/scripts/create_skill_from_go_package.py \
  github.com/fsnotify/fsnotify \
  --version v1.10.1 \
  --name docs-fsnotify
```

Use a local Go repo:

```bash
python3 .agents/skills/skillgen-go-package/scripts/create_skill_from_go_package.py \
  ./path/to/repo \
  --name docs-local-module
```

Include selected subpackages:

```bash
python3 .agents/skills/skillgen-go-package/scripts/create_skill_from_go_package.py \
  github.com/example/project \
  --extra-package github.com/example/project/subpkg
```

Refresh a generated skill:

```bash
python3 .agents/skills/docs-fsnotify/scripts/update_docs.py
```

## README Handling

`godig module readme -o raw` may return a JSON-escaped string rather than plain Markdown. The generator must decode that form before writing `references/pkg-go-dev/readme.md`, so code samples such as channel receives render as `<-watcher.Events` rather than escaped Unicode.

## Validation

Validate this generator skill after edits:

```bash
python3 /home/takagisan/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  .agents/skills/skillgen-go-package
```

Validate a generated docs skill the same way:

```bash
python3 /home/takagisan/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  .agents/skills/docs-fsnotify
```
