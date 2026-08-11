#!/usr/bin/env python3
"""Create a draft documentation skill from a Git repository."""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from analyze_repo import GENERATOR_VERSION, SUMMARY_CANDIDATE_LIMIT, analyze_repository, make_summary  # noqa: E402

TEXT_DOC_EXTENSIONS = {".adoc", ".md", ".markdown", ".mdx", ".rst", ".txt"}
DOC_LINKED_SOURCE_EXTENSIONS = {".go"}
CODE_LANGUAGE_BY_EXT = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "jsx",
    ".kt": "kotlin",
    ".lua": "lua",
    ".mjs": "javascript",
    ".php": "php",
    ".proto": "proto",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".scala": "scala",
    ".sh": "bash",
    ".sql": "sql",
    ".swift": "swift",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".vue": "vue",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}


def slugify(value: str, default: str = "repo", max_length: int = 64) -> str:
    value = value.strip().lower()
    value = re.sub(r"\.git$", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    value = re.sub(r"-{2,}", "-", value)
    if not value:
        value = default
    return value[:max_length].strip("-") or default


def repo_name_from_source(source: str) -> str:
    parsed = urlparse(source)
    if parsed.scheme and parsed.path:
        return Path(parsed.path).name.removesuffix(".git")
    return Path(source).expanduser().resolve().name.removesuffix(".git")


def default_output_dir() -> Path:
    repo_skills = Path.cwd() / ".agents" / "skills"
    if repo_skills.is_dir():
        return repo_skills.resolve()
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser().resolve() / "skills"
    return Path.home() / ".codex" / "skills"


def is_git_url(source: str) -> bool:
    if source.startswith(("http://", "https://", "git@")):
        return True
    return source.endswith(".git") and "://" in source


def clone_or_resolve_repo(source: str, work_dir: Path | None) -> tuple[Path, Path | None]:
    local = Path(source).expanduser()
    if local.exists():
        return local.resolve(), None

    if not is_git_url(source):
        raise FileNotFoundError(f"Repository source is not a local path or Git URL: {source}")

    temp_dir = Path(tempfile.mkdtemp(prefix="skillgen-repo-")) if work_dir is None else work_dir.resolve()
    temp_dir.mkdir(parents=True, exist_ok=True)
    clone_dir = temp_dir / slugify(repo_name_from_source(source))
    if clone_dir.exists():
        shutil.rmtree(clone_dir)
    subprocess.run(["git", "clone", "--depth", "1", source, str(clone_dir)], check=True)
    return clone_dir.resolve(), temp_dir if work_dir is None else None


def safe_reference_path(original_rel: str, suffix: str = ".md") -> Path:
    parts = [slugify(part, default="part", max_length=80) for part in Path(original_rel).parts]
    if not parts:
        return Path(f"item{suffix}")
    last = parts[-1]
    original_suffix = Path(original_rel).suffix.lower()
    if original_suffix:
        stem = slugify(Path(original_rel).stem, default="item", max_length=80)
        parts[-1] = f"{stem}{suffix}"
    elif not last.endswith(suffix):
        parts[-1] = f"{last}{suffix}"
    return Path(*parts)


def read_limited_text(path: Path, max_bytes: int) -> tuple[str, bool]:
    data = path.read_bytes()
    truncated = len(data) > max_bytes
    if truncated:
        data = data[:max_bytes]
    return data.decode("utf-8", errors="replace"), truncated


def markdown_title_from_path(path: str) -> str:
    stem = Path(path).stem
    text = re.sub(r"[-_]+", " ", stem).strip()
    return text.title() if text else "Document"


def strip_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + 5 :].lstrip()
    return text


