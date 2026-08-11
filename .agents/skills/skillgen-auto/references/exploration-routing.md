# Skillgen Auto Exploration Routing

Use this reference when the automatic report needs human judgment. The goal is to choose the smallest reliable source set that will make a high-quality offline `docs-*` skill.

## Inputs

Classify user input before exploration:

- Bare name: project/library/product name such as `protovalidate`.
- GitHub URL: canonical source repo or possible docs repo.
- Local repo path: run `skillgen-repo` analysis directly after any local inspection.
- Docs URL: hosted documentation page or docs homepage.
- `llms.txt` URL: route directly to `skillgen-llms-txt`, then verify.
- Go import path or pkg.go.dev URL: route to `skillgen-go-package` or use as supplement.

If the user gives multiple hints, prefer their hints over search results. Search results are evidence, not decisions.

For an explicit GitHub URL, prefer shallow Git clone and local file analysis. Do not use GitHub REST API tree/search/pages endpoints unless the user selects `--github-mode api` or the clone path fails and `--github-mode auto` is intentional. This is the reason `skillgen-repo` is usually reliable under GitHub API rate limits: it uses Git transport, not anonymous REST API tree traversal.

## Exploration Order

1. Normalize all direct hints.
2. Probe explicit `llms.txt` URLs and likely sibling endpoints.
3. Probe explicit docs URLs for scrapeability and links.
4. Inspect explicit GitHub repositories with shallow Git clone and local file analysis.
5. Probe explicit Go packages.
6. For a bare name, search GitHub and pkg.go.dev, then probe likely docs domains.
7. Merge evidence and choose a route.
8. Stop for user confirmation if two or more unrelated official-looking projects match the same name.

## Evidence Strength

Use this evidence ranking:

1. User-provided direct URL that resolves successfully.
2. Official repository homepage or README link found from cloned repo files or trusted metadata.
3. Upstream `llms.txt` with Markdown links.
4. Repository tree evidence: docs directories, examples, tests, config, `go.mod`.
5. pkg.go.dev package page for the import path.
6. Search result titles and descriptions.
7. Guessed domains.

Never let a guessed domain override a repository homepage, README link, or user-provided URL.

## Route Decision Matrix

### Use skillgen-llms-txt

Choose this when:

- A valid `llms.txt` endpoint returns Markdown rather than HTML.
- The index has enough links to represent the docs.
- The user wants an offline documentation skill, not source-evidence analysis.

Validation:

- Run the llms generator.
- Inspect `references/index.md` and `references/manifest.json`.
- If many linked pages fail, retry with options such as `--allow-html`, `--recursive`, or `--append-suffix ""` only when the source pattern supports it.

Supplement with `skillgen-repo` when the user needs examples, tests, source capsules, or inferred docs that are not in the upstream llms index.

### Use skillgen-website

Choose this when:

- A docs site is static enough for plain HTTP scraping.
- The page has meaningful text content.
- Same-origin links, sitemap entries, or navigation links expose most docs pages.
- No valid `llms.txt` exists.

Validation:

- Use the report's suggested `PAGES` entries as a starting point.
- Open a few pages and confirm main content is present without JavaScript rendering.
- Follow `skillgen-website` and adjust the scraper selector if needed.

Avoid this as the primary route when:

- The docs are mostly client-rendered and page text is nearly empty.
- The hosted site hides important content behind tabs/components that the HTML scraper cannot see.
- The repo contains clean Markdown/MDX source that can be mirrored more faithfully.

### Use skillgen-repo

Choose this when:

- The repository contains docs, MDX, examples, tests, schemas, or source evidence.
- The docs site is generated from repository source and may need a build.
- The project has sparse docs and needs source-grounded inferred pages.
- You need to explain architecture, configuration, API shape, or behavior from source.

Validation:

- Run `skillgen-repo/scripts/analyze_repo.py` first. For remote repositories this also shallow-clones with Git and avoids GitHub REST API tree limits.
- Classify the repository using `skillgen-repo/references/repo-classification.md`.
- Do not install dependencies or run builds without user approval.
- After generation, revise inferred pages so every claim cites mirrored docs, examples, tests, config, public API, or source evidence.

### Use skillgen-go-package

Choose this when:

- The target is a Go import path, pkg.go.dev URL, or GitHub repo with `go.mod`.
- The user needs exported symbols, examples, versions, dependencies, vulnerabilities, or package API docs.
- The docs site is thin but pkg.go.dev has useful reference pages.

