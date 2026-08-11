#!/usr/bin/env python3
"""Analyze a Git repository for documentation-skill generation."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

GENERATOR_VERSION = "0.1.0"
SUMMARY_CANDIDATE_LIMIT = 8
SUMMARY_LANGUAGE_LIMIT = 8
SUMMARY_HINT_LIMIT = 6
FULL_MARKDOWN_CANDIDATE_LIMIT = 40

IGNORE_DIRS = {
    ".agents",
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".old",
    ".vscode",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "node_modules",
    "bower_components",
    "ref_repos",
    "dist",
    "build",
    "out",
    ".next",
    ".nuxt",
    ".docusaurus",
    ".vitepress/cache",
    "coverage",
    "target",
    "vendor",
    "third_party",
    "tmp",
    "temp",
    "worktrees",
}

TEXT_EXTENSIONS = {
    ".adoc",
    ".cjs",
    ".conf",
    ".config",
    ".css",
    ".go",
    ".graphql",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".lua",
    ".mjs",
    ".md",
    ".markdown",
    ".mdx",
    ".proto",
    ".py",
    ".rb",
    ".rs",
    ".rst",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}

BINARY_EXTENSIONS = {
    ".7z",
    ".avif",
    ".bmp",
    ".br",
    ".class",
    ".dmg",
    ".eot",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lockb",
    ".mp3",
    ".mp4",
    ".otf",
    ".pdf",
    ".png",
    ".so",
    ".tar",
    ".tgz",
    ".ttf",
    ".wasm",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".zip",
}

DOC_EXTENSIONS = {".adoc", ".md", ".markdown", ".mdx", ".rst", ".txt"}
CODE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".lua",
    ".mjs",
    ".php",
    ".proto",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".sql",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
}

LANGUAGE_BY_EXT = {
    ".c": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".cs": "C#",
    ".go": "Go",
    ".java": "Java",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".kt": "Kotlin",
    ".lua": "Lua",
    ".mjs": "JavaScript",
    ".php": "PHP",
    ".proto": "Protocol Buffers",
    ".py": "Python",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".scala": "Scala",
    ".sh": "Shell",
    ".sql": "SQL",
    ".swift": "Swift",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".vue": "Vue",
}

DOC_DIR_NAMES = {
    "doc",
    "docs",
    "documentation",
    "guide",
    "guides",
    "handbook",
    "manual",
    "site",
    "website",
    "wiki",
}

EXAMPLE_DIR_NAMES = {
    "cookbook",
    "demo",
    "demos",
    "example",
    "examples",
    "sample",
    "samples",
    "tutorial",
    "tutorials",
}

TEST_DIR_NAMES = {
    "__tests__",
    "spec",
    "specs",
    "test",
    "tests",
}

ROOT_DOC_NAMES = {
    "changelog",
    "code_of_conduct",
    "contributing",
    "faq",
    "getting_started",
    "getting-started",
    "index",
    "install",
    "installation",
    "license",
    "readme",
    "release_notes",
    "releases",
    "security",
}

CONFIG_NAMES = {
    "Cargo.toml",
    "deno.json",
    "deno.jsonc",
    "go.mod",
    "package.json",
    "pnpm-workspace.yaml",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "tsconfig.json",
}

SCHEMA_EXTENSIONS = {".graphql", ".graphqls", ".proto", ".sql"}
CANDIDATE_GROUPS = [
    ("docs", "Documentation", "doc_candidates"),
    ("examples", "Examples", "example_candidates"),
    ("tests", "Tests", "test_candidates"),
    ("config", "Config", "config_candidates"),
    ("source", "Source Evidence", "source_candidates"),
]


def run_git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


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
    return Path(source).expanduser().name.removesuffix(".git")


def is_git_url(source: str) -> bool:
    return source.startswith(("http://", "https://", "git@")) or (source.endswith(".git") and "://" in source)


def clone_or_resolve_repo(source: str) -> tuple[Path, Path | None]:
    local = Path(source).expanduser()
    if local.exists():
        return local.resolve(), None
    if not is_git_url(source):
        raise FileNotFoundError(f"Repository source is not a local path or Git URL: {source}")
    temp_dir = Path(tempfile.mkdtemp(prefix="skillgen-repo-analyze-"))
    clone_dir = temp_dir / slugify(repo_name_from_source(source))
    subprocess.run(["git", "clone", "--depth", "1", source, str(clone_dir)], check=True)
    return clone_dir.resolve(), temp_dir


def git_tracked_paths(root: Path) -> list[str] | None:
    output = run_git(root, "ls-files", "-z")
    if output is None:
        return None
    return [path for path in output.split("\0") if path]


def is_probably_text(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in BINARY_EXTENSIONS:
        return False
    if suffix in TEXT_EXTENSIONS or path.name in CONFIG_NAMES or path.name in {"Dockerfile", "Makefile"}:
        return True
    try:
        with path.open("rb") as handle:
            sample = handle.read(4096)
    except OSError:
        return False
    return b"\0" not in sample


def should_ignore_path(rel: str) -> bool:
    parts = Path(rel).parts
    for index, part in enumerate(parts):
        lowered = part.lower()
        if lowered in IGNORE_DIRS:
            return True
        prefix = "/".join(piece.lower() for piece in parts[: index + 1])
        if prefix in IGNORE_DIRS:
            return True
    return False


def iter_repo_files(root: Path, max_files: int) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    tracked = git_tracked_paths(root)
    if tracked is not None:
        for rel in tracked:
            if should_ignore_path(rel):
                continue
            path = root / rel
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            suffix = path.suffix.lower()
            files.append(
                {
                    "path": rel,
                    "size": stat.st_size,
                    "suffix": suffix,
                    "is_text": is_probably_text(path),
                }
            )
            if len(files) >= max_files:
                return files
        return files

    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if not should_ignore_path(Path(current, name).relative_to(root).as_posix())
        ]
        for filename in filenames:
            path = Path(current) / filename
            try:
                rel = path.relative_to(root).as_posix()
                stat = path.stat()
            except OSError:
                continue
            if should_ignore_path(rel):
                continue
            suffix = path.suffix.lower()
            files.append(
                {
                    "path": rel,
                    "size": stat.st_size,
                    "suffix": suffix,
                    "is_text": is_probably_text(path),
                }
            )
            if len(files) >= max_files:
                return files
    return files


def path_parts(path: str) -> tuple[str, ...]:
    return tuple(part.lower() for part in Path(path).parts)


def stem_name(path: str) -> str:
    return Path(path).stem.lower()


def has_part(path: str, names: set[str]) -> bool:
    return any(part in names for part in path_parts(path))


def is_root_file(path: str) -> bool:
    return len(Path(path).parts) == 1


def reasoned(path: str, reason: str, priority: int, size: int) -> dict[str, Any]:
    return {"path": path, "reason": reason, "priority": priority, "size": size}


def find_doc_candidates(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in files:
        path = item["path"]
        suffix = item["suffix"]
        if not item["is_text"]:
            continue
        base = Path(path).name.lower()
        stem = stem_name(path)
        parts = path_parts(path)
        candidate: dict[str, Any] | None = None

        if base in {"llms.txt", "llms-full.txt"}:
            candidate = reasoned(path, "llms index or full bundle", 1, item["size"])
        elif is_root_file(path) and (stem in ROOT_DOC_NAMES or base in {"readme.md", "readme.mdx"}):
            candidate = reasoned(path, "root documentation file", 5, item["size"])
        elif suffix in DOC_EXTENSIONS and has_part(path, DOC_DIR_NAMES):
            candidate = reasoned(path, "documentation directory", 10, item["size"])
        elif suffix in DOC_EXTENSIONS and has_part(path, EXAMPLE_DIR_NAMES):
            candidate = reasoned(path, "example or tutorial directory", 20, item["size"])
        elif suffix in DOC_EXTENSIONS and parts[-1] in {"readme.md", "readme.mdx"}:
            candidate = reasoned(path, "package readme", 30, item["size"])
        elif suffix in {".md", ".mdx"} and ("pages" in parts or "content" in parts):
            candidate = reasoned(path, "docs-site content file", 35, item["size"])

        if candidate and path not in seen:
            candidates.append(candidate)
            seen.add(path)

    return sorted(candidates, key=lambda entry: (entry["priority"], entry["path"]))


def find_example_candidates(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in files:
        path = item["path"]
        if item["is_text"] and has_part(path, EXAMPLE_DIR_NAMES):
            candidates.append(reasoned(path, "example evidence", 20, item["size"]))
    return sorted(candidates, key=lambda entry: (entry["priority"], entry["path"]))


def find_test_candidates(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in files:
        path = item["path"]
        if (
            item["is_text"]
            and item["suffix"] not in DOC_EXTENSIONS
            and (has_part(path, TEST_DIR_NAMES) or re.search(r"(\.|_|-)(test|spec)\.", path))
        ):
            candidates.append(reasoned(path, "test evidence", 30, item["size"]))
    return sorted(candidates, key=lambda entry: (entry["priority"], entry["path"]))


def find_config_candidates(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in files:
        path = item["path"]
        name = Path(path).name
        if item["is_text"] and (name in CONFIG_NAMES or name in {"Dockerfile", "Makefile"}):
            candidates.append(reasoned(path, "project configuration", 10, item["size"]))
    return sorted(candidates, key=lambda entry: (entry["priority"], entry["path"]))


def find_source_candidates(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in files:
        path = item["path"]
        suffix = item["suffix"]
        parts = path_parts(path)
        name = Path(path).name
        stem = Path(path).stem.lower()
        if not item["is_text"]:
            continue
        priority: int | None = None
        reason = "source evidence"
        if name in CONFIG_NAMES:
            priority = 5
            reason = "project metadata"
        elif suffix in SCHEMA_EXTENSIONS:
            priority = 8
            reason = "schema or protocol definition"
        elif suffix in CODE_EXTENSIONS and stem in {"index", "main", "mod", "lib", "__init__", "cli", "server"}:
            priority = 15
            reason = "entry point candidate"
        elif suffix in CODE_EXTENSIONS and any(part in {"src", "lib", "pkg", "cmd", "packages", "crates"} for part in parts):
            priority = 25
            reason = "implementation candidate"
        elif suffix in CODE_EXTENSIONS and has_part(path, EXAMPLE_DIR_NAMES):
            priority = 30
            reason = "example code"
        elif suffix in CODE_EXTENSIONS and has_part(path, TEST_DIR_NAMES):
            priority = 35
            reason = "test code"

        if priority is not None:
            candidates.append(reasoned(path, reason, priority, item["size"]))

    return sorted(candidates, key=lambda entry: (entry["priority"], entry["path"]))


def detect_languages(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    bytes_by_language: Counter[str] = Counter()
    for item in files:
        language = LANGUAGE_BY_EXT.get(item["suffix"])
        if not language:
            continue
        counts[language] += 1
        bytes_by_language[language] += item["size"]
    return [
        {"language": language, "files": counts[language], "bytes": bytes_by_language[language]}
        for language, _ in counts.most_common()
    ]


def detect_package_managers(files: list[dict[str, Any]]) -> list[str]:
    names = {Path(item["path"]).name for item in files}
    managers: list[str] = []
    markers = [
        ("pnpm", "pnpm-lock.yaml"),
        ("yarn", "yarn.lock"),
        ("npm", "package-lock.json"),
        ("bun", "bun.lockb"),
        ("pip/uv", "pyproject.toml"),
        ("poetry", "poetry.lock"),
        ("go", "go.mod"),
        ("cargo", "Cargo.lock"),
        ("maven", "pom.xml"),
        ("gradle", "build.gradle"),
    ]
    for manager, marker in markers:
        if marker in names:
            managers.append(manager)
    if "package.json" in names and not any(manager in managers for manager in {"pnpm", "yarn", "npm", "bun"}):
        managers.append("node")
    return managers


def read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def detect_doc_site(root: Path, files: list[dict[str, Any]]) -> dict[str, Any]:
    paths = {item["path"] for item in files}
    names = {Path(path).name for path in paths}
    frameworks: list[str] = []
    evidence: list[str] = []

    def add(framework: str, path: str) -> None:
        if framework not in frameworks:
            frameworks.append(framework)
        evidence.append(path)

    for path in sorted(paths):
        name = Path(path).name
        if name.startswith("docusaurus.config."):
            add("Docusaurus", path)
        if path.startswith("docs/.vitepress/") or path.startswith(".vitepress/"):
            add("VitePress", path)
        if name == "mint.json" or name == "docs.json":
            add("Mintlify", path)
        if name.startswith("astro.config."):
            add("Astro/Starlight", path)
        if name.startswith("theme.config.") or path.startswith("pages/") and path.endswith(".mdx"):
            add("Nextra", path)

    package_json = read_json_file(root / "package.json")
    if package_json:
        deps = {}
        for key in ("dependencies", "devDependencies"):
            value = package_json.get(key)
            if isinstance(value, dict):
                deps.update(value)
        dependency_markers = [
            ("Docusaurus", "@docusaurus/core"),
            ("VitePress", "vitepress"),
            ("Nextra", "nextra"),
            ("Astro/Starlight", "@astrojs/starlight"),
            ("Mintlify", "mintlify"),
        ]
        for framework, dependency in dependency_markers:
            if dependency in deps:
                add(framework, f"package.json:{dependency}")

    build_hints: list[str] = []
    if package_json and isinstance(package_json.get("scripts"), dict):
        for name, command in sorted(package_json["scripts"].items()):
            if any(word in name.lower() for word in ("doc", "site", "build")) or any(
                word in str(command).lower() for word in ("docusaurus", "vitepress", "mintlify", "starlight", "nextra")
            ):
                build_hints.append(f"npm script {name}: {command}")

    mdx_count = sum(1 for path in paths if path.endswith(".mdx"))
    md_count = sum(1 for path in paths if path.endswith(".md"))
    requires_confirmation = bool(frameworks or build_hints)

    return {
        "frameworks": frameworks,
        "evidence": sorted(set(evidence)),
        "build_hints": build_hints,
        "markdown_files": md_count,
        "mdx_files": mdx_count,
        "requires_build_confirmation": requires_confirmation,
    }


def classify_repo(analysis: dict[str, Any]) -> dict[str, Any]:
    docs = analysis["doc_candidates"]
    doc_site = analysis["doc_site"]
    examples = analysis["example_candidates"]
    tests = analysis["test_candidates"]
    has_llms = any(Path(item["path"]).name in {"llms.txt", "llms-full.txt"} for item in docs)
    doc_count = len(docs)
    example_count = len(examples)
    test_count = len(tests)

    if has_llms:
        kind = "llms-published"
        confidence = "high"
    elif doc_site["frameworks"] or doc_site["mdx_files"] >= 5:
        kind = "source-docs-site"
        confidence = "high" if doc_count >= 5 else "medium"
    elif doc_count >= 5 or example_count >= 5:
        kind = "mirrored-docs"
        confidence = "high" if doc_count >= 10 else "medium"
    elif doc_count >= 1 or example_count >= 1 or test_count >= 5:
        kind = "sparse-docs"
        confidence = "medium"
    else:
        kind = "inferred-docs"
        confidence = "medium"

    return {
        "kind": kind,
        "confidence": confidence,
        "has_llms": has_llms,
        "doc_count": doc_count,
        "example_count": example_count,
        "test_count": test_count,
    }


def candidate_counts(analysis: dict[str, Any]) -> dict[str, int]:
    return {label: len(analysis[key]) for label, _, key in CANDIDATE_GROUPS}


def compact_candidates(analysis: dict[str, Any], limit: int) -> dict[str, list[dict[str, Any]]]:
    return {label: analysis[key][:limit] for label, _, key in CANDIDATE_GROUPS}


def make_summary(analysis: dict[str, Any], candidate_limit: int = SUMMARY_CANDIDATE_LIMIT) -> dict[str, Any]:
    doc_site = analysis["doc_site"]
    summary: dict[str, Any] = {
        "generator": analysis["generator"],
        "generator_version": analysis["generator_version"],
        "generated_at": analysis["generated_at"],
        "repo_root": analysis["repo_root"],
        "git": analysis["git"],
        "files_scanned": analysis["files_scanned"],
        "scan_truncated": analysis["scan_truncated"],
        "classification": analysis["classification"],
        "languages": analysis["languages"][:SUMMARY_LANGUAGE_LIMIT],
        "package_managers": analysis["package_managers"],
        "doc_site": {
            "frameworks": doc_site["frameworks"],
            "evidence": doc_site["evidence"][:candidate_limit],
            "build_hints": doc_site["build_hints"][:SUMMARY_HINT_LIMIT],
            "markdown_files": doc_site["markdown_files"],
            "mdx_files": doc_site["mdx_files"],
            "requires_build_confirmation": doc_site["requires_build_confirmation"],
        },
        "candidate_counts": candidate_counts(analysis),
        "top_candidates": compact_candidates(analysis, candidate_limit),
    }
    hidden_counts: dict[str, int] = {}
    for label, _, key in CANDIDATE_GROUPS:
        hidden = len(analysis[key]) - len(summary["top_candidates"][label])
        if hidden > 0:
            hidden_counts[label] = hidden
    if len(doc_site["evidence"]) > len(summary["doc_site"]["evidence"]):
        hidden_counts["doc_site_evidence"] = len(doc_site["evidence"]) - len(summary["doc_site"]["evidence"])
    if len(doc_site["build_hints"]) > len(summary["doc_site"]["build_hints"]):
        hidden_counts["build_hints"] = len(doc_site["build_hints"]) - len(summary["doc_site"]["build_hints"])
    summary["truncated_counts"] = hidden_counts
    summary["full_output_hint"] = "Pass --full for complete Markdown or --json --full for complete JSON."
    return summary


def analyze_repository(root: Path, max_files: int = 10000) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Repository path does not exist or is not a directory: {root}")

    files = iter_repo_files(root, max_files)
    analysis: dict[str, Any] = {
        "generator": "skillgen-repo",
        "generator_version": GENERATOR_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "git": {
            "remote": run_git(root, "remote", "get-url", "origin"),
            "commit": run_git(root, "rev-parse", "HEAD"),
            "branch": run_git(root, "branch", "--show-current"),
        },
        "files_scanned": len(files),
        "scan_truncated": len(files) >= max_files,
        "languages": detect_languages(files),
        "package_managers": detect_package_managers(files),
        "doc_site": detect_doc_site(root, files),
        "doc_candidates": find_doc_candidates(files),
        "example_candidates": find_example_candidates(files),
        "test_candidates": find_test_candidates(files),
        "config_candidates": find_config_candidates(files),
        "source_candidates": find_source_candidates(files),
    }
    analysis["classification"] = classify_repo(analysis)
    return analysis


def render_candidate_lines(entries: list[dict[str, Any]]) -> list[str]:
    return [f"- `{entry['path']}` - {entry['reason']} ({entry['size']} bytes)" for entry in entries]


def render_summary_markdown(analysis: dict[str, Any], candidate_limit: int = SUMMARY_CANDIDATE_LIMIT) -> str:
    summary = make_summary(analysis, candidate_limit)
    classification = summary["classification"]
    lines = [
        "# Repository Analysis Summary",
        "",
        f"- Repository: `{summary['repo_root']}`",
        f"- Git remote: `{summary['git'].get('remote') or 'unknown'}`",
        f"- Commit: `{summary['git'].get('commit') or 'unknown'}`",
        f"- Files scanned: {summary['files_scanned']}{' (truncated)' if summary['scan_truncated'] else ''}",
        f"- Classification: **{classification['kind']}** ({classification['confidence']})",
        "",
        "## Signals",
        "",
    ]

    if summary["package_managers"]:
        lines.append(f"- Package managers: {', '.join(summary['package_managers'])}")
    else:
        lines.append("- Package managers: none detected")

    if summary["languages"]:
        language_bits = [
            f"{language['language']} ({language['files']} files)"
            for language in summary["languages"]
        ]
        lines.append(f"- Languages: {', '.join(language_bits)}")
    else:
        lines.append("- Languages: none detected")

    doc_site = summary["doc_site"]
    lines.append(f"- Markdown / MDX files: {doc_site['markdown_files']} / {doc_site['mdx_files']}")
    if doc_site["frameworks"]:
        lines.append(f"- Docs-site frameworks: {', '.join(doc_site['frameworks'])}")
    if doc_site["requires_build_confirmation"]:
        lines.append("- Build/install confirmation required before running docs-site commands.")
    if classification["has_llms"]:
        lines.append("- `llms.txt` or `llms-full.txt` detected; prefer `skillgen-llms-txt` unless source evidence is needed.")

    lines.extend(["", "## Candidate Counts", ""])
    count_bits = [f"{title}: {summary['candidate_counts'][label]}" for label, title, _ in CANDIDATE_GROUPS]
    lines.append("- " + "; ".join(count_bits))

    if doc_site["build_hints"]:
        lines.extend(["", "## Build Hints", ""])
        lines.extend(f"- `{hint}`" for hint in doc_site["build_hints"])
        if "build_hints" in summary["truncated_counts"]:
            lines.append(f"- ... {summary['truncated_counts']['build_hints']} more omitted")

    top_candidate_lines: list[str] = []
    for label, title, _ in CANDIDATE_GROUPS:
        entries = summary["top_candidates"][label]
        if not entries:
            continue
        top_candidate_lines.append(f"### {title}")
        top_candidate_lines.extend(render_candidate_lines(entries))
        if label in summary["truncated_counts"]:
            top_candidate_lines.append(f"- ... {summary['truncated_counts'][label]} more omitted")
        top_candidate_lines.append("")
    if top_candidate_lines:
        if top_candidate_lines[-1] == "":
            top_candidate_lines.pop()
        lines.extend(["", "## Top Candidates", "", *top_candidate_lines])

    lines.extend(
        [
            "",
            "## Next Steps",
            "",
        ]
    )
    kind = classification["kind"]
    if kind == "llms-published":
        lines.append("- Route to `skillgen-llms-txt` by default, or continue with repo-derived evidence when requested.")
    elif kind == "source-docs-site":
        lines.append("- Mirror `.md`/`.mdx` docs and ask before installing dependencies or running a docs build.")
    elif kind == "mirrored-docs":
        lines.append("- Generate from mirrored docs and examples, then add focused source capsules for missing details.")
    elif kind == "sparse-docs":
        lines.append("- Copy the small doc/example set, then write clearly marked source-grounded inferred pages.")
    else:
        lines.append("- Treat this as source-grounded inferred documentation; cite source/test/config evidence carefully.")
    lines.append("- Use `--full` for complete Markdown or `--json --full` for complete JSON when deeper inspection is needed.")

    return "\n".join(lines).rstrip() + "\n"


def render_markdown(analysis: dict[str, Any]) -> str:
    lines = [
        "# Repository Analysis",
        "",
        f"- Repository: `{analysis['repo_root']}`",
        f"- Git remote: `{analysis['git'].get('remote') or 'unknown'}`",
        f"- Commit: `{analysis['git'].get('commit') or 'unknown'}`",
        f"- Files scanned: {analysis['files_scanned']}",
        f"- Classification: **{analysis['classification']['kind']}** ({analysis['classification']['confidence']})",
        "",
        "## Languages",
        "",
    ]
    for language in analysis["languages"][:12]:
        lines.append(f"- {language['language']}: {language['files']} files, {language['bytes']} bytes")
    if not analysis["languages"]:
        lines.append("- None detected")

    lines.extend(["", "## Documentation Signals", ""])
    doc_site = analysis["doc_site"]
    if doc_site["frameworks"]:
        lines.append(f"- Docs site frameworks: {', '.join(doc_site['frameworks'])}")
    lines.append(f"- Markdown files: {doc_site['markdown_files']}")
    lines.append(f"- MDX files: {doc_site['mdx_files']}")
    if doc_site["build_hints"]:
        lines.append("- Build hints:")
        for hint in doc_site["build_hints"][:12]:
            lines.append(f"  - `{hint}`")

    for title, key in [
        ("Documentation Candidates", "doc_candidates"),
        ("Examples", "example_candidates"),
        ("Tests", "test_candidates"),
        ("Source Evidence Candidates", "source_candidates"),
    ]:
        lines.extend(["", f"## {title}", ""])
        entries = analysis[key][:FULL_MARKDOWN_CANDIDATE_LIMIT]
        if not entries:
            lines.append("- None detected")
            continue
        lines.extend(render_candidate_lines(entries))
        omitted = len(analysis[key]) - len(entries)
        if omitted > 0:
            lines.append(f"- ... {omitted} more omitted; use `--json --full` for the complete list")

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a Git repository for docs-skill generation.")
    parser.add_argument("repo", help="GitHub/Git URL or local repository path.")
    parser.add_argument("--max-files", type=int, default=10000, help="Maximum files to scan.")
    parser.add_argument("--json", action="store_true", help="Print compact JSON summary instead of Markdown.")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown summary. This is the default.")
    parser.add_argument("--full", action="store_true", help="Print the complete analysis instead of the compact LLM summary.")
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=SUMMARY_CANDIDATE_LIMIT,
        help="Top candidates per group in compact output.",
    )
    parser.add_argument("--output", help="Write output to this file instead of stdout.")
    parser.add_argument(
        "--full-output",
        help="Also write the complete analysis JSON to this file while keeping stdout compact.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    temp_to_cleanup: Path | None = None
    try:
        repo_root, temp_to_cleanup = clone_or_resolve_repo(args.repo)
        analysis = analyze_repository(repo_root, max_files=args.max_files)
    except subprocess.CalledProcessError as error:
        print(f"[ERROR] git command failed: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    if args.candidate_limit < 0:
        print("[ERROR] --candidate-limit must be zero or greater", file=sys.stderr)
        return 1

    if args.full_output:
        Path(args.full_output).write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json and not args.markdown:
        payload = analysis if args.full else make_summary(analysis, args.candidate_limit)
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    else:
        content = render_markdown(analysis) if args.full else render_summary_markdown(analysis, args.candidate_limit)

    if args.output:
        Path(args.output).write_text(content, encoding="utf-8")
    else:
        sys.stdout.write(content)
    if temp_to_cleanup is not None:
        shutil.rmtree(temp_to_cleanup, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