def mdx_to_markdown_view(text: str) -> str:
    text = strip_frontmatter(text)
    lines: list[str] = []
    in_jsx_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "export ")):
            continue
        if stripped.startswith("<") and stripped.endswith(">") and not stripped.startswith(("<a ", "<img ", "<br", "<code")):
            if stripped.startswith("</"):
                in_jsx_block = False
            elif not stripped.endswith("/>") and not stripped.startswith("<Tabs"):
                in_jsx_block = True
            continue
        if in_jsx_block and stripped.startswith("</"):
            in_jsx_block = False
            continue
        lines.append(line)
    view = "\n".join(lines)
    view = re.sub(r"\n{4,}", "\n\n\n", view)
    return view.strip() + "\n"


def render_original_doc(original_rel: str, text: str, truncated: bool) -> tuple[str, str]:
    suffix = Path(original_rel).suffix.lower()
    title = markdown_title_from_path(original_rel)
    transform = "copied"
    if suffix == ".mdx":
        text = mdx_to_markdown_view(text)
        transform = "markdown-view"
    elif suffix in {".md", ".markdown"}:
        text = strip_frontmatter(text)
    header = [
        f"# {title}",
        "",
        f"> Source file: `{original_rel}`",
    ]
    if suffix == ".mdx":
        header.append("> Converted from MDX source. JSX components may be summarized or omitted.")
    if truncated:
        header.append("> Truncated by generator size limits.")
    header.append("")
    return "\n".join(header) + text.strip() + "\n", transform


MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)")


def iter_relative_markdown_links(text: str) -> list[str]:
    targets: list[str] = []
    for match in MARKDOWN_LINK_RE.finditer(text):
        target = match.group(1).strip().strip("<>")
        target = target.split("#", 1)[0].split("?", 1)[0]
        if not target:
            continue
        if "://" in target or target.startswith(("/", "#", "mailto:")):
            continue
        if "{{" in target or "}}" in target:
            continue
        targets.append(target)
    return targets


