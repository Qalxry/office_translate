---
name: skillgen-website
description: >-
  Scrape documentation websites (HTML) and package them as local skills with
  structured references/.  Use when you need to turn external docs — ConnectRPC,
  Protobuf, NATS, sqlc, Temporal, Kubernetes, database docs, web framework docs,
  or any technical documentation — into a self-contained skill with indexed
  Markdown references organized by category.
  Do NOT use for: personal blog scraping, general web crawling, downloading
  binary files, or sites that require JavaScript rendering.
filePatterns:
  - "**/scrape.py"
  - "**/scrape-docs.py"
---

# Docs Website to Skill

Scrapes technical documentation websites and packages them as a structured skill under `.agents/skills/<name>/`.

## When You Need This Skill

- You want to turn an external docs site (e.g. `connectrpc.com/docs`, `nats.io/docs`, `sqlc.dev/docs`) into an offline skill
- You need reference material organized by language/concept for AI coding assistance
- You're doing multi-language SDK work and want all docs in one place
- You want a self-contained, re-scrapeable knowledge package

## Output Structure

```
.agents/skills/<name>/
├── SKILL.md                    ← Entry point: trigger info, quick nav, patterns, checklist
├── assets/                     ← Templates, sample files (optional)
├── scripts/
│   └── scrape.py               ← Reusable scraper script
└── references/
    ├── INDEX.md                ← Centralized index of all pages (auto-generated)
    ├── overview.md             ← Top-level introductory pages
    ├── protocol.md             ← Core technical specs
    ├── category_a/             ← Grouped by language/concept
    │   ├── getting-started.md
    │   └── ...
    └── category_b/
        └── ...
```

## Workflow

### Phase 1: Plan the Skill

1. **Identify the docs site** and list the pages you want to scrape
2. **Categorize** pages by language, concept, or section — this determines subdirectory structure
3. **Name the skill** — use `docs-<topic>` hyphen-case format (e.g. `docs-connectrpc`, `docs-nats-jetstream`, `docs-sqlc`)
4. **Create the skill directory** under `.agents/skills/<name>/`
5. Copy `scripts/scrape.py` from this skill into the new skill's `scripts/`

### Phase 2: Configure and Scrape

1. Edit the `PAGES` list in `scripts/scrape.py`:
   - Each entry: `(url, subdirectory, filename.md)`
   - `"."` means top-level (root of references/)
   - Subdirectories group related pages (e.g. `"go"`, `"web"`, `"python"`, `"api"`, `"concepts"`)
2. Run scraper:
   ```bash
   cd .agents/skills/<name>
   python3 scripts/scrape.py
   ```
3. Verify:
   - All pages scraped successfully (check output for errors)
   - `references/INDEX.md` lists every page
   - Content is readable Markdown

### Phase 3: Create SKILL.md Entry

1. Write `SKILL.md` with:
   - **YAML frontmatter**: `name`, `description` (with clear triggering signals), `filePatterns`
   - **Quick Navigation**: Table or bullet links to references/ organized by category
   - **Core Patterns**: 1-3 essential code snippets or patterns from the docs
   - **Verification Checklist**: Key things to check after using the skill

2. **Accuracy requirements for Core Patterns and Verification Checklist**:
   - 每条表述必须从已下载的 `references/` 文档中提取，**不得依赖编写者的既有知识**
   - 涉及具体值（路径、端口、命令、参数）时，必须注明文档中的确切表述，避免过度泛化或写死示例值
   - 如果文档中存在歧义或多种可能，应当在 checklist 中体现（如"通常为 X，具体取决于配置"），而不是武断选择一个"默认值"
   - 建议在编写后快速 grep 验证每条断言是否能在 references/ 中找到对应原文

3. Progressive disclosure principle:
   - SKILL.md provides **navigation + essential patterns** (~100-200 lines)
   - `references/` contains full docs (loaded by Codex only when needed)

### Phase 4: Validate

- `python3 scripts/scrape.py --index` regenerates INDEX.md without re-fetching
- Verify all internal links in SKILL.md point to correct paths
- Test that the skill triggers correctly by checking `description` matches typical queries

## scraper.py Reference

The scraper in `scripts/scrape.py` is the core tool. See [scripts/scrape.py](scripts/scrape.py) for the executable.

### Requirements

```bash
pip3 install beautifulsoup4 html2text
```

### PAGES Configuration

Each page is a tuple of `(url, subdirectory, filename)`:

```python
PAGES = [
    # Top-level pages (subdirectory = ".")
    ("https://example.com/docs/intro/",   ".",     "introduction.md"),

    # Grouped by language/concept (subdirectory = category name)
    ("https://example.com/docs/go/setup/",    "go", "getting-started.md"),
    ("https://example.com/docs/go/errors/",   "go", "errors.md"),
    ("https://example.com/docs/web/overview/","web", "overview.md"),
]
```

**Naming conventions:**
- Filenames: hyphen-case, descriptive (`getting-started.md`, not `page1.md`)
- Subdirectories: single word, lowercase (`go`, `web`, `python`, `api`, `advanced`)
- INDEX.md groups sections alphabetically by subdirectory name

### URL Patterns

Docs sites commonly use these URL structures:

| Site Type | Pattern | Example |
|-----------|---------|---------|
| Starlight/Astro | `docs.example.com/<section>/<page>/` | `connectrpc.com/docs/go/getting-started/` |
| Docusaurus | `docs.example.com/docs/<section>/<page>` | `nats.io/docs/developing-with-nats/` |
| GitBook | `docs.example.com/<section>/<page>` | `docs.sqlc.dev/en/latest/howto/` |
| ReadTheDocs | `docs.example.com/en/latest/<section>/<page>.html` | Various |
| Custom | Varies | Check the site's navigation |

### How It Works

1. Fetches HTML with `urllib.request`
2. Parses with `BeautifulSoup` and finds the main content (`.sl-markdown-content` or `<main>`)
3. Strips anchor-link icons, SVGs, decorative elements
4. Converts to Markdown using `html2text` with sensible defaults
5. Post-processes: removes "Section titled" artifacts, collapses blank lines
6. Writes to `references/<subdir>/<filename>.md`
7. Generates/updates `references/INDEX.md`

### CLI

```bash
python3 scripts/scrape.py              # Fetch all pages
python3 scripts/scrape.py --index      # Rebuild INDEX.md only
```

## Design Principles

- **Progressive disclosure**: SKILL.md is lightweight (~100 lines). Full content lives in `references/`.
- **Deterministic**: The same PAGES list always produces the same output.
- **Concise filenames**: No redundant prefixes (files are already namespaced by subdirectory).
- **Idempotent INDEX**: `--index` rebuilds from the PAGES list, always consistent.
- **Self-contained**: Everything needed to understand and use the skill is in the skill folder itself.

## Anti-Patterns

- ❌ Don't flatten all pages into a single directory — use subdirectories for navigation
- ❌ Don't use JS-rendered sites (SPA/React that requires client-side rendering) — the scraper only parses server HTML
- ❌ Don't put the scraper in the project root — it belongs inside the skill folder
- ❌ Don't include authentication credentials in the scraper — use environment variables if needed
- ❌ Don't modify auto-generated INDEX.md by hand — always regenerate with `--index`
- ❌ Don't create per-directory INDEX.md files — a single centralized INDEX.md is sufficient
