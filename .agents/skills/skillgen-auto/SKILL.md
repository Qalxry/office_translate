---
name: skillgen-auto
description: Automatically explore unknown documentation targets and route docs skill generation. Use when a user provides a project or library name, GitHub URL, local repo path, docs site URL, llms.txt URL, Go import path, or pkg.go.dev URL and wants Codex to decide whether to use skillgen-llms-txt, skillgen-website, skillgen-repo, skillgen-go-package, or a combined generation path.
---

# Skillgen Auto

## Overview

Use this skill as the first pass before creating a `docs-*` skill when the best source is not obvious. It gathers evidence, ranks routes, and then hands off to the existing specialized generators.

This skill does not replace the downstream generators. It chooses between them and records why.

## Quick Start

Run the explorer with every hint the user gave:

```bash
python3 .agents/skills/skillgen-auto/scripts/explore_target.py protovalidate \
  --output /tmp/skillgen-auto-protovalidate.md
```

Useful variants:

```bash
python3 .agents/skills/skillgen-auto/scripts/explore_target.py protovalidate \
  --github https://github.com/bufbuild/protovalidate \
  --docs https://buf.build/docs/protovalidate \
  --go-package buf.build/go/protovalidate \
  --output /tmp/skillgen-auto-protovalidate.md

python3 .agents/skills/skillgen-auto/scripts/explore_target.py \
  https://github.com/org/repo --json --output /tmp/skillgen-auto.json
```

Explicit GitHub repository URLs are inspected by shallow `git clone` and local file scanning by default. This matches `skillgen-repo` and avoids GitHub REST API rate limits. Use `--github-mode api` only when API metadata is specifically needed.

Then read the report and follow its recommended route. If the report is ambiguous, read `references/exploration-routing.md`.

## Workflow

1. Collect target hints. Prefer concrete hints in this order: direct `llms.txt` URL, docs site URL, GitHub URL, Go import path or pkg.go.dev URL, then bare project name.
2. Run `scripts/explore_target.py`. Use `--github`, `--docs`, and `--go-package` for user-provided hints instead of relying only on discovery.
3. Inspect the report sections in order: `Recommended route`, `Valid llms.txt endpoints`, `Documentation sites`, `GitHub repositories`, `Go packages`, then `Suggested next commands`.
4. Read the selected downstream skill before executing it if it is not already loaded:
   - `.agents/skills/skillgen-llms-txt/SKILL.md`
   - `.agents/skills/skillgen-website/SKILL.md`
   - `.agents/skills/skillgen-repo/SKILL.md`
   - `.agents/skills/skillgen-go-package/SKILL.md`
5. Generate the target docs skill with the selected generator or generator combination.
6. If more than one `docs-*` skill is created for the same target, edit every generated `SKILL.md` so they cross-reference each other. Each reference should state what the other skill covers and when to switch to it, for example conceptual docs vs Go API reference vs source-grounded repository evidence.
7. Inspect generated `references/INDEX.md` or `references/index.md`, `manifest.json`, and any failures.
8. Run the skill validator on every generated skill.

## Route Defaults

Prefer `skillgen-llms-txt` when a valid upstream `llms.txt` exists. It usually gives the most token-efficient, author-curated docs mirror.

Prefer `skillgen-website` when there is a scrapeable HTML docs site with enough same-origin docs links and no usable `llms.txt`.

Prefer `skillgen-repo` when the best docs are in repository Markdown/MDX, examples, tests, source evidence, or a docs site source tree. Also use it when the docs site needs a build step and the user has not approved builds.

Prefer `skillgen-go-package` when the reusable skill specifically needs pkg.go.dev API docs, exported Go symbols, examples, versions, dependencies, or vulnerabilities. Use it as a supplement when a broader docs site or repo skill exists but Go API reference is important.

Use a combined path when sources cover different needs:

- `llms.txt` plus repo evidence: generate from `skillgen-llms-txt`, then optionally add repo-derived examples/source evidence with `skillgen-repo`.
- Docs website plus Go API: generate the website skill, then create a separate `docs-*-go` package skill if pkg.go.dev adds useful exported-symbol detail.
- Sparse repo plus Go package: use `skillgen-repo` for source-grounded guides and `skillgen-go-package` for package API reference.

When a combined path creates multiple generated skills, add bidirectional links in their `SKILL.md` files. Keep the note short but explicit: list the sibling skill name/path, its source type, and the use case it is better for.

## Safety Rules

Do not install dependencies, run package managers, execute project code, or build docs during exploration. If a repository appears to need `npm install`, `pnpm install`, `make docs`, `go generate`, or similar, ask the user before running it and offer source extraction as the fallback.

Shallow cloning a public Git repository for file analysis is allowed. It is not a build or code execution step. Prefer this for explicit GitHub URLs.

Do not treat a guessed URL, search result, README badge, package metadata, or framework config as authoritative by itself. Use the report evidence and, when needed, open the linked source.

If only a bare name was provided and multiple plausible projects are found, stop after the exploration report and ask the user which target is intended.

## Explorer Output

The explorer is intentionally conservative. It can:

- Probe direct and guessed `llms.txt` endpoints.
- Search public GitHub repositories for a bare name. This uses GitHub REST API and is best-effort; skip it with `--no-github-search` when rate-limited.
- Inspect explicit public GitHub repositories by shallow cloning with Git, then scanning local file shape, docs files, docs frameworks, gh-pages branch, README links, and `go.mod`.
- Probe docs pages, same-origin links, sitemap and robots sitemap entries, page text size, and likely static-docs frameworks.
- Probe pkg.go.dev search results and package pages.
- Emit suggested downstream commands and website scraper `PAGES` entries.

The script uses Python standard library plus the local `git` executable. `GITHUB_TOKEN` only affects optional GitHub REST API paths such as bare-name repository search or `--github-mode api`; the token value is never printed.

## Detailed Routing

Read `references/exploration-routing.md` when:

- The report lists multiple plausible official sources.
- The project is a monorepo, docs repo, gh-pages site, MDX docs site, or package split across languages.
- The user only gave a name and the route is not high confidence.
- A weak model needs a line-by-line procedure for deciding which generator to run.
