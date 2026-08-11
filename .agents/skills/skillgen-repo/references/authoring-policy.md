# Inferred Documentation Authoring Policy

Use this file when writing or revising `references/inferred/*.md` in a generated docs skill.

## Grounding Rules

- Base claims on mirrored docs, examples, tests, config files, schemas, public API declarations, and implementation files copied into `references/source/`.
- Add an `Evidence` section to every inferred page.
- Use repository-relative paths in evidence bullets.
- State uncertainty directly when evidence is incomplete.
- Prefer "The repository exposes..." or "The implementation indicates..." over upstream-sounding claims when the page is inferred.
- Do not invent setup steps, environment variables, API behavior, protocols, or compatibility promises.
- Do not treat package metadata as proof of runtime behavior unless implementation or tests support it.

## Source Copying Policy

Generated skills may need source evidence, especially for undocumented repositories. Copy focused source capsules rather than full application source by default.

Recommended evidence:

- Public entry points: `src/index.*`, `lib/index.*`, `pkg/**`, `cmd/**`, exported modules.
- Package metadata: `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `deno.json`, `tsconfig.json`.
- Schemas and protocols: `*.proto`, OpenAPI files, GraphQL schemas, SQL migrations, JSON schemas.
- Examples and tests that show intended usage.
- Configuration files that affect documented behavior.

Avoid copying:

- Generated bundles, lockfiles, vendored dependencies, minified files, build outputs, large snapshots, binary files, and full source trees when a focused subset is enough.

If the user asks for a fully source-backed offline skill, expand `--max-source-files` and `--max-source-bytes`, but keep `manifest.json` honest about the chosen limits.

## Suggested Inferred Pages

Use these pages when they fit the repo:

- `overview.md`: purpose, package shape, main concepts, current evidence.
- `installation.md`: install/build/use requirements that are explicitly evidenced.
- `quick-start.md`: smallest evidenced working path, usually from README/examples/tests.
- `api.md`: public API, CLI commands, services, schemas, or package exports.
- `architecture.md`: module layout, data flow, storage, networking, extension points.
- `configuration.md`: config files, environment variables, flags, defaults.
- `examples.md`: extracted examples and what they demonstrate.
- `limitations.md`: unsupported or unclear behavior.
- `open-questions.md`: facts that require upstream confirmation.

Do not create pages that are empty or generic. Merge small pages when the repo is narrow.

## Quality Bar

A generated docs skill is ready when:

- A reader can find the main entry points without reading the whole repository.
- Inferred claims cite concrete evidence.
- API and configuration docs distinguish documented, tested, and inferred behavior.
- Known gaps are recorded as open questions instead of being hidden.
- `SKILL.md` tells future Codex instances where to start and how to verify claims.
