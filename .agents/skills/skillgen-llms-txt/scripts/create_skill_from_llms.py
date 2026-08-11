#!/usr/bin/env python3
"""Generate an offline documentation skill from an llms.txt source."""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urldefrag, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

USER_AGENT = "Codex-skillgen-llms-txt/1.0"

MARKDOWN_LINK_RE = re.compile(r"(\[[^\]\n]*\]\()([^)]+)(\))")
HTML_HREF_RE = re.compile(r"(\bhref=[\"'])([^\"']+)([\"'])")
BARE_URL_RE = re.compile(r"https?://[^\s<>)\"']+")
HTML_START_RE = re.compile(r"^\s*(?:<!doctype\s+html\b|<html\b)", re.IGNORECASE)
FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")

TEXT_EXTENSIONS = {".md", ".mdx", ".markdown", ".txt", ".rst"}
BINARY_EXTENSIONS = {
    ".7z",
    ".avif",
    ".bmp",
    ".br",
    ".css",
    ".dmg",
    ".eot",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".mp3",
    ".mp4",
    ".otf",
    ".pdf",
    ".png",
    ".svg",
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


@dataclass(frozen=True)
class DocEntry:
    title: str
    url: str
    section: str
    description: str
    order: int


@dataclass(frozen=True)
class Page:
    entry: DocEntry
    requested_url: str
    fetched_url: str
    local_path: str
    content: str
    content_type: str


def fetch_response_text(url: str, timeout: int) -> tuple[str, str, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        content_type = response.headers.get_content_type() or ""
        return response.read().decode(charset, errors="replace"), response.geturl(), content_type


def fetch_response_text_with_retries(url: str, timeout: int, retries: int) -> tuple[str, str, str]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fetch_response_text(url, timeout)
        except HTTPError:
            raise
        except (URLError, TimeoutError) as error:
            last_error = error
            if attempt < retries:
                time.sleep(min(0.5 * (attempt + 1), 2.0))
                continue
            raise
    raise RuntimeError(f"unreachable retry state for {url}: {last_error}")


def read_text_resource(source: str, timeout: int, retries: int = 0) -> str:
    if source.startswith(("http://", "https://", "file://")):
        text, _effective_url, _content_type = fetch_response_text_with_retries(source, timeout, retries)
        return text
    return Path(source).read_text(encoding="utf-8")


def source_base_url(source: str) -> str:
    if source.startswith(("http://", "https://", "file://")):
        return source
    return Path(source).resolve().as_uri()


def resolve_url(raw_url: str, base_url: str) -> str | None:
    cleaned = raw_url.strip().strip("<>")
    if not cleaned or cleaned.startswith("#"):
        return None

    lower = cleaned.lower()
    if lower.startswith(("mailto:", "javascript:", "data:")):
        return None

    without_fragment, _fragment = urldefrag(cleaned)
    try:
        parsed = urlparse(without_fragment)
    except ValueError:
        return None
    if parsed.scheme and parsed.scheme not in {"http", "https", "file"}:
        return None

    absolute = urljoin(base_url, without_fragment)
    try:
        parsed_absolute = urlparse(absolute)
    except ValueError:
        return None
    if parsed_absolute.scheme not in {"http", "https", "file"}:
        return None

    if Path(unquote(parsed_absolute.path)).suffix.lower() in BINARY_EXTENSIONS:
        return None

    return absolute


def split_markdown_destination(destination: str) -> tuple[str, str]:
    stripped = destination.strip()
    if stripped.startswith("<"):
        end = stripped.find(">")
        if end != -1:
            return stripped[1:end], stripped[end + 1 :]

    parts = stripped.split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " " + parts[1]


def iter_markdown_link_urls(line: str) -> Iterable[tuple[str, re.Match[str]]]:
    for match in MARKDOWN_LINK_RE.finditer(line):
        destination = match.group(2).strip()
        url, _suffix = split_markdown_destination(destination)
        yield url, match


def markdown_link_label(match: re.Match[str]) -> str:
    prefix = match.group(1)
    if prefix.startswith("[") and prefix.endswith("]("):
        return prefix[1:-2]
    return prefix


BACKTICK_REF_RE = re.compile(r"`([^`]+)`")  # matches `path/to/file`


def parse_llms_entries(source_text: str, base_url: str, local_repo: Path | None = None) -> list[DocEntry]:
    entries: list[DocEntry] = []
    seen: set[str] = set()
    section = "Documentation"
    in_fence = False

    for line in source_text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        section_match = SECTION_RE.match(line)
        if section_match:
            section = strip_markdown(section_match.group(1)).strip() or "Documentation"
            continue

        for raw_url, match in iter_markdown_link_urls(line):
            absolute = resolve_url(raw_url, base_url)
            if not absolute:
                continue
            if is_llms_full_url(absolute):
                continue

            normalized = normalize_url(absolute)
            if normalized in seen:
                continue
            seen.add(normalized)

            title = strip_markdown(markdown_link_label(match)).strip() or route_title_from_url(absolute)
            description = ""
            tail = line[match.end() :].strip()
            if tail.startswith(":"):
                description = tail[1:].strip()
            entries.append(
                DocEntry(
                    title=title,
                    url=absolute,
                    section=section,
                    description=description,
                    order=len(entries),
                )
            )

    # If no markdown links found and a local repo is provided, parse backtick file references.
    if not entries and local_repo is not None:
        section = "Documentation"
        in_fence = False
        repo_root = local_repo.resolve()

        for line in source_text.splitlines():
            if FENCE_RE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            section_match = SECTION_RE.match(line)
            if section_match:
                section = strip_markdown(section_match.group(1)).strip() or "Documentation"
                continue

            for bt_match in BACKTICK_REF_RE.finditer(line):
                raw_path = bt_match.group(1).strip()
                # Skip URLs
                if raw_path.startswith(("http://", "https://", "www.")):
                    continue

                # Directory reference: `docs/topics/` — recursively expand to all doc files
                if raw_path.endswith("/"):
                    dir_path = (repo_root / raw_path).resolve()
                    if dir_path.is_dir():
                        _scan_repo_dir(dir_path, repo_root, section, entries, seen)
                    continue

                # Skip bare words (not paths with a /)
                if "/" not in raw_path:
                    continue

                # Resolve relative to the repo root
                candidate = (repo_root / raw_path).resolve()
                try:
                    candidate.relative_to(repo_root)
                except ValueError:
                    continue

                if candidate.is_file():
                    _add_local_entry(candidate, repo_root, section, entries, seen)

        # Fallback: if no entries found via backtick parsing, also scan standard doc paths
        if not entries:
            _scan_repo_dir(repo_root / "docs", repo_root, "Documentation", entries, seen)
            _scan_repo_dir(repo_root / "specification", repo_root, "Specification", entries, seen)

    return entries


def _add_local_entry(
    file_path: Path, repo_root: Path, section: str, entries: list[DocEntry], seen: set[str]
) -> None:
    """Add a single local file as a DocEntry if not already seen."""
    try:
        file_path.relative_to(repo_root)
    except ValueError:
        return

    uri = file_path.as_uri()
    normalized = normalize_url(uri)
    if normalized in seen:
        return
    seen.add(normalized)

    title = file_path.stem.replace("-", " ").replace("_", " ").title()
    entries.append(
        DocEntry(title=title, url=uri, section=section, description="", order=len(entries))
    )


def _scan_repo_dir(
    directory: Path, repo_root: Path, section: str, entries: list[DocEntry], seen: set[str]
) -> None:
    """Recursively scan a directory for documentation files."""
    if not directory.is_dir():
        return
    for child in sorted(directory.rglob("*")):
        if child.name.startswith("."):
            continue
        if child.is_file() and child.suffix.lower() in {".md", ".proto", ".mdx", ".txt", ".rst", ".yaml", ".yml", ".py", ".sh"}:
            _add_local_entry(child, repo_root, section, entries, seen)


def extract_linked_doc_urls(markdown: str, base_url: str) -> set[str]:
    urls: set[str] = set()
    in_fence = False

    for line in markdown.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        for raw_url, _match in iter_markdown_link_urls(line):
            absolute = resolve_url(raw_url, base_url)
            if absolute and not is_llms_full_url(absolute):
                urls.add(absolute)

        for match in HTML_HREF_RE.finditer(line):
            absolute = resolve_url(match.group(2), base_url)
            if absolute and not is_llms_full_url(absolute):
                urls.add(absolute)

        for match in BARE_URL_RE.finditer(line):
            absolute = resolve_url(match.group(0), base_url)
            if absolute and not is_llms_full_url(absolute):
                urls.add(absolute)

    return urls


def extract_title(source_text: str, source_url: str) -> str:
    for line in source_text.splitlines():
        match = HEADING_RE.match(line)
        if match and len(match.group(1)) == 1:
            title = strip_markdown(match.group(2)).strip()
            if title:
                return title
    parsed = urlparse(source_url)
    if parsed.netloc:
        return parsed.netloc.removeprefix("www.")
    return Path(source_url).stem or "Documentation"


def strip_markdown(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("*", "").replace("_", "")
    return text


def is_llms_full_url(url: str) -> bool:
    parsed = urlparse(url)
    return "llms-full" in Path(parsed.path).name.lower()


def infer_full_source(source: str, source_text: str, base_url: str) -> str | None:
    for line in source_text.splitlines():
        for raw_url, _match in iter_markdown_link_urls(line):
            absolute = resolve_url(raw_url, base_url)
            if absolute and is_llms_full_url(absolute):
                return absolute

    parsed = urlparse(source)
    if parsed.scheme in {"http", "https", "file"}:
        path = parsed.path
        if path.endswith("llms.txt"):
            return urlunparse(parsed._replace(path=path[: -len("llms.txt")] + "llms-full.txt"))
        return None

    source_path = Path(source)
    if source_path.name == "llms.txt":
        return str(source_path.with_name("llms-full.txt"))
    return None


def route_title_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if not path:
        return parsed.netloc or "Documentation"
    stem = Path(unquote(path)).stem or Path(unquote(path)).name
    return stem.replace("-", " ").replace("_", " ").title()


def slugify(value: str, default: str = "item", max_length: int = 64) -> str:
    value = unquote(value).strip().lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    if not value:
        value = default
    return value[:max_length].strip("-") or default


def safe_path_part(value: str) -> str:
    value = unquote(value).strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return value or "index"


def safe_relative_markdown_path(parts: list[str]) -> str:
    cleaned = [safe_path_part(part) for part in parts if part and part not in {".", ".."}]
    if not cleaned:
        cleaned = ["index"]
    if not cleaned[-1].lower().endswith((".md", ".mdx", ".markdown", ".txt", ".rst")):
        cleaned[-1] = f"{cleaned[-1]}.md"
    else:
        cleaned[-1] = f"{Path(cleaned[-1]).stem}.md"
    return "/".join(cleaned)


def relative_url_path(fetched_url: str, source_base: str) -> list[str] | None:
    parsed = urlparse(fetched_url)
    parsed_source = urlparse(source_base)
    if (parsed.scheme, parsed.netloc) != (parsed_source.scheme, parsed_source.netloc):
        return None

    if parsed.scheme == "file":
        source_path = Path(unquote(parsed_source.path))
        base_dir = source_path if source_path.is_dir() else source_path.parent
        try:
            relative = os.path.relpath(unquote(parsed.path), start=str(base_dir))
        except ValueError:
            return None
        if relative == "." or relative.startswith(f"..{os.sep}") or relative == ".." or os.path.isabs(relative):
            return None
        return [part for part in Path(relative).parts if part not in {"", ".", ".."}]

    source_path = unquote(parsed_source.path or "/")
    base_dir = source_path if source_path.endswith("/") else source_path.rsplit("/", 1)[0] or "/"
    relative = posixpath.relpath(unquote(parsed.path or "/"), start=base_dir)
    if relative == "." or relative.startswith("../") or relative == "..":
        return None
    return [part for part in relative.split("/") if part not in {"", ".", ".."}]


def local_path_for_page(entry: DocEntry, fetched_url: str, source_base: str, used_paths: set[str]) -> str:
    parsed = urlparse(fetched_url)
    relative_parts = relative_url_path(fetched_url, source_base)

    parts: list[str]
    if relative_parts:
        parts = relative_parts
    elif parsed.path.strip("/"):
        path = unquote(parsed.path).strip("/")
        raw_parts = [part for part in path.split("/") if part and part not in {".", ".."}]
        if raw_parts and raw_parts[0] == "llms":
            raw_parts = raw_parts[1:]
        if raw_parts:
            parts = raw_parts
        else:
            parts = [slugify(entry.title)]
    else:
        parts = [slugify(entry.title)]

    local_path = safe_relative_markdown_path(parts)
    if "/" not in local_path:
        local_path = f"pages/{local_path}"

    if local_path not in used_paths:
        used_paths.add(local_path)
        return local_path

    stem = local_path[:-3] if local_path.endswith(".md") else local_path
    for suffix in range(2, 10_000):
        candidate = f"{stem}-{suffix}.md"
        if candidate not in used_paths:
            used_paths.add(candidate)
            return candidate
    raise RuntimeError(f"could not allocate unique local path for {entry.url}")


def normalize_url(url: str) -> str:
    url_without_fragment, _fragment = urldefrag(url)
    parsed = urlparse(url_without_fragment)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = quote(unquote(parsed.path or "/"), safe="/:@")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def url_aliases(url: str) -> set[str]:
    aliases: set[str] = set()
    normalized = normalize_url(url)
    aliases.add(normalized)

    parsed = urlparse(normalized)
    path = parsed.path
    suffix = Path(path).suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        aliases.add(urlunparse(parsed._replace(path=path[: -len(suffix)])))
    elif not suffix:
        aliases.add(urlunparse(parsed._replace(path=f"{path}.md")))
    return aliases


def candidate_doc_urls(url: str, append_suffix: str | None) -> list[str]:
    candidates: list[str] = [url]
    if append_suffix:
        parsed = urlparse(url)
        suffix = Path(parsed.path).suffix.lower()
        if parsed.scheme in {"http", "https", "file"} and suffix not in TEXT_EXTENSIONS:
            appended_path = parsed.path.rstrip("/") + append_suffix
            candidate = urlunparse(parsed._replace(path=appended_path))
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def looks_like_html(text: str, content_type: str) -> bool:
    if HTML_START_RE.search(text):
        return True
    return content_type.lower().startswith("text/html") and "<body" in text[:2000].lower()


def download_doc(
    entry: DocEntry,
    timeout: int,
    retries: int,
    append_suffix: str | None,
    allow_html: bool,
    used_paths: set[str],
    used_paths_lock: Lock,
    source_base: str,
) -> tuple[Page | None, str | None]:
    errors: list[str] = []
    html_candidate: tuple[str, str, str] | None = None

    for candidate in candidate_doc_urls(entry.url, append_suffix):
        try:
            content, fetched_url, content_type = fetch_response_text_with_retries(candidate, timeout, retries)
        except HTTPError as error:
            errors.append(f"HTTP {error.code} from {candidate}")
            continue
        except URLError as error:
            errors.append(f"{error.reason} from {candidate}")
            continue
        except TimeoutError:
            errors.append(f"timeout from {candidate}")
            continue

        if looks_like_html(content, content_type) and not allow_html:
            html_candidate = (content, fetched_url, content_type)
            errors.append(f"HTML response from {candidate}")
            continue

        with used_paths_lock:
            local_path = local_path_for_page(entry, fetched_url, source_base, used_paths)
        return (
            Page(
                entry=entry,
                requested_url=candidate,
                fetched_url=fetched_url,
                local_path=local_path,
                content=content,
                content_type=content_type,
            ),
            None,
        )

    if html_candidate and allow_html:
        content, fetched_url, content_type = html_candidate
        with used_paths_lock:
            local_path = local_path_for_page(entry, fetched_url, source_base, used_paths)
        return (
            Page(
                entry=entry,
                requested_url=entry.url,
                fetched_url=fetched_url,
                local_path=local_path,
                content=content,
                content_type=content_type,
            ),
            None,
        )

    return None, "; ".join(errors) or f"could not download {entry.url}"


def mirror_docs(
    initial_entries: list[DocEntry],
    max_pages: int,
    timeout: int,
    delay: float,
    retries: int,
    workers: int,
    append_suffix: str | None,
    allow_html: bool,
    recursive: bool,
    source_base: str,
) -> tuple[dict[str, Page], dict[str, str]]:
    pending: list[DocEntry] = list(initial_entries)
    queued: set[str] = {normalize_url(entry.url) for entry in initial_entries}
    pages: dict[str, Page] = {}
    failures: dict[str, str] = {}
    used_paths: set[str] = set()
    used_paths_lock = Lock()
    worker_count = max(1, workers)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        while pending:
            remaining = max_pages - len(pages)
            if remaining <= 0:
                for entry in pending:
                    failures[entry.url] = f"skipped after --max-pages={max_pages}"
                break

            batch = pending[:remaining]
            for entry in pending[remaining:]:
                failures[entry.url] = f"skipped after --max-pages={max_pages}"
            pending = []

            futures = {}
            for entry in batch:
                futures[executor.submit(download_doc, entry, timeout, retries, append_suffix, allow_html, used_paths, used_paths_lock, source_base)] = entry
                if delay > 0:
                    time.sleep(delay)

            for future in as_completed(futures):
                entry = futures[future]
                try:
                    page, error = future.result()
                except Exception as error:  # noqa: BLE001 - keep one bad page from aborting the mirror.
                    failures[entry.url] = f"{type(error).__name__}: {error}"
                    continue
                if error:
                    failures[entry.url] = error
                    continue
                if not page:
                    failures[entry.url] = "download returned no page"
                    continue

                pages[normalize_url(entry.url)] = page

                if recursive:
                    page_base = page.fetched_url
                    for linked_url in sorted(extract_linked_doc_urls(page.content, page_base)):
                        normalized = normalize_url(linked_url)
                        if normalized in queued or normalized in pages or normalized in failures:
                            continue
                        if not same_origin(linked_url, entry.url):
                            continue
                        queued.add(normalized)
                        pending.append(
                            DocEntry(
                                title=route_title_from_url(linked_url),
                                url=linked_url,
                                section="Discovered",
                                description="Discovered from mirrored documentation links.",
                                order=len(queued),
                            )
                        )

    return pages, failures


def same_origin(left: str, right: str) -> bool:
    left_parsed = urlparse(left)
    right_parsed = urlparse(right)
    return (left_parsed.scheme, left_parsed.netloc) == (right_parsed.scheme, right_parsed.netloc)


def build_link_targets(pages: dict[str, Page]) -> dict[str, str]:
    targets: dict[str, str] = {}
    for page in pages.values():
        for alias in url_aliases(page.entry.url) | url_aliases(page.requested_url) | url_aliases(page.fetched_url):
            targets.setdefault(alias, page.local_path)
    return targets


def local_link_for_url(raw_url: str, current_path: Path, references_dir: Path, link_targets: dict[str, str], base_url: str) -> str | None:
    absolute = resolve_url(raw_url, base_url)
    if not absolute:
        return None
    _without_fragment, fragment = urldefrag(raw_url.strip().strip("<>"))

    local_path = None
    for alias in url_aliases(absolute):
        if alias in link_targets:
            local_path = link_targets[alias]
            break
    if not local_path:
        return None

    target_path = references_dir / local_path
    relative = os.path.relpath(target_path, start=current_path.parent).replace(os.sep, "/")
    if current_path.resolve() == target_path.resolve() and fragment:
        relative = ""
    if fragment:
        return f"{relative}#{fragment}" if relative else f"#{fragment}"
    return relative


def rewrite_markdown_links(text: str, current_path: Path, references_dir: Path, link_targets: dict[str, str], base_url: str) -> str:
    in_fence = False
    rewritten_lines: list[str] = []

    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            rewritten_lines.append(line)
            continue
        if in_fence:
            rewritten_lines.append(line)
            continue

        line = MARKDOWN_LINK_RE.sub(
            lambda match: rewrite_markdown_link(match, current_path, references_dir, link_targets, base_url),
            line,
        )
        line = HTML_HREF_RE.sub(
            lambda match: rewrite_html_href(match, current_path, references_dir, link_targets, base_url),
            line,
        )
        line = BARE_URL_RE.sub(
            lambda match: rewrite_bare_url(match, current_path, references_dir, link_targets, base_url),
            line,
        )
        rewritten_lines.append(line)

    return "\n".join(rewritten_lines).rstrip() + "\n"


def rewrite_markdown_link(
    match: re.Match[str],
    current_path: Path,
    references_dir: Path,
    link_targets: dict[str, str],
    base_url: str,
) -> str:
    destination = match.group(2).strip()
    url, suffix = split_markdown_destination(destination)
    replacement = local_link_for_url(url, current_path, references_dir, link_targets, base_url)
    if not replacement:
        return match.group(0)
    if destination.startswith("<"):
        new_destination = f"<{replacement}>{suffix}"
    else:
        new_destination = f"{replacement}{suffix}"
    return f"{match.group(1)}{new_destination}{match.group(3)}"


def rewrite_html_href(
    match: re.Match[str],
    current_path: Path,
    references_dir: Path,
    link_targets: dict[str, str],
    base_url: str,
) -> str:
    replacement = local_link_for_url(match.group(2), current_path, references_dir, link_targets, base_url)
    if not replacement:
        return match.group(0)
    return f"{match.group(1)}{replacement}{match.group(3)}"


def rewrite_bare_url(
    match: re.Match[str],
    current_path: Path,
    references_dir: Path,
    link_targets: dict[str, str],
    base_url: str,
) -> str:
    replacement = local_link_for_url(match.group(0), current_path, references_dir, link_targets, base_url)
    return replacement or match.group(0)


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def render_index(
    title: str,
    source_text: str,
    source_label: str,
    references_dir: Path,
    link_targets: dict[str, str],
    pages: dict[str, Page],
    failures: dict[str, str],
    full_source_label: str | None,
    source_base: str,
) -> str:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    source_index = rewrite_markdown_links(source_text, references_dir / "index.md", references_dir, link_targets, source_base)
    lines = [
        f"# {title} Offline Documentation",
        "",
        f"> Generated by `skillgen-llms-txt` at {generated_at}.",
        f"> Source: `{source_label}`.",
        f"> Downloaded pages: {len(pages)}.",
    ]
    if full_source_label:
        lines.append(f"> Full bundle: `llms-full.txt` from `{full_source_label}`.")
    lines.extend(
        [
            "",
            "Use this index to choose focused files under this `references/` directory instead of loading the full mirror.",
            "",
            source_index.rstrip(),
        ]
    )
    if failures:
        lines.extend(
            [
                "",
                "## Download Failures",
                "",
                "These links were discovered but could not be mirrored. Keep their original upstream URLs when encountered.",
                "",
            ]
        )
        for url, reason in sorted(failures.items()):
            lines.append(f"- `{url}`: {reason}")
    return "\n".join(lines).rstrip() + "\n"


def render_manifest(
    title: str,
    skill_name: str,
    source_label: str,
    full_source_label: str | None,
    pages: dict[str, Page],
    failures: dict[str, str],
) -> str:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "skillgen-llms-txt",
        "title": title,
        "skill_name": skill_name,
        "source": source_label,
        "full_source": full_source_label,
        "page_count": len(pages),
        "pages": [
            {
                "title": page.entry.title,
                "section": page.entry.section,
                "description": page.entry.description,
                "source_url": page.entry.url,
                "requested_url": page.requested_url,
                "fetched_url": page.fetched_url,
                "local_path": page.local_path,
                "content_type": page.content_type,
            }
            for page in sorted(pages.values(), key=lambda item: (item.entry.order, item.local_path))
        ],
        "failures": [{"url": url, "reason": reason} for url, reason in sorted(failures.items())],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def write_references(
    skill_dir: Path,
    title: str,
    skill_name: str,
    source_text: str,
    source_label: str,
    source_base: str,
    pages: dict[str, Page],
    failures: dict[str, str],
    full_text: str | None,
    full_source_label: str | None,
) -> None:
    if not pages:
        raise RuntimeError("No pages were downloaded; refusing to replace offline references.")

    references_dir = skill_dir / "references"
    temp_dir = skill_dir / ".references.tmp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    link_targets = build_link_targets(pages)
    for page in sorted(pages.values(), key=lambda item: item.local_path):
        target = references_dir / page.local_path
        temp_target = temp_dir / page.local_path
        heading = f"<!-- Source: {page.fetched_url} -->\n\n"
        rewritten = rewrite_markdown_links(page.content, target, references_dir, link_targets, page.fetched_url)
        write_atomic(temp_target, heading + rewritten)

    write_atomic(
        temp_dir / "index.md",
        render_index(title, source_text, source_label, references_dir, link_targets, pages, failures, full_source_label if full_text else None, source_base),
    )
    write_atomic(temp_dir / "llms.txt", source_text.rstrip() + "\n")
    if full_text:
        write_atomic(temp_dir / "llms-full.txt", full_text.rstrip() + "\n")
    write_atomic(temp_dir / "manifest.json", render_manifest(title, skill_name, source_label, full_source_label if full_text else None, pages, failures))

    if references_dir.exists():
        shutil.rmtree(references_dir)
    temp_dir.replace(references_dir)


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_skill_md(skill_name: str, display_name: str, description: str, source: str) -> str:
    return f"""---
name: {skill_name}
description: {yaml_quote(description)}
---

# {display_name}

## Overview

Use this skill to answer {display_name} questions from bundled offline Markdown docs generated from an llms.txt source. Prefer focused files under `references/` over loading the full bundle.

## Reference Workflow

1. Start with `references/index.md` to choose the relevant guide, API page, component, or tutorial.
2. Read focused files under `references/` before answering or editing code.
3. Use `rg` across the mirrored docs for APIs, options, examples, migration notes, or accessibility details:

```bash
rg -n "install|configure|API|migration|accessibility|example" path/to/{skill_name}/references
```

4. Use `references/llms-full.txt` only as a fallback when a topic spans many pages or focused search misses context.
5. Treat `references/manifest.json` as the inventory of source URLs and local paths when tracing where a page came from.

## Implementation Guidance

- Follow the source documentation over model memory for current API names, imports, configuration, and behavior.
- Check adjacent setup, migration, and conceptual pages before making broad implementation changes.
- Keep generated docs in `references/`; put any future project-specific notes in this `SKILL.md` so refreshes can safely replace the mirror.

## Offline Docs Layout

- `references/index.md`: local navigation index generated from the source llms.txt.
- `references/`: mirrored Markdown pages, stored by source route when possible.
- `references/llms.txt`: source index from `{source}`.
- `references/llms-full.txt`: optional full offline bundle, when the upstream publishes one.
- `references/manifest.json`: generated source URL, fetched URL, local path, and failure inventory.

## Updating The Docs

Run the updater from the repository root or pass an absolute path:

```bash
python3 path/to/{skill_name}/scripts/update_docs.py
```

The updater refreshes `references/` from `{source}`. It preserves this `SKILL.md` by default; pass `--overwrite-skill` only when you intentionally want to regenerate the skill instructions and UI metadata.
"""


def render_openai_yaml(skill_name: str, display_name: str, short_description: str) -> str:
    default_prompt = f"Use ${skill_name} to answer a question from the bundled offline documentation."
    return "\n".join(
        [
            "interface:",
            f"  display_name: {yaml_quote(display_name)}",
            f"  short_description: {yaml_quote(short_description)}",
            f"  default_prompt: {yaml_quote(default_prompt)}",
            "",
        ]
    )


def render_update_script(
    source: str,
    skill_name: str,
    display_name: str,
    append_suffix: str | None,
    allow_html: bool,
    recursive: bool,
    skip_full: bool,
    full_source: str | None,
    local_repo: str | None,
    skill_dir: Path | None = None,
) -> str:
    extra_args = []
    if append_suffix is not None:
        extra_args.extend(["--append-suffix", append_suffix])
    else:
        extra_args.extend(["--append-suffix", ""])
    if allow_html:
        extra_args.append("--allow-html")
    if recursive:
        extra_args.append("--recursive")
    if skip_full:
        extra_args.append("--skip-full")
    elif full_source:
        extra_args.extend(["--full-source", full_source])
    if local_repo:
        extra_args.extend(["--local-repo", local_repo])
    return f'''#!/usr/bin/env python3
"""Refresh this generated offline documentation skill."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SOURCE = {source!r}
SKILL_NAME = {skill_name!r}
DISPLAY_NAME = {display_name!r}
EXTRA_ARGS = {extra_args!r}


def find_generator(this_skill: Path) -> Path:
    env_path = os.environ.get("LLMS_TXT_TO_SKILL_SCRIPT")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(this_skill.parent / "skillgen-llms-txt" / "scripts" / "create_skill_from_llms.py")
    candidates.append(Path.cwd() / ".agents" / "skills" / "skillgen-llms-txt" / "scripts" / "create_skill_from_llms.py")

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(
        "Could not find skillgen-llms-txt generator. Set LLMS_TXT_TO_SKILL_SCRIPT "
        "to the path of create_skill_from_llms.py."
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
        "--overwrite",
    ]
    command.extend(EXTRA_ARGS)
    command.extend(sys.argv[1:])
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
'''


def write_skill_files(
    skill_dir: Path,
    skill_name: str,
    display_name: str,
    description: str,
    short_description: str,
    source: str,
    overwrite_skill: bool,
    write_update_script: bool,
    append_suffix: str | None,
    allow_html: bool,
    recursive: bool,
    skip_full: bool,
    full_source: str | None,
    local_repo: str | None = None,
) -> None:
    skill_md = skill_dir / "SKILL.md"
    if overwrite_skill or not skill_md.exists():
        write_atomic(skill_md, render_skill_md(skill_name, display_name, description, source))

    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if overwrite_skill or not openai_yaml.exists():
        write_atomic(openai_yaml, render_openai_yaml(skill_name, display_name, short_description))

    if write_update_script:
        update_script = skill_dir / "scripts" / "update_docs.py"
        if overwrite_skill or not update_script.exists():
            write_atomic(
                update_script,
                render_update_script(source, skill_name, display_name, append_suffix, allow_html, recursive, skip_full, full_source, local_repo, skill_dir=skill_dir),
            )
            update_script.chmod(0o755)


def default_output_dir() -> Path:
    cwd_agents = Path.cwd() / ".agents" / "skills"
    if cwd_agents.is_dir():
        return cwd_agents
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home) / "skills"
    return Path.home() / ".codex" / "skills"


def resolve_skill_dir(args: argparse.Namespace, skill_name: str) -> Path:
    if args.skill_dir:
        return Path(args.skill_dir).expanduser().resolve()
    return (Path(args.output).expanduser().resolve() / skill_name)


def mirror_local_repo(
    initial_entries: list[DocEntry],
    repo_root: Path,
) -> tuple[dict[str, Page], dict[str, str]]:
    """Mirror documentation files from a local repository, skipping URL entries."""
    pages: dict[str, Page] = {}
    failures: dict[str, str] = {}
    used_paths: set[str] = set()
    repo_root = repo_root.resolve()

    for entry in initial_entries:
        parsed = urlparse(entry.url)
        if parsed.scheme not in {"file", ""}:
            # Skip URL-based entries in local-repo mode
            failures[entry.url] = "skipped URL entry in local-repo mode"
            continue

        local_path = Path(unquote(parsed.path)) if parsed.path else Path(entry.url)
        if not local_path.is_file():
            failures[entry.url] = "local file not found"
            continue

        try:
            content = local_path.read_text(encoding="utf-8")
        except Exception as exc:
            failures[entry.url] = f"read error: {exc}"
            continue

        suffix = local_path.suffix.lower()
        if suffix in {".md", ".mdx", ".markdown", ".txt", ".rst"}:
            content_type = "text/markdown"
        else:
            content_type = "text/plain"

        # Compute relative path from repo root
        try:
            rel = local_path.relative_to(repo_root)
        except ValueError:
            rel = Path(local_path.name)

        ref_path = str(rel.as_posix())
        # Deduplicate used paths
        if ref_path in used_paths:
            stem = ref_path.rsplit(".", 1)[0]
            ext = ref_path.rsplit(".", 1)[1] if "." in ref_path else ""
            for i in range(2, 10_000):
                candidate = f"{stem}-{i}.{ext}" if ext else f"{stem}-{i}"
                if candidate not in used_paths:
                    ref_path = candidate
                    break
        used_paths.add(ref_path)

        page = Page(
            entry=entry,
            requested_url=entry.url,
            fetched_url=entry.url,
            local_path=ref_path,
            content=content,
            content_type=content_type,
        )
        pages[normalize_url(entry.url)] = page

    return pages, failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an offline Codex skill from an llms.txt URL or file.")
    parser.add_argument("source_arg", nargs="?", help="llms.txt URL or local file path.")
    parser.add_argument("--source", dest="source_option", help="llms.txt URL or local file path. Overrides the positional source.")
    parser.add_argument("--name", help='Generated skill name. Defaults to a "docs-<topic>" slug from the llms.txt title.')
    parser.add_argument("--display-name", help="Human-facing generated skill name. Defaults to the llms.txt title.")
    parser.add_argument("--description", help="Generated skill frontmatter description.")
    parser.add_argument("--short-description", help="Generated agents/openai.yaml short description.")
    parser.add_argument("--output", default=str(default_output_dir()), help="Parent directory for the generated skill.")
    parser.add_argument("--skill-dir", help="Exact generated skill directory. Overrides --output/--name placement.")
    parser.add_argument("--full-source", default="auto", help="llms-full source URL/path, 'auto', or 'none'.")
    parser.add_argument("--max-pages", type=int, default=500, help="Safety limit for downloaded docs.")
    parser.add_argument("--timeout", type=int, default=30, help="Network timeout in seconds.")
    parser.add_argument("--delay", type=float, default=0.0, help="Delay between scheduling downloads in seconds.")
    parser.add_argument("--retries", type=int, default=3, help="Retries for transient network failures.")
    parser.add_argument("--workers", type=int, default=8, help="Parallel download workers.")
    parser.add_argument("--recursive", action="store_true", help="Also mirror same-origin docs linked by downloaded pages.")
    parser.add_argument("--local-repo", help="Path to a local Git clone. When the llms.txt has no markdown links, parse backtick file references and read them from this local repository.")
    parser.add_argument("--allow-html", action="store_true", help="Store HTML responses when Markdown endpoints are unavailable.")
    parser.add_argument("--append-suffix", default=".md", help="Fallback suffix appended to non-text doc URLs. Use empty string to disable.")
    parser.add_argument("--skip-full", action="store_true", help="Do not download llms-full.txt.")
    parser.add_argument("--no-update-script", action="store_true", help="Do not create scripts/update_docs.py in the generated skill.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing references in an existing skill directory.")
    parser.add_argument("--overwrite-skill", action="store_true", help="Also overwrite SKILL.md, agents/openai.yaml, and updater script.")
    parser.add_argument("--dry-run", action="store_true", help="Download and report without writing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source_option or args.source_arg
    if not source:
        print("[ERROR] Provide an llms.txt URL or file path.", file=sys.stderr)
        return 2

    local_repo = Path(args.local_repo).expanduser().resolve() if args.local_repo else None
    stored_source = source if source.startswith(("http://", "https://", "file://")) else str(Path(source).expanduser().resolve())
    source_text = read_text_resource(source, args.timeout, args.retries)

    if local_repo and not source.startswith(("http://", "https://")):
        # When using a local repo with a local llms.txt file, use the repo URL as base
        base_url = local_repo.as_uri()
    else:
        base_url = source_base_url(source)

    title = extract_title(source_text, source)
    if args.name:
        skill_name = slugify(args.name, default="docs-skill")
    else:
        skill_name = slugify(title, default="docs-skill")
        if not skill_name.startswith("docs-"):
            skill_name = f"docs-{skill_name}"
    display_name = args.display_name or title
    description = args.description or (
        f"Offline {display_name} documentation generated from llms.txt. "
        f"Use when answering questions, writing code, reviewing integrations, or checking current APIs for {display_name} from bundled reference docs."
    )
    short_description = args.short_description or f"Offline {display_name} docs from llms.txt"
    skill_dir = resolve_skill_dir(args, skill_name)
    skill_existed = skill_dir.exists()

    entries = parse_llms_entries(source_text, base_url, local_repo=local_repo)
    if not entries:
        print(f"[ERROR] No documentation links found in source: {source}", file=sys.stderr)
        return 1

    if skill_dir.exists() and not args.overwrite and not args.dry_run:
        print(f"[ERROR] Target skill already exists: {skill_dir}", file=sys.stderr)
        print("        Pass --overwrite to refresh references, or choose --name/--skill-dir.", file=sys.stderr)
        return 1

    append_suffix = args.append_suffix or None
    if local_repo:
        pages, failures = mirror_local_repo(entries, local_repo)
    else:
        pages, failures = mirror_docs(
            entries,
            args.max_pages,
            args.timeout,
            args.delay,
            args.retries,
            args.workers,
            append_suffix,
            args.allow_html,
            args.recursive,
            base_url,
        )

    full_text = None
    full_source = None
    if not args.skip_full and args.full_source != "none":
        full_source = infer_full_source(source, source_text, base_url) if args.full_source == "auto" else args.full_source
        if full_source:
            try:
                full_text = read_text_resource(full_source, args.timeout, args.retries)
            except (HTTPError, URLError, TimeoutError, OSError) as error:
                failures[str(full_source)] = f"could not download full bundle: {error}"

    if args.dry_run:
        print(f"Title: {title}")
        print(f"Skill name: {skill_name}")
        print(f"Target skill dir: {skill_dir}")
        print(f"Source links: {len(entries)}")
        print(f"Downloaded pages: {len(pages)}")
        print(f"Full bundle: {'downloaded' if full_text else 'not downloaded'}")
        print(f"Failures: {len(failures)}")
        for url, reason in sorted(failures.items()):
            print(f"- {url}: {reason}")
        return 0 if pages else 1

    skill_dir.mkdir(parents=True, exist_ok=True)
    write_references(skill_dir, title, skill_name, source_text, stored_source, base_url, pages, failures, full_text, full_source)
    local_repo_str = str(local_repo) if local_repo else None
    write_skill_files(
        skill_dir,
        skill_name,
        display_name,
        description,
        short_description,
        stored_source,
        args.overwrite_skill,
        not args.no_update_script,
        append_suffix,
        args.allow_html,
        args.recursive,
        args.skip_full,
        full_source,
        local_repo=local_repo_str,
    )

    print(f"[OK] Generated skill: {skill_dir}")
    print(f"[OK] Downloaded {len(pages)} pages into {skill_dir / 'references'}")
    if full_text:
        print("[OK] Saved llms-full.txt")
    if failures:
        print(f"[WARN] {len(failures)} docs could not be mirrored; see references/index.md")
    if skill_existed and not args.overwrite_skill:
        print("[INFO] Existing SKILL.md/openai.yaml were preserved when present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
