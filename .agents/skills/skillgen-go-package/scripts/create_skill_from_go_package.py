#!/usr/bin/env python3
"""Create an offline documentation skill from pkg.go.dev Go package data."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

GENERATOR_VERSION = "0.1.0"
SOURCE_LABEL = "pkg.go.dev via godig"


@dataclass
class CommandRecord:
    name: str
    command: list[str]
    generated_path: str | None
    exit_code: int
    ok: bool
    stderr: str


@dataclass
class PageRecord:
    generated_path: str
    kind: str
    package_path: str | None
    module_path: str | None
    command: list[str]
    exit_code: int
    ok: bool


def slugify(value: str, default: str = "go-package", max_length: int = 80) -> str:
    value = value.strip().lower()
    value = re.sub(r"\.git$", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    value = re.sub(r"-{2,}", "-", value)
    if not value:
        value = default
    return value[:max_length].strip("-") or default


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def default_output_dir() -> Path:
    cwd_agents = Path.cwd() / ".agents" / "skills"
    if cwd_agents.is_dir():
        return cwd_agents.resolve()
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return (Path(codex_home).expanduser() / "skills").resolve()
    return (Path.home() / ".codex" / "skills").resolve()


def split_source_version(source: str) -> tuple[str, str | None]:
    if source.startswith(("http://", "https://", "file://")):
        return source, None
    slash = source.rfind("/")
    at = source.rfind("@")
    if at > slash and at != -1:
        version = source[at + 1 :]
        if version:
            return source[:at], version
    return source, None


def read_module_from_go_mod(repo: Path) -> str | None:
    go_mod = repo / "go.mod"
    if not go_mod.is_file():
        return None
    for line in go_mod.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("module "):
            return stripped.split(None, 1)[1].strip()
    return None


def github_url_to_import_path(parsed: Any) -> str:
    parts = [part for part in unquote(parsed.path).split("/") if part]
    if len(parts) < 2:
        raise ValueError(f"GitHub URL does not include owner/repo: {parsed.geturl()}")
    return f"github.com/{parts[0]}/{parts[1].removesuffix('.git')}"


def pkg_go_dev_url_to_import_path(parsed: Any) -> str:
    path = unquote(parsed.path).strip("/")
    if not path:
        raise ValueError(f"pkg.go.dev URL does not include an import path: {parsed.geturl()}")
    return path.removesuffix(".git")


def normalize_source(source: str) -> tuple[str, str | None, str]:
    stripped_source, version = split_source_version(source.strip())
    local = Path(stripped_source).expanduser()
    if local.exists():
        module = read_module_from_go_mod(local.resolve())
        if not module:
            raise ValueError(f"Local source has no readable go.mod module line: {stripped_source}")
        return module, version, "local-go-repo"

    parsed = urlparse(stripped_source)
    if parsed.scheme in {"http", "https"}:
        host = parsed.netloc.lower()
        if host == "pkg.go.dev":
            import_path, path_version = split_source_version(pkg_go_dev_url_to_import_path(parsed))
            return import_path, version or path_version, "pkg-go-dev-url"
        if host == "github.com":
            return github_url_to_import_path(parsed), version, "github-url"
        if parsed.path:
            path, path_version = split_source_version(unquote(parsed.path).strip("/").removesuffix(".git"))
            if path:
                return f"{host}/{path}", version or path_version, "go-import-url"

    if stripped_source.startswith("git@github.com:"):
        path = stripped_source.removeprefix("git@github.com:").removesuffix(".git")
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2:
            return f"github.com/{parts[0]}/{parts[1]}", version, "github-ssh-url"

    return stripped_source.removesuffix(".git"), version, "import-path"


def find_godig(explicit: str | None) -> str:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    env_path = os.environ.get("GODIG")
    if env_path:
        candidates.append(env_path)
    path_bin = shutil.which("godig")
    if path_bin:
        candidates.append(path_bin)

    for candidate in candidates:
        resolved = shutil.which(candidate) if not Path(candidate).exists() else candidate
        if resolved:
            return str(Path(resolved).expanduser())

    raise SystemExit(
        "godig is required but was not found. Install only after user confirmation:\n"
        "  go install github.com/samber/godig/cmd/godig@latest\n"
        "Or pass --godig /path/to/godig."
    )


def run_command(command: list[str], required: bool) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if required and result.returncode != 0:
        raise SystemExit(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def stderr_summary(stderr: str, max_length: int = 1000) -> str:
    text = stderr.strip()
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + " ..."


def godig_command(godig: str, parts: list[str], output: str, timeout: str | None) -> list[str]:
    command = [godig, *parts, "-o", output]
    if timeout:
        command.extend(["--timeout", timeout])
    return command


def read_json_output(result: subprocess.CompletedProcess[str], command: list[str]) -> Any:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SystemExit(f"Could not parse JSON from {' '.join(command)}: {error}") from error


def first_non_retracted_version(versions: Any) -> str | None:
    if not isinstance(versions, list):
        return None
    for item in versions:
        if not isinstance(item, dict):
            continue
        if item.get("retracted") is True:
            continue
        version = item.get("version")
        if isinstance(version, str) and version:
            return version
    return None


def clean_readme(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    try:
        decoded = json.loads(text)
        if isinstance(decoded, str):
            text = decoded
    except json.JSONDecodeError:
        pass
    text = text.replace("\r\n", "\n")
    return text.strip() + "\n"


def render_header(
    title: str,
    package_path: str,
    module_path: str,
    resolved_version: str,
    command: list[str] | None,
    generated_at: str,
) -> str:
    lines = [
        f"# {title}",
        "",
        f"> Package: `{package_path}`",
        f"> Module: `{module_path}`",
        f"> Version: `{resolved_version}`",
        f"> Source: {SOURCE_LABEL}",
        f"> Generated: `{generated_at}`",
    ]
    if command:
        lines.append(f"> Command: `{' '.join(command)}`")
    lines.append("")
    return "\n".join(lines) + "\n"


def render_failed_page(
    title: str,
    package_path: str,
    module_path: str,
    resolved_version: str,
    command: list[str],
    generated_at: str,
    result: subprocess.CompletedProcess[str],
) -> str:
    body = [
        render_header(title, package_path, module_path, resolved_version, command, generated_at),
        "This facet could not be fetched. The generated skill remains usable, but this page should not be treated as evidence.",
        "",
        f"- Exit code: `{result.returncode}`",
    ]
    if result.stderr.strip():
        body.extend(["", "## stderr", "", "```text", result.stderr.strip(), "```"])
    if result.stdout.strip():
        body.extend(["", "## stdout", "", "```text", result.stdout.strip(), "```"])
    body.append("")
    return "\n".join(body)


def render_page(
    title: str,
    content: str,
    package_path: str,
    module_path: str,
    resolved_version: str,
    command: list[str],
    generated_at: str,
) -> str:
    body = content.strip()
    if not body:
        body = "_No content returned._"
    return render_header(title, package_path, module_path, resolved_version, command, generated_at) + body + "\n"


def record_command(
    commands: list[CommandRecord],
    name: str,
    command: list[str],
    generated_path: str | None,
    result: subprocess.CompletedProcess[str],
) -> None:
    commands.append(
        CommandRecord(
            name=name,
            command=command,
            generated_path=generated_path,
            exit_code=result.returncode,
            ok=result.returncode == 0,
            stderr=stderr_summary(result.stderr),
        )
    )


def write_godig_page(
    *,
    godig: str,
    command_parts: list[str],
    output: str,
    timeout: str | None,
    title: str,
    kind: str,
    generated_rel: Path,
    skill_dir: Path,
    package_path: str,
    module_path: str,
    resolved_version: str,
    generated_at: str,
    commands: list[CommandRecord],
    pages: list[PageRecord],
    warnings: list[str],
    transform_readme: bool = False,
    required: bool = False,
) -> None:
    command = godig_command(godig, command_parts, output, timeout)
    result = run_command(command, required=required)
    generated_path = generated_rel.as_posix()
    record_command(commands, kind, command, generated_path, result)
    if result.returncode == 0:
        content = clean_readme(result.stdout) if transform_readme else result.stdout
        page = render_page(title, content, package_path, module_path, resolved_version, command, generated_at)
    else:
        warnings.append(f"{kind} failed with exit code {result.returncode}: {' '.join(command)}")
        page = render_failed_page(title, package_path, module_path, resolved_version, command, generated_at, result)
    write_text(skill_dir / generated_rel, page)
    pages.append(
        PageRecord(
            generated_path=generated_path,
            kind=kind,
            package_path=package_path,
            module_path=module_path,
            command=command,
            exit_code=result.returncode,
            ok=result.returncode == 0,
        )
    )


def package_dir(package_path: str, module_path: str) -> Path:
    suffix = package_path.removeprefix(module_path).strip("/")
    if not suffix:
        suffix = Path(package_path).name
    return Path(slugify(suffix.replace("/", "-"), default="package"))


def should_include_package(path: str, module_path: str, include_internal: bool) -> bool:
    if path == module_path:
        return False
    suffix = path.removeprefix(module_path).strip("/")
    if not suffix:
        return False
    parts = suffix.split("/")
    if not include_internal and ("internal" in parts or parts[0] == "cmd"):
        return False
    return True


def render_index(
    *,
    display_name: str,
    package_path: str,
    module_path: str,
    requested_version: str,
    resolved_version: str,
    latest_version: str | None,
    repo_url: str | None,
    generated_at: str,
    pages: list[PageRecord],
    warnings: list[str],
) -> str:
    lines = [
        f"# {display_name} Go Package Docs",
        "",
        f"> Package: `{package_path}`",
        f"> Module: `{module_path}`",
        f"> Resolved version: `{resolved_version}`",
        f"> Requested version: `{requested_version}`",
    ]
    if latest_version:
        lines.append(f"> Latest version reported by pkg.go.dev: `{latest_version}`")
    if repo_url:
        lines.append(f"> Repository: {repo_url}")
    lines.extend(
        [
            f"> Generated: `{generated_at}`",
            "",
            "## Start Here",
            "",
            "- Use `pkg-go-dev/overview.md` for module metadata, license, latest version, and vulnerability summary.",
            "- Use `pkg-go-dev/readme.md` for upstream usage guidance when available.",
            "- Use `pkg-go-dev/package-doc.md` for full API documentation.",
            "- Use `pkg-go-dev/symbols.md` for a compact exported API map.",
            "- Check `manifest.json` for command failures, version provenance, and refresh details.",
            "",
            "## References",
            "",
        ]
    )
    for page in pages:
        status = "OK" if page.ok else "FAILED"
        rel = page.generated_path.removeprefix("references/")
        lines.append(f"- [{rel}]({rel}) - `{page.kind}` ({status})")
    if warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")
    lines.extend(
        [
            "",
            "## Refresh",
            "",
            "```bash",
            "python3 scripts/update_docs.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def render_generated_skill_md(
    *,
    skill_name: str,
    display_name: str,
    package_path: str,
    module_path: str,
    requested_version: str,
    resolved_version: str,
    latest_version: str | None,
) -> str:
    description = (
        f"Offline Go package documentation for {package_path} at version {resolved_version}, "
        "generated from pkg.go.dev via godig. Use when answering API, symbol, example, README, "
        f"version, dependency, or vulnerability questions for {package_path}; start with references/INDEX.md."
    )
    latest_line = f"- Latest version: `{latest_version}`\n" if latest_version else ""
    return f"""---