def find_doc_linked_source_candidates(
    repo_root: Path,
    doc_entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    candidates: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    missing: list[str] = []

    for entry in doc_entries:
        original_doc = entry.get("original_path")
        if not isinstance(original_doc, str):
            continue
        doc_path = repo_root / original_doc
        if not doc_path.is_file():
            continue
        try:
            text, _ = read_limited_text(doc_path, 300_000)
        except OSError as error:
            warnings.append(f"Could not inspect doc links in {original_doc}: {error}")
            continue
        base = posixpath.dirname(original_doc)
        for target in iter_relative_markdown_links(text):
            if Path(target).suffix.lower() not in DOC_LINKED_SOURCE_EXTENSIONS:
                continue
            resolved = posixpath.normpath(posixpath.join(base, target))
            if resolved.startswith("../") or resolved == "..":
                continue
            if resolved in seen:
                continue
            source = repo_root / resolved
            if not source.is_file():
                missing.append(f"{resolved} referenced by {original_doc}")
                continue
            seen.add(resolved)
            candidates.append(
                {
                    "path": resolved,
                    "reason": f"referenced by mirrored documentation: {original_doc}",
                    "priority": 4,
                    "size": source.stat().st_size,
                }
            )

    if missing:
        preview = "; ".join(missing[:5])
        suffix = "" if len(missing) <= 5 else f"; and {len(missing) - 5} more"
        warnings.append(f"Documentation-linked source files not found: {preview}{suffix}.")

    return sorted(candidates, key=lambda entry: (entry["priority"], entry["path"])), warnings


def render_code_capsule(original_rel: str, text: str, truncated: bool, reason: str) -> str:
    language = CODE_LANGUAGE_BY_EXT.get(Path(original_rel).suffix.lower(), "")
    header = [
        f"# Source Evidence: {original_rel}",
        "",
        f"> Source file: `{original_rel}`",
        f"> Reason: {reason}",
    ]
    if truncated:
        header.append("> Truncated by generator size limits.")
    header.extend(["", f"```{language}", text.rstrip(), "```", ""])
    return "\n".join(header)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_original_docs(
    repo_root: Path,
    skill_dir: Path,
    candidates: list[dict[str, Any]],
    max_files: int,
    max_bytes: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    for candidate in candidates[:max_files]:
        original_rel = candidate["path"]
        source = repo_root / original_rel
        if not source.exists() or source.suffix.lower() not in TEXT_DOC_EXTENSIONS:
            continue
        try:
            text, truncated = read_limited_text(source, max_bytes)
        except OSError as error:
            warnings.append(f"Could not read doc {original_rel}: {error}")
            continue
        relative = Path("references") / "original" / safe_reference_path(original_rel)
        content, transform = render_original_doc(original_rel, text, truncated)
        write_text(skill_dir / relative, content)
        entries.append(
            {
                "generated_path": relative.as_posix(),
                "original_path": original_rel,
                "kind": "original",
                "transform": transform,
                "bytes": len(content.encode("utf-8")),
                "reason": candidate["reason"],
            }
        )
    if len(candidates) > max_files:
        warnings.append(f"Documentation candidates truncated at {max_files} files.")
    return entries, warnings


def copy_source_capsules(
    repo_root: Path,
    skill_dir: Path,
    candidates: list[dict[str, Any]],
    max_files: int,
    max_bytes: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if len(entries) >= max_files:
            break
        original_rel = candidate["path"]
        if original_rel in seen:
            continue
        seen.add(original_rel)
        source = repo_root / original_rel
        if not source.exists():
            continue
        try:
            text, truncated = read_limited_text(source, max_bytes)
        except OSError as error:
            warnings.append(f"Could not read source {original_rel}: {error}")
            continue
        relative = Path("references") / "source" / safe_reference_path(original_rel)
        content = render_code_capsule(original_rel, text, truncated, candidate["reason"])
        write_text(skill_dir / relative, content)
        entries.append(
            {
                "generated_path": relative.as_posix(),
                "original_path": original_rel,
                "kind": "source",
                "transform": "code-capsule",
                "bytes": len(content.encode("utf-8")),
                "reason": candidate["reason"],
            }
        )
    if len(candidates) > max_files:
        warnings.append(f"Source evidence candidates truncated at {max_files} files.")
    return entries, warnings


def inferred_templates(classification: str) -> list[tuple[str, str]]:
    base = [
        ("overview.md", "Overview"),
        ("quick-start.md", "Quick Start"),
        ("api.md", "API And Public Surface"),
        ("architecture.md", "Architecture"),
        ("examples.md", "Examples"),
        ("limitations.md", "Limitations And Open Questions"),
    ]
    if classification in {"source-docs-site", "mirrored-docs"}:
        return base[:1] + base[2:]
    return base


def write_inferred_placeholders(skill_dir: Path, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    classification = analysis["classification"]["kind"]
    for filename, title in inferred_templates(classification):
        relative = Path("references") / "inferred" / filename
        content = "\n".join(
            [
                f"# {title}",
                "",
                "> Status: draft placeholder generated by `skillgen-repo`.",
                "> Replace this page with source-grounded documentation before treating the skill as complete.",
                "",
                "## Evidence To Review",
                "",
                "- `references/original/` for mirrored upstream documentation.",
                "- `references/source/` for copied source, config, schema, test, and example evidence.",
                "- `references/source-map.json` for original repository paths.",
                "",
                "## Notes",
                "",
                "Write this section from repository evidence. Mark uncertainty explicitly.",
                "",
            ]
        )
        write_text(skill_dir / relative, content)
        entries.append(
            {
                "generated_path": relative.as_posix(),
                "original_path": None,
                "kind": "inferred",
                "transform": "placeholder",
                "bytes": len(content.encode("utf-8")),
                "reason": f"{classification} inferred documentation placeholder",
            }
        )
    return entries


def render_index(
    repo_source: str,
    skill_name: str,
    analysis: dict[str, Any],
    source_map: list[dict[str, Any]],
    warnings: list[str],
) -> str:
    classification = analysis["classification"]
    original = [entry for entry in source_map if entry["kind"] == "original"]
    source = [entry for entry in source_map if entry["kind"] == "source"]
    inferred = [entry for entry in source_map if entry["kind"] == "inferred"]
    lines = [
        f"# {skill_name} Repository Docs Index",
        "",
        f"> Source: `{repo_source}`",
        f"> Classification: **{classification['kind']}** ({classification['confidence']})",
        f"> Generated at: {analysis['generated_at']}",
        "",
        "## Start Here",
        "",
        "- Read mirrored upstream docs in `original/` first.",
        "- Use `source/` to verify inferred claims.",
        "- Fill `inferred/` pages before calling this skill complete.",
        "- Check `manifest.json` for warnings and generation limits.",
        "",
        "## Original Docs And Examples",
        "",
    ]
    if original:
        for entry in original[:200]:
            lines.append(f"- [{entry['generated_path'].removeprefix('references/')}]({entry['generated_path'].removeprefix('references/')}) - `{entry['original_path']}`")
    else:
        lines.append("- None mirrored.")
    lines.extend(["", "## Source Evidence", ""])
    if source:
        for entry in source[:200]:
            lines.append(f"- [{entry['generated_path'].removeprefix('references/')}]({entry['generated_path'].removeprefix('references/')}) - `{entry['original_path']}`")
    else:
        lines.append("- None copied.")
    lines.extend(["", "## Inferred Draft Pages", ""])
    for entry in inferred:
        lines.append(f"- [{entry['generated_path'].removeprefix('references/')}]({entry['generated_path'].removeprefix('references/')}) - {entry['reason']}")
    if warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")
    lines.extend(["", "## Classification Signals", ""])
    lines.append(f"- Docs candidates: {classification['doc_count']}")
    lines.append(f"- Example candidates: {classification['example_count']}")
    lines.append(f"- Test candidates: {classification['test_count']}")
    if analysis["doc_site"]["frameworks"]:
        lines.append(f"- Docs-site frameworks: {', '.join(analysis['doc_site']['frameworks'])}")
    if analysis["doc_site"]["build_hints"]:
        lines.append("- Build hints require user confirmation before execution.")
    return "\n".join(lines).rstrip() + "\n"


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_generated_skill_md(skill_name: str, display_name: str, repo_source: str, classification: str) -> str:
    description = (
        f"Offline {display_name} documentation generated from repository docs, examples, and source evidence. "
        f"Use when answering questions, writing code, reviewing integrations, or checking behavior for {display_name}; "
        "start from bundled references and verify inferred claims against source-map evidence."
    )
    return f"""---
name: {skill_name}
description: {yaml_quote(description)}
---

# {display_name}

Use this skill to answer questions from offline repository-derived documentation.

## Navigation

1. Start with `references/INDEX.md`.
2. Prefer `references/original/` for upstream-authored docs and examples.
3. Use `references/inferred/` for source-grounded explanations written after generation.
4. Verify inferred or surprising claims against `references/source/` and `references/source-map.json`.
5. Check `references/manifest.json` for skipped files, limits, source commit, and classification.

## Evidence Policy

- Treat `references/original/` as mirrored upstream documentation.
- Treat `references/source/` as evidence capsules, not full source coverage.
- Treat `references/inferred/` as AI-authored documentation derived from repository evidence.
- When evidence is incomplete, prefer a clear uncertainty note over guessing.

## Repository Source

- Source: `{repo_source}`
- Initial classification: `{classification}`

## Refresh

```bash
python3 scripts/update_docs.py
```
"""


def render_openai_yaml(skill_name: str, display_name: str) -> str:
    short = f"Offline {display_name} repo docs"
    prompt = f"Use ${skill_name} to answer questions from the offline repository documentation."
    return "\n".join(
        [
            "interface:",
            f"  display_name: {yaml_quote(display_name)}",
            f"  short_description: {yaml_quote(short[:64])}",
            f"  default_prompt: {yaml_quote(prompt)}",
            "",
        ]
    )


def render_update_script(repo_source: str, skill_name: str) -> str:
    return f'''#!/usr/bin/env python3
"""Refresh this repository-derived documentation skill."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_SOURCE = {repo_source!r}
SKILL_NAME = {skill_name!r}


def find_generator(this_skill: Path) -> Path:
    env_path = os.environ.get("SKILLGEN_REPO_SCRIPT")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(this_skill.parent / "skillgen-repo" / "scripts" / "create_skill_from_repo.py")
    candidates.append(Path.cwd() / ".agents" / "skills" / "skillgen-repo" / "scripts" / "create_skill_from_repo.py")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit("Could not find skillgen-repo generator. Set SKILLGEN_REPO_SCRIPT.")


def main() -> int:
    this_skill = Path(__file__).resolve().parents[1]
    generator = find_generator(this_skill)
    command = [
        sys.executable,
        str(generator),
        REPO_SOURCE,
        "--skill-dir",
        str(this_skill),
        "--name",
        SKILL_NAME,
        "--overwrite",
    ]
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
'''


def write_manifest(
    skill_dir: Path,
    repo_source: str,
    repo_root: Path,
    analysis: dict[str, Any],
    source_map: list[dict[str, Any]],
    warnings: list[str],
    args: argparse.Namespace,
) -> None:
    manifest = {
        "generator": "skillgen-repo",
        "generator_version": GENERATOR_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_source": repo_source,
        "repo_root": str(repo_root),
        "git": analysis["git"],
        "classification": analysis["classification"],
        "doc_site": analysis["doc_site"],
        "limits": {
            "max_files": args.max_files,
            "max_doc_files": args.max_doc_files,
            "max_doc_bytes": args.max_doc_bytes,
            "max_source_files": args.max_source_files,
            "max_source_bytes": args.max_source_bytes,
        },
        "counts": {
            "source_map_entries": len(source_map),
            "original": sum(1 for entry in source_map if entry["kind"] == "original"),
            "source": sum(1 for entry in source_map if entry["kind"] == "source"),
            "inferred": sum(1 for entry in source_map if entry["kind"] == "inferred"),
        },
        "warnings": warnings,
    }
    write_text(skill_dir / "references" / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


def resolve_skill_dir(args: argparse.Namespace, skill_name: str) -> Path:
    if args.skill_dir:
        return Path(args.skill_dir).expanduser().resolve()
    return (Path(args.output).expanduser().resolve() / skill_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a draft Codex docs skill from a Git repository.")
    parser.add_argument("repo", help="GitHub/Git URL or local repository path.")
    parser.add_argument("--name", help='Generated skill name. Defaults to "docs-<repo-name>".')
    parser.add_argument("--display-name", help="Human-facing display name. Defaults to the repository name.")
    parser.add_argument("--output", default=str(default_output_dir()), help="Parent directory for generated skill.")
    parser.add_argument("--skill-dir", help="Exact skill directory. Overrides --output and --name.")
    parser.add_argument("--work-dir", help="Directory for temporary remote clones.")
    parser.add_argument("--max-files", type=int, default=10000, help="Maximum repository files to scan.")
    parser.add_argument("--max-doc-files", type=int, default=250, help="Maximum docs/example files to mirror.")
    parser.add_argument("--max-doc-bytes", type=int, default=300_000, help="Maximum bytes per mirrored doc.")
    parser.add_argument("--max-source-files", type=int, default=80, help="Maximum source evidence capsules.")
    parser.add_argument("--max-source-bytes", type=int, default=120_000, help="Maximum bytes per source evidence capsule.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing generated skill directory.")
    parser.add_argument("--dry-run", action="store_true", help="Analyze and report without writing a skill.")
    parser.add_argument("--full", action="store_true", help="With --dry-run, print complete analysis instead of compact summary.")
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=SUMMARY_CANDIDATE_LIMIT,
        help="Top candidates per group in compact dry-run output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    temp_to_cleanup: Path | None = None
    try:
        work_dir = Path(args.work_dir).expanduser().resolve() if args.work_dir else None
        repo_root, temp_to_cleanup = clone_or_resolve_repo(args.repo, work_dir)
        analysis = analyze_repository(repo_root, max_files=args.max_files)
    except subprocess.CalledProcessError as error:
        print(f"[ERROR] git command failed: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    repo_slug = slugify(args.name or f"docs-{repo_name_from_source(args.repo)}", default="docs-repo")
    if not repo_slug.startswith("docs-"):
        repo_slug = f"docs-{repo_slug}"
    display_name = args.display_name or repo_name_from_source(args.repo).replace("-", " ").replace("_", " ").title()
    skill_dir = resolve_skill_dir(args, repo_slug)

    if args.dry_run:
        if args.candidate_limit < 0:
            print("[ERROR] --candidate-limit must be zero or greater", file=sys.stderr)
            return 1
        dry_run_analysis = analysis if args.full else make_summary(analysis, args.candidate_limit)
        print(json.dumps({"skill_dir": str(skill_dir), "analysis": dry_run_analysis}, ensure_ascii=False, indent=2))
        return 0

    if skill_dir.exists():
        if not args.overwrite:
            print(f"[ERROR] Target skill already exists: {skill_dir}", file=sys.stderr)
            print("        Pass --overwrite or choose --name/--skill-dir.", file=sys.stderr)
            return 1
        shutil.rmtree(skill_dir)

    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "agents").mkdir(parents=True, exist_ok=True)
    (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_dir / "references").mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    docs_entries, doc_warnings = copy_original_docs(
        repo_root,
        skill_dir,
        analysis["doc_candidates"] + analysis["example_candidates"],
        args.max_doc_files,
        args.max_doc_bytes,
    )
    warnings.extend(doc_warnings)

    doc_source_candidates, doc_source_warnings = find_doc_linked_source_candidates(repo_root, docs_entries)
    warnings.extend(doc_source_warnings)

    source_candidates = doc_source_candidates + analysis["config_candidates"] + analysis["source_candidates"] + analysis["test_candidates"]
    source_entries, source_warnings = copy_source_capsules(
        repo_root,
        skill_dir,
        source_candidates,
        args.max_source_files,
        args.max_source_bytes,
    )
    warnings.extend(source_warnings)

    inferred_entries = write_inferred_placeholders(skill_dir, analysis)
    source_map = docs_entries + source_entries + inferred_entries

    write_text(skill_dir / "references" / "source-map.json", json.dumps(source_map, ensure_ascii=False, indent=2) + "\n")
    write_manifest(skill_dir, args.repo, repo_root, analysis, source_map, warnings, args)
    write_text(skill_dir / "references" / "INDEX.md", render_index(args.repo, repo_slug, analysis, source_map, warnings))
    write_text(
        skill_dir / "SKILL.md",
        render_generated_skill_md(repo_slug, display_name, args.repo, analysis["classification"]["kind"]),
    )
    write_text(skill_dir / "agents" / "openai.yaml", render_openai_yaml(repo_slug, display_name))
    write_text(skill_dir / "scripts" / "update_docs.py", render_update_script(args.repo, repo_slug))
    try:
        (skill_dir / "scripts" / "update_docs.py").chmod(0o755)
    except OSError:
        pass

    print(f"[OK] Generated skill: {skill_dir}")
    print(f"[OK] Mirrored docs/examples: {len(docs_entries)}")
    print(f"[OK] Source evidence capsules: {len(source_entries)}")
    print(f"[OK] Inferred placeholders: {len(inferred_entries)}")
    if warnings:
        print(f"[WARN] {len(warnings)} warnings; see references/manifest.json")

    if temp_to_cleanup is not None:
        shutil.rmtree(temp_to_cleanup, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