Validation:

- Confirm `godig version`.
- If `godig` is missing, ask before installing it.
- Inspect generated version metadata in `references/INDEX.md` and `references/manifest.json`.

Use as a supplement when the project has broader conceptual docs elsewhere.

## Combined Routes

Use combined routes deliberately:

- `llms.txt` primary plus repo supplement: best for official docs plus source examples/tests.
- Website primary plus Go package supplement: best for multi-language docs with a strong Go API surface.
- Repo primary plus Go package supplement: best for sparse Go repos where source explains behavior and pkg.go.dev explains exported API.
- Repo primary plus website supplement: best when repo has source docs but hosted docs include generated API pages or versioned pages not present in the repo.

Keep generated skills separate when the audiences differ. Example: `docs-protovalidate` for conceptual docs and `docs-protovalidate-go` for Go API reference.

After creating more than one generated skill for the same target, edit every generated `SKILL.md` to include sibling references. The references must be bidirectional:

- In the conceptual or website skill, link to repo/API supplement skills and say when they are better sources.
- In the repo/API supplement skill, link back to the conceptual or primary skill and say what it covers.
- Use concrete names and paths, such as `.agents/skills/docs-protovalidate` and `.agents/skills/docs-protovalidate-go`.
- Keep this in `SKILL.md`, not only in `references/`, because future Codex instances load `SKILL.md` first.

## Ambiguity Rules

Ask the user before generation when:

- A bare name maps to multiple unrelated organizations or products.
- The official source cannot be identified from repo metadata, docs links, package path, or user hints.
- The best route requires dependency installation, running project code, or building docs.
- A private/authenticated source is required.

Do not ask when the uncertainty is only about optional supplements. Generate the strongest primary skill and report the optional second pass.

## Website Page Selection

For a website route:

1. Prefer sitemap URLs when they exist and match the docs path.
2. Otherwise use same-origin links from the docs landing page.
3. Keep docs pages, reference pages, guides, tutorials, API pages, examples, concepts, and configuration pages.
4. Exclude blog posts, marketing pages, pricing, changelog, careers, login, binary downloads, images, and generated search pages.
5. Use stable, descriptive filenames derived from the URL path.
6. Group by first meaningful path segment after dropping prefixes such as `docs`, `en`, `latest`, `stable`, and version labels.

If the crawler finds too many pages, start with top-level guides, reference pages, API pages, and examples, then expand after validation.

## Repository Signals

Strong docs-source signals:

- `docs/`, `documentation/`, `site/`, `website/`, `examples/`, `samples/`.
- `.md` or `.mdx` files beyond the README.
- Docusaurus, VitePress, Nextra, Astro/Starlight, Mintlify, MkDocs, mdBook, Sphinx, Hugo, or VuePress config.
- `gh-pages` branch or GitHub Pages metadata.
- README links to docs, package docs, or examples.

When these signals come from the cloned repository, trust them more than API search results. GitHub API search is useful only for a bare name; it should never override a user-provided repository URL.

Strong source-evidence signals:

- Public API entry points.
- Tests and examples showing intended usage.
- Protocol/schema files such as `.proto`, OpenAPI, GraphQL, SQL migrations, or JSON Schema.
- Package metadata and config.

Treat generated bundles, lockfiles, vendored dependencies, minified files, and build outputs as low-value evidence.

## Weak-Agent Checklist

Follow this checklist exactly when uncertain:

1. Run `explore_target.py` with all hints. For explicit GitHub URLs, keep the default `--github-mode git`.
2. If `Valid llms.txt endpoints` is non-empty, choose `skillgen-llms-txt` unless the user asked for source evidence.
3. Else if the best docs site has many docs links and meaningful text, choose `skillgen-website`.
4. Else if a GitHub repo has docs, examples, tests, or public source evidence, choose `skillgen-repo`.
5. Else if a pkg.go.dev page is valid, choose `skillgen-go-package`.
6. Else ask the user for a GitHub URL, docs URL, package path, or official project homepage.
7. Before running a downstream generator, read that generator's `SKILL.md`.
8. If multiple generated skills are created, add bidirectional sibling links to every generated `SKILL.md`.
9. After generation, inspect indexes/manifests and run the validator.
10. Report the chosen route, generated path, validation result, failures, and optional follow-up routes.