name: {skill_name}
description: {yaml_quote(description)}
---

# {display_name}

Use this skill to answer questions from offline pkg.go.dev-derived documentation.

## Package Metadata

- Package: `{package_path}`
- Module: `{module_path}`
- Resolved version: `{resolved_version}`
- Requested version: `{requested_version}`
{latest_line}
## Navigation

1. Start with `references/INDEX.md`.
2. Read `references/pkg-go-dev/overview.md` for metadata and status.
3. Read `references/pkg-go-dev/readme.md` for upstream usage guidance.
4. Read `references/pkg-go-dev/package-doc.md` and `references/pkg-go-dev/symbols.md` for API details.
5. Check `references/manifest.json` for command failures and version provenance.

## Evidence Policy

- Treat files under `references/pkg-go-dev/` as pkg.go.dev data fetched through `godig`.
- Do not assume docs apply to another version unless the user asks you to compare versions.
- If a page records a failed `godig` command, do not use that page as evidence.

## Refresh

```bash
python3 scripts/update_docs.py
```
"""


def render_openai_yaml(skill_name: str, display_name: str, package_path: str) -> str:
    short = f"{package_path} Go docs"
    prompt = f"Use ${skill_name} to answer questions from the offline Go package docs for {package_path}."
    return "\n".join(
        [
            "interface:",
            f"  display_name: {yaml_quote(display_name)}",
            f"  short_description: {yaml_quote(short[:64])}",
            f"  default_prompt: {yaml_quote(prompt)}",
            "",
        ]
    )


def render_update_script(
    *,
    source: str,
    skill_name: str,
    display_name: str,
    version: str,
    extra_args: list[str],
) -> str:
    return f'''#!/usr/bin/env python3
"""Refresh this pkg.go.dev-derived documentation skill."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SOURCE = {source!r}
SKILL_NAME = {skill_name!r}
DISPLAY_NAME = {display_name!r}
VERSION = {version!r}
EXTRA_ARGS = {extra_args!r}


