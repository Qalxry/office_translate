# skillgen-go-package Output Contract

## Generated Skill Layout

```
docs-<package>/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── INDEX.md
│   ├── manifest.json
│   ├── source-map.json
│   └── pkg-go-dev/
│       ├── overview.md
│       ├── module-info.md
│       ├── readme.md
│       ├── package-info.md
│       ├── package-doc.md
│       ├── package-examples.md
│       ├── package-imports.md
│       ├── symbols.md
│       ├── packages.md
│       ├── versions.md
│       ├── dependencies.md
│       ├── vulns.md
│       └── packages/<extra-package>/
│           ├── package-doc.md
│           ├── package-examples.md
│           └── symbols.md
└── scripts/
    └── update_docs.py
```

Extra package directories are created only when `--extra-package` or `--all-packages` is used.

## Required Version Markers

Generated artifacts must show the resolved concrete version in these places:

- `references/INDEX.md`, near the top.
- Generated `SKILL.md`, under the package metadata.
- Every Markdown file under `references/pkg-go-dev/`, in the header block.
- `references/manifest.json`, as `requested_version`, `resolved_version`, and `latest_version` when available.

When `--version latest` is used, `resolved_version` is the current concrete version returned by `godig overview` or the first non-retracted version from `godig versions`.

## Manifest Fields

`references/manifest.json` should include:

- `generator`: `skillgen-go-package`
- `generated_at`: ISO-8601 UTC timestamp.
- `input_source`: original user input.
- `package_path`: main package/import path.
- `module_path`: Go module path.
- `requested_version`: user-requested version, commonly `latest`.
- `resolved_version`: concrete version used for package docs.
- `latest_version`: latest version reported by pkg.go.dev, when available.
- `repo_url`: repository URL reported by pkg.go.dev, when available.
- `godig`: executable path and version output.
- `commands`: list of `godig` commands, generated paths, exit codes, and stderr summaries.
- `warnings`: non-fatal skipped facets or decoding notes.

## Source Map Entries

Each `source-map.json` entry should identify:

- `generated_path`
- `kind`
- `package_path` or `module_path`
- `source`
- `command`
- `exit_code`
- `ok`

Use `source: "pkg.go.dev via godig"` for all pkg.go.dev-derived pages.

## Failure Policy

- Missing `godig` is fatal. Do not install it automatically; ask the user before installation.
- `overview` is fatal because it resolves module identity and version.
- Individual facets such as examples, vulnerabilities, dependencies, or README are non-fatal. Write a small Markdown page explaining the failed command and record the warning in the manifest.
- README output must be decoded when it arrives as a JSON string from `godig module readme -o raw`.
