# Repository Classification

Use this file after `scripts/analyze_repo.py` reports the repository shape. Pick the strongest matching case and follow the recommended path.

## Decision Tree

1. If the repo has `llms.txt`, use `skillgen-llms-txt` unless source evidence or examples must be bundled too.
2. If the repo has a docs-site framework and many `.md`/`.mdx` files, treat it as a source docs site.
3. If the repo has `docs/`, `documentation/`, `examples/`, or `samples/`, treat it as a mirrored-docs repo.
4. If the repo has only README-style files plus meaningful tests/examples, treat it as sparse-docs.
5. If there are no useful docs, treat it as inferred-docs and rely on source, tests, config, schemas, and examples.

## Cases

### llms.txt Published

Signals:

- `llms.txt` or `llms-full.txt` at repository root or docs root.
- README links to a hosted `llms.txt`.

Action:

- Prefer `skillgen-llms-txt` for the core docs mirror.
- Use `skillgen-repo` only if the generated skill also needs examples, source capsules, or inferred architecture notes.

### Source Documentation Site

Signals:

- Docusaurus: `docusaurus.config.*`, `sidebars.*`, `docs/**/*.mdx`.
- VitePress: `.vitepress/config.*`, `docs/**/*.md`.
- Nextra: `theme.config.*`, `pages/**/*.mdx`, `app/**/*.mdx`.
- Mintlify: `mint.json`, `docs.json`, `*.mdx`.
- Astro/Starlight: `astro.config.*`, Starlight dependency in `package.json`, `src/content/docs`.

Action:

- Extract source `.md` and `.mdx` first.
- Convert MDX to a readable Markdown view while keeping source paths in `source-map.json`.
- Ask the user before installing dependencies or building the docs site.

About compiling to Markdown:

- Most docs sites compile Markdown or MDX to HTML, not back to Markdown.
- Source `.md` is already Markdown and can be copied.
- Source `.mdx` can be transformed into a Markdown view, but React components, tabs, cards, API playgrounds, imports, and exports may lose semantics.
- Built HTML can be converted back to Markdown with an HTML converter, but it is a lossy fallback.
- Some ecosystems can emit `llms.txt` or Markdown through plugins; use those only when the repo already provides the config or the user approves adding/running tooling.

### Mirrored-Docs Repository

Signals:

- `docs/`, `doc/`, `documentation/`, `guides/`, `tutorials/`.
- `examples/`, `samples/`, cookbook directories.
- Multiple package READMEs.

Action:

- Mirror docs and examples into `references/original/`.
- Copy focused source capsules into `references/source/`.
- Write missing guides under `references/inferred/` only after checking the mirrored docs.

### Sparse-Docs Repository

Signals:

- Root README plus package metadata and tests.
- Useful examples or integration tests but no full docs.

Action:

- Mirror README and examples.
- Use tests, public API files, schemas, and config as evidence.
- Write source-grounded inferred pages for overview, installation, configuration, API, workflows, and limitations.

### Inferred-Docs Repository

Signals:

- No useful docs.
- Source code contains the only reliable behavior description.

Action:

- Copy focused source, config, schema, test, and example evidence.
- Write detailed inferred docs with evidence lists and confidence notes.
- Do not represent inferred pages as upstream docs.
- Add open questions when behavior cannot be established from evidence.

## Build Confirmation Rule

Ask before running any command that installs dependencies, executes project code, or builds docs. This includes `npm install`, `pnpm install`, `yarn`, `bun install`, `pip install -e`, `go generate`, `make docs`, `npm run build`, `pnpm docs:build`, and similar commands.

When asking, include:

- Why the build may improve extraction.
- What command would be run.
- What files or directories it may create.
- The fallback if the user declines.