def find_generator(this_skill: Path) -> Path:
    env_path = os.environ.get("GO_PACKAGE_TO_SKILL_SCRIPT")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(this_skill.parent / "skillgen-go-package" / "scripts" / "create_skill_from_go_package.py")
    candidates.append(Path.cwd() / ".agents" / "skills" / "skillgen-go-package" / "scripts" / "create_skill_from_go_package.py")

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(
        "Could not find skillgen-go-package generator. Set GO_PACKAGE_TO_SKILL_SCRIPT "
        "to the path of create_skill_from_go_package.py."
    )


def main() -> int:
    this_skill = Path(__file__).resolve().parents[1]
    generator = find_generator(this_skill)
    command = [
        sys.executable,
        str(generator),
        SOURCE,
        "--skill-dir",
        str(this_skill),
        "--name",
        SKILL_NAME,
        "--display-name",
        DISPLAY_NAME,
        "--version",
        VERSION,
        "--overwrite",
    ]
    command.extend(EXTRA_ARGS)
    command.extend(sys.argv[1:])
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
'''


def command_records_to_json(records: list[CommandRecord]) -> list[dict[str, Any]]:
    return [
        {
            "name": record.name,
            "command": record.command,
            "generated_path": record.generated_path,
            "exit_code": record.exit_code,
            "ok": record.ok,
            "stderr": record.stderr,
        }
        for record in records
    ]


def page_records_to_json(records: list[PageRecord]) -> list[dict[str, Any]]:
    return [
        {
            "generated_path": record.generated_path,
            "kind": record.kind,
            "package_path": record.package_path,
            "module_path": record.module_path,
            "source": SOURCE_LABEL,
            "command": record.command,
            "exit_code": record.exit_code,
            "ok": record.ok,
        }
        for record in records
    ]


def update_extra_args(args: argparse.Namespace) -> list[str]:
    extra: list[str] = []
    if args.module:
        extra.extend(["--module", args.module])
    if args.timeout:
        extra.extend(["--timeout", args.timeout])
    if args.versions_limit != 40:
        extra.extend(["--versions-limit", str(args.versions_limit)])
    for package in args.extra_package:
        extra.extend(["--extra-package", package])
    if args.all_packages:
        extra.append("--all-packages")
    if args.include_internal_packages:
        extra.append("--include-internal-packages")
    if args.skip_readme:
        extra.append("--skip-readme")
    if args.skip_examples:
        extra.append("--skip-examples")
    if args.skip_vulns:
        extra.append("--skip-vulns")
    if args.skip_dependencies:
        extra.append("--skip-dependencies")
    return extra


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Go import path, pkg.go.dev URL, GitHub repo URL, local Go repo, or module@version.")
    parser.add_argument("--version", default=None, help="Module version. Defaults to latest unless source uses @version.")
    parser.add_argument("--module", help="Explicit module path for subpackage documentation.")
    parser.add_argument("--name", help="Generated skill name. Defaults to docs-<package>.")
    parser.add_argument("--display-name", help="Generated skill display name.")
    parser.add_argument("--skill-dir", help="Exact output skill directory.")
    parser.add_argument("--output", default=str(default_output_dir()), help="Directory for generated skills.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing target skill directory.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve metadata and print planned output without writing files.")
    parser.add_argument("--godig", help="Path to godig. Defaults to GODIG env var or PATH lookup.")
    parser.add_argument("--timeout", default="30s", help="godig HTTP timeout duration.")
    parser.add_argument("--versions-limit", type=int, default=40, help="Maximum versions to include in versions.md.")
    parser.add_argument("--extra-package", action="append", default=[], help="Additional package import path to document.")
    parser.add_argument("--all-packages", action="store_true", help="Document public non-internal subpackages in addition to the main package.")
    parser.add_argument("--include-internal-packages", action="store_true", help="With --all-packages, include internal and cmd packages.")
    parser.add_argument("--skip-readme", action="store_true", help="Skip module README.")
    parser.add_argument("--skip-examples", action="store_true", help="Skip package examples.")
    parser.add_argument("--skip-vulns", action="store_true", help="Skip vulnerabilities.")
    parser.add_argument("--skip-dependencies", action="store_true", help="Skip dependencies.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    package_path, source_version, source_kind = normalize_source(args.source)
    requested_version = args.version or source_version or "latest"
    godig = find_godig(args.godig)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    commands: list[CommandRecord] = []
    warnings: list[str] = []

    godig_version_result = run_command([godig, "version"], required=False)
    godig_version = (godig_version_result.stdout or godig_version_result.stderr).strip()

    overview_json_command = godig_command(godig, ["overview", package_path, "--version", requested_version], "json", args.timeout)
    overview_json_result = run_command(overview_json_command, required=True)
    record_command(commands, "overview-json", overview_json_command, None, overview_json_result)
    overview = read_json_output(overview_json_result, overview_json_command)
    if not isinstance(overview, dict):
        raise SystemExit(f"Unexpected overview JSON shape from {' '.join(overview_json_command)}")

    module_path = args.module or overview.get("modulePath") or package_path
    latest_version = overview.get("latestVersion") if isinstance(overview.get("latestVersion"), str) else None
    repo_url = overview.get("repoUrl") if isinstance(overview.get("repoUrl"), str) else None
    display_base = args.display_name or overview.get("name") or Path(package_path).name
    display_name = str(display_base).strip() or Path(package_path).name

    versions_json_command = godig_command(godig, ["versions", module_path, "--limit", str(max(args.versions_limit, 1))], "json", args.timeout)
    versions_json_result = run_command(versions_json_command, required=False)
    record_command(commands, "versions-json", versions_json_command, None, versions_json_result)
    versions_json: Any = []
    if versions_json_result.returncode == 0:
        versions_json = read_json_output(versions_json_result, versions_json_command)
    else:
        warnings.append(f"versions-json failed with exit code {versions_json_result.returncode}; latest resolution may be less precise.")

    resolved_version = requested_version
    if requested_version == "latest":
        resolved_version = latest_version or first_non_retracted_version(versions_json) or requested_version
    if resolved_version == "latest":
        warnings.append("Could not resolve latest to a concrete version; docs are generated with version `latest`.")

    skill_name = args.name or f"docs-{slugify(display_name or Path(package_path).name, default='go-package', max_length=56)}"
    skill_dir = Path(args.skill_dir).expanduser().resolve() if args.skill_dir else (Path(args.output).expanduser().resolve() / skill_name)

    if args.dry_run:
        print(json.dumps(
            {
                "source": args.source,
                "source_kind": source_kind,
                "package_path": package_path,
                "module_path": module_path,
                "requested_version": requested_version,
                "resolved_version": resolved_version,
                "latest_version": latest_version,
                "skill_name": skill_name,
                "skill_dir": str(skill_dir),
                "godig": godig,
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 0

    if skill_dir.exists():
        if not args.overwrite:
            print(f"[ERROR] Target skill already exists: {skill_dir}", file=sys.stderr)
            print("        Pass --overwrite or choose --name/--skill-dir.", file=sys.stderr)
            return 1
        shutil.rmtree(skill_dir)

    (skill_dir / "agents").mkdir(parents=True, exist_ok=True)
    (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_dir / "references" / "pkg-go-dev").mkdir(parents=True, exist_ok=True)

    pages: list[PageRecord] = []

    def write_main_page(command_parts: list[str], output: str, title: str, kind: str, filename: str, **kwargs: Any) -> None:
        write_godig_page(
            godig=godig,
            command_parts=command_parts,
            output=output,
            timeout=args.timeout,
            title=title,
            kind=kind,
            generated_rel=Path("references") / "pkg-go-dev" / filename,
            skill_dir=skill_dir,
            package_path=package_path,
            module_path=module_path,
            resolved_version=resolved_version,
            generated_at=generated_at,
            commands=commands,
            pages=pages,
            warnings=warnings,
            **kwargs,
        )

    common_package_flags = ["--module", module_path, "--version", resolved_version]
    common_module_flags = ["--version", resolved_version]

    write_main_page(["overview", package_path, "--version", resolved_version], "md", "Overview", "overview", "overview.md")
    write_main_page(["module", "info", module_path, *common_module_flags], "md", "Module Info", "module-info", "module-info.md")
    if not args.skip_readme:
        write_main_page(
            ["module", "readme", module_path, *common_module_flags],
            "raw",
            "README",
            "readme",
            "readme.md",
            transform_readme=True,
        )
    write_main_page(["package", "info", package_path, *common_package_flags], "md", "Package Info", "package-info", "package-info.md")
    write_main_page(
        ["package", "doc", package_path, *common_package_flags, "--format", "md"],
        "md",
        "Package Documentation",
        "package-doc",
        "package-doc.md",
    )
    if not args.skip_examples:
        write_main_page(
            ["package", "examples", package_path, *common_package_flags],
            "md",
            "Package Examples",
            "package-examples",
            "package-examples.md",
        )
    write_main_page(["package", "imports", package_path, *common_package_flags], "md", "Package Imports", "package-imports", "package-imports.md")
    write_main_page(["symbols", package_path, *common_package_flags], "md", "Exported Symbols", "symbols", "symbols.md")
    write_main_page(["packages", module_path, *common_module_flags], "md", "Module Packages", "packages", "packages.md")
    write_main_page(
        ["versions", module_path, "--limit", str(max(args.versions_limit, 1))],
        "md",
        "Versions",
        "versions",
        "versions.md",
    )
    if not args.skip_dependencies:
        write_main_page(["dependencies", module_path, *common_module_flags], "md", "Dependencies", "dependencies", "dependencies.md")
    if not args.skip_vulns:
        write_main_page(["vulns", module_path, *common_module_flags], "md", "Known Vulnerabilities", "vulns", "vulns.md")

    extra_packages = list(dict.fromkeys(args.extra_package))
    if args.all_packages:
        packages_json_command = godig_command(godig, ["packages", module_path, "--version", resolved_version], "json", args.timeout)
        packages_json_result = run_command(packages_json_command, required=False)
        record_command(commands, "packages-json", packages_json_command, None, packages_json_result)
        if packages_json_result.returncode == 0:
            packages_data = read_json_output(packages_json_result, packages_json_command)
            if isinstance(packages_data, list):
                for item in packages_data:
                    if isinstance(item, dict) and isinstance(item.get("path"), str):
                        candidate = item["path"]
                        if should_include_package(candidate, module_path, args.include_internal_packages):
                            extra_packages.append(candidate)
        else:
            warnings.append(f"packages-json failed with exit code {packages_json_result.returncode}; --all-packages skipped.")

    for extra_package in list(dict.fromkeys(extra_packages)):
        rel_dir = Path("references") / "pkg-go-dev" / "packages" / package_dir(extra_package, module_path)
        extra_flags = ["--module", module_path, "--version", resolved_version]
        for parts, output, title, kind, filename, transform in [
            (["package", "doc", extra_package, *extra_flags, "--format", "md"], "md", f"{extra_package} Documentation", "extra-package-doc", "package-doc.md", False),
            (["symbols", extra_package, *extra_flags], "md", f"{extra_package} Symbols", "extra-symbols", "symbols.md", False),
            (["package", "examples", extra_package, *extra_flags], "md", f"{extra_package} Examples", "extra-examples", "package-examples.md", False),
        ]:
            if args.skip_examples and kind == "extra-examples":
                continue
            write_godig_page(
                godig=godig,
                command_parts=parts,
                output=output,
                timeout=args.timeout,
                title=title,
                kind=kind,
                generated_rel=rel_dir / filename,
                skill_dir=skill_dir,
                package_path=extra_package,
                module_path=module_path,
                resolved_version=resolved_version,
                generated_at=generated_at,
                commands=commands,
                pages=pages,
                warnings=warnings,
                transform_readme=transform,
            )

    manifest = {
        "generator": "skillgen-go-package",
        "generator_version": GENERATOR_VERSION,
        "generated_at": generated_at,
        "input_source": args.source,
        "input_source_kind": source_kind,
        "package_path": package_path,
        "module_path": module_path,
        "requested_version": requested_version,
        "resolved_version": resolved_version,
        "latest_version": latest_version,
        "repo_url": repo_url,
        "godig": {
            "path": godig,
            "version": godig_version,
        },
        "commands": command_records_to_json(commands),
        "warnings": warnings,
    }

    write_text(skill_dir / "references" / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    write_text(skill_dir / "references" / "source-map.json", json.dumps(page_records_to_json(pages), ensure_ascii=False, indent=2) + "\n")
    write_text(
        skill_dir / "references" / "INDEX.md",
        render_index(
            display_name=display_name,
            package_path=package_path,
            module_path=module_path,
            requested_version=requested_version,
            resolved_version=resolved_version,
            latest_version=latest_version,
            repo_url=repo_url,
            generated_at=generated_at,
            pages=pages,
            warnings=warnings,
        ),
    )
    write_text(
        skill_dir / "SKILL.md",
        render_generated_skill_md(
            skill_name=skill_name,
            display_name=display_name,
            package_path=package_path,
            module_path=module_path,
            requested_version=requested_version,
            resolved_version=resolved_version,
            latest_version=latest_version,
        ),
    )
    write_text(skill_dir / "agents" / "openai.yaml", render_openai_yaml(skill_name, display_name, package_path))
    write_text(
        skill_dir / "scripts" / "update_docs.py",
        render_update_script(
            source=args.source,
            skill_name=skill_name,
            display_name=display_name,
            version=requested_version,
            extra_args=update_extra_args(args),
        ),
    )
    try:
        (skill_dir / "scripts" / "update_docs.py").chmod(0o755)
    except OSError:
        pass

    print(f"[OK] Generated skill: {skill_dir}")
    print(f"[OK] Package: {package_path}")
    print(f"[OK] Module: {module_path}")
    print(f"[OK] Version: {resolved_version} (requested {requested_version})")
    print(f"[OK] Reference pages: {len(pages)}")
    if warnings:
        print(f"[WARN] {len(warnings)} warnings; see references/manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
