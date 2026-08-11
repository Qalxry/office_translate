#!/usr/bin/env python3
"""Explore a documentation target and recommend a skillgen route.

The script is intentionally non-executing. It probes public HTTP endpoints,
docs pages, sitemaps, and pkg.go.dev pages. For explicit GitHub repository
URLs it prefers a shallow Git clone and local file analysis, which avoids the
GitHub REST API rate limits that affect tree/search endpoints. It does not
install dependencies, build docs, or execute project code.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import html.parser
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


USER_AGENT = "skillgen-auto/1.0 (+https://github.com/openai/codex)"
DOC_PATH_HINTS = (
    "docs",
    "documentation",
    "guide",
    "guides",
    "learn",
    "reference",
    "api",
    "manual",
    "concept",
    "concepts",
    "tutorial",
    "tutorials",
    "quickstart",
    "getting-started",
    "usage",
    "examples",
    "configuration",
    "cli",
)
SKIP_PATH_HINTS = (
    "blog",
    "pricing",
    "login",
    "signup",
    "sign-in",
    "careers",
    "jobs",
    "changelog",
    "releases",
    "download",
    "downloads",
    "assets",
    "img",
    "image",
    "images",
    "search",
)
DOC_PREFIXES = {"docs", "documentation", "en", "latest", "stable", "main", "current"}
NON_DOC_SITE_HOSTS = {
    "github.com",
    "raw.githubusercontent.com",
    "pkg.go.dev",
    "api.github.com",
}
DOC_FRAMEWORK_HINTS = {
    "docusaurus": ("docusaurus", "__docusaurus", "theme-doc-markdown"),
    "vitepress": ("vitepress", "__vitepress", "VPContent"),
    "nextra": ("nextra", "__nextra", "nextra-theme-docs"),
    "starlight": ("starlight", "sl-markdown-content", "@astrojs/starlight"),
    "gitbook": ("gitbook", "gitbook-root", "page-body"),
    "readthedocs": ("readthedocs", "sphinx", "wy-nav-content"),
    "mkdocs": ("mkdocs", "md-content", "mkdocs-material"),
    "mdbook": ("mdbook", "book.js", "chapter"),
    "mintlify": ("mintlify", "mint.json", "mintlify"),
}


@dataclasses.dataclass
class HttpResult:
    url: str
    status: int | None = None
    final_url: str = ""
    content_type: str = ""
    body: str = ""
    error: str = ""
    elapsed_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300 and not self.error


class SimplePageParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._in_h1 = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        if tag in {"script", "style", "svg", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])
        elif tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        elif self._in_h1:
            self.h1_parts.append(text)
        self.text_parts.append(text)

    @property
    def title(self) -> str:
        if self.h1_parts:
            return " ".join(self.h1_parts)[:160]
        return " ".join(self.title_parts)[:160]

    @property
    def text_len(self) -> int:
        return len(" ".join(self.text_parts))


def slugify(value: str, fallback: str = "docs-target") -> str:
    value = urllib.parse.unquote(value)
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or fallback


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def with_scheme(value: str) -> str:
    if re.match(r"^[a-z][a-z0-9+.-]*://", value, re.I):
        return value
    return "https://" + value


def is_url(value: str) -> bool:
    return bool(re.match(r"^[a-z][a-z0-9+.-]*://", value, re.I))


def parse_github_repo(value: str) -> tuple[str, str] | None:
    candidate = with_scheme(value) if "github.com/" in value and not is_url(value) else value
    parsed = urllib.parse.urlparse(candidate)
    if parsed.netloc.lower() != "github.com":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    if not owner or not repo:
        return None
    return owner, repo


def repo_url(owner: str, repo: str) -> str:
    return f"https://github.com/{owner}/{repo}"


def looks_like_go_import(value: str) -> bool:
    if is_url(value):
        return False
    parts = value.split("/")
    if len(parts) < 2:
        return False
    first = parts[0]
    return "." in first or first in {"golang.org", "go.opentelemetry.io"}


def looks_like_local_path(value: str) -> bool:
    return value.startswith((".", "/", "~")) or os.path.exists(os.path.expanduser(value))


def pkg_from_pkg_go_dev(value: str) -> str | None:
    parsed = urllib.parse.urlparse(value)
    if parsed.netloc.lower() != "pkg.go.dev":
        return None
    path = parsed.path.strip("/")
    return urllib.parse.unquote(path) if path else None


def request_headers(token_env: str) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    token = os.environ.get(token_env)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def http_get(
    url: str,
    *,
    timeout: int,
    token_env: str = "GITHUB_TOKEN",
    max_bytes: int = 1_500_000,
    accept: str | None = None,
) -> HttpResult:
    headers = request_headers(token_env)
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes + 1)
            content_type = resp.headers.get("content-type", "")
            charset = "utf-8"
            match = re.search(r"charset=([^;\s]+)", content_type, re.I)
            if match:
                charset = match.group(1).strip('"')
            body = raw[:max_bytes].decode(charset, errors="replace")
            return HttpResult(
                url=url,
                status=resp.status,
                final_url=resp.geturl(),
                content_type=content_type,
                body=body,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read(8192).decode("utf-8", errors="replace")
        except Exception:
            pass
        return HttpResult(
            url=url,
            status=exc.code,
            final_url=url,
            content_type=exc.headers.get("content-type", "") if exc.headers else "",
            body=body,
            error=f"HTTP {exc.code}: {exc.reason}",
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as exc:
        return HttpResult(
            url=url,
            final_url=url,
            error=str(exc),
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )


def fetch_json(url: str, *, timeout: int, token_env: str) -> tuple[dict[str, Any] | None, str]:
    result = http_get(
        url,
        timeout=timeout,
        token_env=token_env,
        accept="application/vnd.github+json, application/json",
    )
    if not result.ok:
        return None, result.error or f"HTTP {result.status}"
    try:
        value = json.loads(result.body)
    except json.JSONDecodeError as exc:
        return None, f"JSON parse error: {exc}"
    if isinstance(value, dict):
        return value, ""
    return None, "JSON root was not an object"


def markdown_links(markdown: str) -> list[str]:
    links = re.findall(r"\[[^\]]+\]\((https?://[^)\s]+)", markdown)
    links.extend(re.findall(r"(?<!\()https?://[^\s)>\"]+", markdown))
    cleaned = [link.rstrip(".,;:") for link in links]
    return unique(cleaned)


def looks_docs_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if host in NON_DOC_SITE_HOSTS:
        return False
    if any(skip in path for skip in SKIP_PATH_HINTS):
        return False
    if host.startswith("docs."):
        return True
    return any(hint in path for hint in DOC_PATH_HINTS)


def same_origin(url_a: str, url_b: str) -> bool:
    a = urllib.parse.urlparse(url_a)
    b = urllib.parse.urlparse(url_b)
    return a.scheme == b.scheme and a.netloc.lower() == b.netloc.lower()


def normalize_href(base_url: str, href: str) -> str | None:
    if not href or href.startswith(("mailto:", "tel:", "javascript:")):
        return None
    url = urllib.parse.urljoin(base_url, href)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    clean = parsed._replace(fragment="", query="").geturl()
    if any(clean.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".zip")):
        return None
    return clean.rstrip("/")


def detect_frameworks(html: str) -> list[str]:
    lower = html.lower()
    frameworks: list[str] = []
    for name, hints in DOC_FRAMEWORK_HINTS.items():
        if any(hint.lower() in lower for hint in hints):
            frameworks.append(name)
    return frameworks


def is_valid_llms_body(body: str) -> bool:
    stripped = body.lstrip()
    lower_start = stripped[:500].lower()
    if not stripped or "<html" in lower_start or "<!doctype" in lower_start:
        return False
    link_count = len(re.findall(r"\[[^\]]+\]\([^)]+\)", body))
    return stripped.startswith("#") or link_count >= 2 or "llms-full" in lower_start


def is_valid_llms_result(result: HttpResult) -> bool:
    if not result.ok:
        return False
    content_type = result.content_type.lower()
    if "html" in content_type or "json" in content_type or "xml" in content_type:
        return False
    return is_valid_llms_body(result.body)


def llms_candidates_for_base(url: str) -> list[str]:
    parsed = urllib.parse.urlparse(with_scheme(url))
    if not parsed.netloc:
        return []
    origin = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [
        f"{origin}/llms.txt",
        f"{origin}/llms-full.txt",
    ]
    path = parsed.path or "/"
    directory = path if path.endswith("/") else path.rsplit("/", 1)[0] + "/"
    directory = "/" + directory.strip("/") if directory.strip("/") else ""
    if directory:
        candidates.extend(
            [
                f"{origin}{directory}/llms.txt",
                f"{origin}{directory}/llms-full.txt",
            ]
        )
    if "/docs" in path.lower():
        candidates.extend([f"{origin}/docs/llms.txt", f"{origin}/docs/llms-full.txt"])
    return unique(candidates)


def discover_sitemap_urls(base_url: str, *, timeout: int, token_env: str, limit: int) -> list[str]:
    parsed = urllib.parse.urlparse(base_url)
    if not parsed.netloc:
        return []
    origin = f"{parsed.scheme}://{parsed.netloc}"
    sitemap_urls = [f"{origin}/sitemap.xml"]
    robots = http_get(f"{origin}/robots.txt", timeout=timeout, token_env=token_env, max_bytes=200_000)
    if robots.ok:
        for line in robots.body.splitlines():
            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                sitemap_urls.append(normalize_href(origin, sitemap_url) or sitemap_url)
    found: list[str] = []
    nested: list[str] = []
    for sitemap in unique(sitemap_urls):
        result = http_get(sitemap, timeout=timeout, token_env=token_env, max_bytes=1_500_000)
        if not result.ok:
            continue
        locs = re.findall(r"<loc>\s*([^<]+)\s*</loc>", result.body, flags=re.I)
        for loc in locs:
            loc = loc.strip()
            loc = normalize_href(origin, loc) or loc
            if loc.endswith(".xml") and len(nested) < 8:
                nested.append(loc)
            elif same_origin(origin, loc) and looks_docs_url(loc):
                found.append(normalize_href(origin, loc) or loc)
    for sitemap in unique(nested):
        if len(found) >= limit:
            break
        result = http_get(sitemap, timeout=timeout, token_env=token_env, max_bytes=1_500_000)
        if not result.ok:
            continue
        for loc in re.findall(r"<loc>\s*([^<]+)\s*</loc>", result.body, flags=re.I):
            loc = loc.strip()
            if same_origin(origin, loc) and looks_docs_url(loc):
                found.append(normalize_href(origin, loc) or loc)
                if len(found) >= limit:
                    break
    return unique(found)[:limit]


def page_tuple_for_url(url: str, used: set[str]) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(url)
    parts = [slugify(p) for p in parsed.path.split("/") if p]
    while parts and (parts[0] in DOC_PREFIXES or re.fullmatch(r"v?\d+(\.\d+)*", parts[0])):
        parts.pop(0)
    if not parts:
        subdir = "."
        filename = "overview.md"
    elif len(parts) == 1:
        subdir = "."
        filename = f"{parts[0]}.md"
    else:
        subdir = parts[0]
        filename = f"{parts[-1]}.md"
    key = f"{subdir}/{filename}"
    if key in used:
        stem = filename[:-3]
        i = 2
        while f"{subdir}/{stem}-{i}.md" in used:
            i += 1
        filename = f"{stem}-{i}.md"
    used.add(f"{subdir}/{filename}")
    return subdir, filename


def probe_docs_site(url: str, *, timeout: int, token_env: str, max_links: int) -> dict[str, Any]:
    result = http_get(url, timeout=timeout, token_env=token_env, max_bytes=1_500_000)
    info: dict[str, Any] = {
        "url": url,
        "status": result.status,
        "final_url": result.final_url,
        "content_type": result.content_type,
        "error": result.error,
        "text_len": 0,
        "title": "",
        "frameworks": [],
        "same_origin_links": [],
        "docs_links": [],
        "sitemap_links": [],
        "suggested_pages": [],
        "score": 0,
        "js_risk": "unknown",
    }
    if not result.ok or "html" not in result.content_type.lower():
        return info
    parser = SimplePageParser()
    try:
        parser.feed(result.body)
    except Exception:
        pass
    links: list[str] = []
    for href in parser.links:
        normalized = normalize_href(result.final_url or url, href)
        if normalized and same_origin(result.final_url or url, normalized):
            links.append(normalized)
    links = unique(links)
    docs_links = [link for link in links if looks_docs_url(link)]
    sitemap_links = discover_sitemap_urls(
        result.final_url or url,
        timeout=timeout,
        token_env=token_env,
        limit=max_links,
    )
    page_urls = unique([result.final_url or url] + sitemap_links + docs_links)[:max_links]
    used: set[str] = set()
    suggested_pages = []
    for page_url in page_urls:
        subdir, filename = page_tuple_for_url(page_url, used)
        suggested_pages.append({"url": page_url, "subdir": subdir, "filename": filename})
    text_len = parser.text_len
    frameworks = detect_frameworks(result.body)
    js_risk = "low"
    if text_len < 500 and re.search(r'id=["\'](?:root|app|__next)["\']', result.body):
        js_risk = "high"
    elif text_len < 1000:
        js_risk = "medium"
    score = 0
    if text_len >= 1000:
        score += 25
    if len(docs_links) >= 5:
        score += 25
    if sitemap_links:
        score += 25
    if frameworks:
        score += 15
    if js_risk == "high":
        score -= 30
    info.update(
        {
            "text_len": text_len,
            "title": parser.title,
            "frameworks": frameworks,
            "same_origin_links": links[:max_links],
            "docs_links": docs_links[:max_links],
            "sitemap_links": sitemap_links[:max_links],
            "suggested_pages": suggested_pages[:max_links],
            "score": max(score, 0),
            "js_risk": js_risk,
        }
    )
    return info


def github_search(name: str, *, timeout: int, token_env: str, limit: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"q": f"{name} in:name,description", "per_page": str(limit)})
    data, error = fetch_json(f"https://api.github.com/search/repositories?{query}", timeout=timeout, token_env=token_env)
    if error or not data:
        return [{"error": error or "GitHub search failed"}]
    items = data.get("items", [])
    results: list[dict[str, Any]] = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "full_name": item.get("full_name"),
                "html_url": item.get("html_url"),
                "description": item.get("description"),
                "homepage": item.get("homepage"),
                "language": item.get("language"),
                "stargazers_count": item.get("stargazers_count"),
                "topics": item.get("topics", []),
            }
        )
    return results


def raw_github_url(owner: str, repo: str, branch: str, path: str) -> str:
    quoted = "/".join(urllib.parse.quote(part) for part in path.split("/"))
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{urllib.parse.quote(branch)}/{quoted}"


def git_output(root: str, *args: str, timeout: int = 15) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", root, *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()


def git_remote_has_branch(url: str, branch: str, *, timeout: int) -> bool:
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", url, branch],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return bool(result.stdout.strip())


def clone_github_repo(owner: str, repo: str, *, timeout: int) -> tuple[str, str]:
    temp_dir = tempfile.mkdtemp(prefix="skillgen-auto-github-")
    clone_dir = os.path.join(temp_dir, slugify(f"{owner}-{repo}", "repo"))
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--no-tags", repo_url(owner, repo), clone_dir],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    return clone_dir, temp_dir


def read_local_text(root: str, rel: str, max_bytes: int) -> str:
    path = os.path.join(root, rel)
    try:
        with open(path, "rb") as handle:
            raw = handle.read(max_bytes)
    except OSError:
        return ""
    return raw.decode("utf-8", errors="replace")


def local_readme_links(root: str, paths: list[str]) -> list[str]:
    readme = next((path for path in paths if path.lower() in {"readme.md", "readme.mdx", "readme.rst"}), "")
    if not readme:
        return []
    return [link for link in markdown_links(read_local_text(root, readme, 400_000)) if looks_docs_url(link) or "pkg.go.dev" in link][:80]


def local_homepage(root: str) -> str:
    package_json = os.path.join(root, "package.json")
    try:
        with open(package_json, "r", encoding="utf-8", errors="replace") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return ""
    homepage = data.get("homepage") if isinstance(data, dict) else ""
    return homepage if isinstance(homepage, str) and homepage.startswith(("http://", "https://")) else ""


def analyze_github_repo(owner: str, repo: str, *, timeout: int, token_env: str) -> dict[str, Any]:
    api_base = f"https://api.github.com/repos/{owner}/{repo}"
    data, error = fetch_json(api_base, timeout=timeout, token_env=token_env)
    info: dict[str, Any] = {
        "repo": f"{owner}/{repo}",
        "url": repo_url(owner, repo),
        "error": error,
        "analysis_method": "github-api",
        "default_branch": "",
        "description": "",
        "homepage": "",
        "language": "",
        "topics": [],
        "stars": None,
        "tree_error": "",
        "tree_truncated": False,
        "llms_paths": [],
        "docs_files": [],
        "examples": [],
        "tests": [],
        "frameworks": [],
        "root_files": [],
        "go_mod_paths": [],
        "go_modules": [],
        "package_managers": [],
        "raw_llms_urls": [],
        "readme_links": [],
        "github_pages": {},
        "gh_pages_branch": False,
        "score": 0,
    }
    if not data:
        return info
    branch = data.get("default_branch") or "main"
    info.update(
        {
            "error": "",
            "default_branch": branch,
            "description": data.get("description") or "",
            "homepage": data.get("homepage") or "",
            "language": data.get("language") or "",
            "topics": data.get("topics") or [],
            "stars": data.get("stargazers_count"),
        }
    )
    tree, tree_error = fetch_json(f"{api_base}/git/trees/{urllib.parse.quote(branch)}?recursive=1", timeout=timeout, token_env=token_env)
    paths: list[str] = []
    if tree:
        info["tree_truncated"] = bool(tree.get("truncated"))
        for item in tree.get("tree", []):
            if isinstance(item, dict) and item.get("type") == "blob" and item.get("path"):
                paths.append(item["path"])
    else:
        info["tree_error"] = tree_error
    lower_paths = [(path, path.lower()) for path in paths]
    info["root_files"] = sorted([path for path in paths if "/" not in path])[:80]
    info["llms_paths"] = [path for path, lower in lower_paths if lower.endswith(("llms.txt", "llms-full.txt"))][:40]
    info["docs_files"] = [
        path
        for path, lower in lower_paths
        if lower.endswith((".md", ".mdx", ".rst"))
        and ("/" not in lower or any(hint in lower for hint in DOC_PATH_HINTS) or lower.startswith(("readme", "contributing")))
    ][:120]
    info["examples"] = [path for path, lower in lower_paths if any(part in lower for part in ("example", "examples", "sample", "samples", "cookbook"))][:80]
    info["tests"] = [path for path, lower in lower_paths if re.search(r"(^|/)(test|tests|spec|specs)(/|$)", lower) or lower.endswith(("_test.go", ".test.ts", ".spec.ts", ".test.js", ".spec.js"))][:80]
    info["go_mod_paths"] = [path for path, lower in lower_paths if lower.endswith("go.mod")][:20]
    package_files = [path for path, lower in lower_paths if lower.endswith(("package.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "requirements.txt", "pyproject.toml", "cargo.toml", "mkdocs.yml", "book.toml"))]
    info["package_managers"] = package_files[:60]
    framework_files = {
        "docusaurus": ("docusaurus.config", "sidebars."),
        "vitepress": (".vitepress/config",),
        "nextra": ("theme.config",),
        "mintlify": ("mint.json", "docs.json"),
        "astro-starlight": ("astro.config", "src/content/docs"),
        "mkdocs": ("mkdocs.yml",),
        "mdbook": ("book.toml",),
        "sphinx": ("conf.py",),
    }
    frameworks: list[str] = []
    for name, hints in framework_files.items():
        if any(any(hint in lower for hint in hints) for _, lower in lower_paths):
            frameworks.append(name)
    info["frameworks"] = frameworks
    info["raw_llms_urls"] = [raw_github_url(owner, repo, branch, path) for path in info["llms_paths"]]
    modules: list[str] = []
    for path in info["go_mod_paths"][:5]:
        raw = http_get(raw_github_url(owner, repo, branch, path), timeout=timeout, token_env=token_env, max_bytes=200_000)
        if raw.ok:
            match = re.search(r"(?m)^\s*module\s+(\S+)", raw.body)
            if match:
                modules.append(match.group(1))
    info["go_modules"] = unique(modules)
    readme_path = next((path for path in paths if path.lower() in {"readme.md", "readme.mdx", "readme.rst"}), "")
    if readme_path:
        raw = http_get(raw_github_url(owner, repo, branch, readme_path), timeout=timeout, token_env=token_env, max_bytes=400_000)
        if raw.ok:
            info["readme_links"] = [link for link in markdown_links(raw.body) if looks_docs_url(link) or "pkg.go.dev" in link][:80]
    gh_pages, _ = fetch_json(f"{api_base}/branches/gh-pages", timeout=timeout, token_env=token_env)
    info["gh_pages_branch"] = bool(gh_pages)
    pages, pages_error = fetch_json(f"{api_base}/pages", timeout=timeout, token_env=token_env)
    if pages:
        info["github_pages"] = {
            "html_url": pages.get("html_url"),
            "cname": pages.get("cname"),
            "status": pages.get("status"),
        }
    elif pages_error and "404" not in pages_error:
        info["github_pages"] = {"error": pages_error}
    score = 0
    if info["llms_paths"]:
        score += 40
    if info["docs_files"]:
        score += 25
    if info["examples"]:
        score += 10
    if info["tests"]:
        score += 10
    if info["frameworks"]:
        score += 15
    if info["go_modules"]:
        score += 10
    info["score"] = score
    return info


def analyze_local_repo(path: str) -> dict[str, Any]:
    root = os.path.abspath(os.path.expanduser(path))
    info: dict[str, Any] = {
        "path": root,
        "error": "",
        "llms_paths": [],
        "docs_files": [],
        "examples": [],
        "tests": [],
        "frameworks": [],
        "root_files": [],
        "go_mod_paths": [],
        "go_modules": [],
        "package_managers": [],
        "readme_links": [],
        "homepage": "",
        "score": 0,
    }
    if not os.path.isdir(root):
        info["error"] = "not a directory"
        return info
    paths: list[str] = []
    ignored_dirs = {
        ".git",
        "node_modules",
        "vendor",
        "dist",
        "build",
        "target",
        ".next",
        ".cache",
        "__pycache__",
    }
    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in ignored_dirs and not name.startswith(".tox")]
        rel_dir = os.path.relpath(current, root)
        if rel_dir.count(os.sep) > 5:
            dirs[:] = []
        for filename in files:
            rel = filename if rel_dir == "." else os.path.join(rel_dir, filename)
            paths.append(rel.replace(os.sep, "/"))
            if len(paths) >= 5000:
                break
        if len(paths) >= 5000:
            break
    lower_paths = [(item, item.lower()) for item in paths]
    info["root_files"] = sorted([item for item in paths if "/" not in item])[:80]
    info["llms_paths"] = [item for item, lower in lower_paths if lower.endswith(("llms.txt", "llms-full.txt"))][:40]
    info["docs_files"] = [
        item
        for item, lower in lower_paths
        if lower.endswith((".md", ".mdx", ".rst"))
        and ("/" not in lower or any(hint in lower for hint in DOC_PATH_HINTS) or lower.startswith(("readme", "contributing")))
    ][:120]
    info["examples"] = [item for item, lower in lower_paths if any(part in lower for part in ("example", "examples", "sample", "samples", "cookbook"))][:80]
    info["tests"] = [item for item, lower in lower_paths if re.search(r"(^|/)(test|tests|spec|specs)(/|$)", lower) or lower.endswith(("_test.go", ".test.ts", ".spec.ts", ".test.js", ".spec.js"))][:80]
    info["go_mod_paths"] = [item for item, lower in lower_paths if lower.endswith("go.mod")][:20]
    info["package_managers"] = [
        item
        for item, lower in lower_paths
        if lower.endswith(("package.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "requirements.txt", "pyproject.toml", "cargo.toml", "mkdocs.yml", "book.toml"))
    ][:60]
    framework_files = {
        "docusaurus": ("docusaurus.config", "sidebars."),
        "vitepress": (".vitepress/config",),
        "nextra": ("theme.config",),
        "mintlify": ("mint.json", "docs.json"),
        "astro-starlight": ("astro.config", "src/content/docs"),
        "mkdocs": ("mkdocs.yml",),
        "mdbook": ("book.toml",),
        "sphinx": ("conf.py",),
    }
    frameworks: list[str] = []
    for name, hints in framework_files.items():
        if any(any(hint in lower for hint in hints) for _, lower in lower_paths):
            frameworks.append(name)
    info["frameworks"] = frameworks
    info["readme_links"] = local_readme_links(root, paths)
    info["homepage"] = local_homepage(root)
    modules: list[str] = []
    for rel in info["go_mod_paths"][:5]:
        try:
            with open(os.path.join(root, rel), "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read(200_000)
        except OSError:
            continue
        match = re.search(r"(?m)^\s*module\s+(\S+)", text)
        if match:
            modules.append(match.group(1))
    info["go_modules"] = unique(modules)
    score = 0
    if info["llms_paths"]:
        score += 40
    if info["docs_files"]:
        score += 25
    if info["examples"]:
        score += 10
    if info["tests"]:
        score += 10
    if info["frameworks"]:
        score += 15
    if info["go_modules"]:
        score += 10
    info["score"] = score
    return info


def empty_github_repo_info(owner: str, repo: str, error: str = "") -> dict[str, Any]:
    return {
        "repo": f"{owner}/{repo}",
        "url": repo_url(owner, repo),
        "error": error,
        "analysis_method": "none",
        "default_branch": "",
        "description": "",
        "homepage": "",
        "language": "",
        "topics": [],
        "stars": None,
        "tree_error": "",
        "tree_truncated": False,
        "llms_paths": [],
        "docs_files": [],
        "examples": [],
        "tests": [],
        "frameworks": [],
        "root_files": [],
        "go_mod_paths": [],
        "go_modules": [],
        "package_managers": [],
        "raw_llms_urls": [],
        "readme_links": [],
        "github_pages": {},
        "gh_pages_branch": False,
        "score": 0,
    }


def analyze_github_repo_via_git(owner: str, repo: str, *, timeout: int) -> dict[str, Any]:
    url = repo_url(owner, repo)
    temp_dir = ""
    try:
        clone_dir, temp_dir = clone_github_repo(owner, repo, timeout=timeout)
        local = analyze_local_repo(clone_dir)
        commit = git_output(clone_dir, "rev-parse", "HEAD", timeout=10)
        branch = git_output(clone_dir, "branch", "--show-current", timeout=10) or commit or "HEAD"
        info = empty_github_repo_info(owner, repo)
        info.update(
            {
                "analysis_method": "git-clone",
                "default_branch": branch,
                "homepage": local.get("homepage", ""),
                "llms_paths": local.get("llms_paths", []),
                "docs_files": local.get("docs_files", []),
                "examples": local.get("examples", []),
                "tests": local.get("tests", []),
                "frameworks": local.get("frameworks", []),
                "root_files": local.get("root_files", []),
                "go_mod_paths": local.get("go_mod_paths", []),
                "go_modules": local.get("go_modules", []),
                "package_managers": local.get("package_managers", []),
                "readme_links": local.get("readme_links", []),
                "score": local.get("score", 0),
                "temporary_clone": "shallow clone removed after analysis",
            }
        )
        raw_ref = commit or branch
        info["raw_llms_urls"] = [raw_github_url(owner, repo, raw_ref, path) for path in info["llms_paths"]]
        info["gh_pages_branch"] = git_remote_has_branch(url, "gh-pages", timeout=min(timeout, 30))
        return info
    except subprocess.TimeoutExpired as exc:
        return empty_github_repo_info(owner, repo, f"git clone timed out after {exc.timeout} seconds")
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or str(exc)).strip().splitlines()
        message = detail[-1] if detail else str(exc)
        return empty_github_repo_info(owner, repo, f"git clone failed: {message}")
    except Exception as exc:
        return empty_github_repo_info(owner, repo, f"git clone failed: {exc}")
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def search_pkg_go_dev(name: str, *, timeout: int, token_env: str, limit: int) -> list[str]:
    url = f"https://pkg.go.dev/search?q={urllib.parse.quote(name)}"
    result = http_get(url, timeout=timeout, token_env=token_env, max_bytes=1_000_000)
    if not result.ok:
        return []
    parser = SimplePageParser()
    try:
        parser.feed(result.body)
    except Exception:
        pass
    packages: list[str] = []
    for href in parser.links:
        clean = href.split("?", 1)[0].strip("/")
        if not clean or clean.startswith(("search", "about", "license", "std")):
            continue
        if name.lower() not in clean.lower():
            continue
        first = clean.split("/", 1)[0]
        if "." in first or first in {"golang.org", "go.opentelemetry.io"}:
            packages.append(urllib.parse.unquote(clean))
    return unique(packages)[:limit]


def probe_go_package(path: str, *, timeout: int, token_env: str) -> dict[str, Any]:
    url = f"https://pkg.go.dev/{path}"
    result = http_get(url, timeout=timeout, token_env=token_env, max_bytes=1_000_000)
    info: dict[str, Any] = {
        "path": path,
        "url": url,
        "status": result.status,
        "error": result.error,
        "title": "",
        "valid": False,
    }
    if not result.ok:
        return info
    parser = SimplePageParser()
    try:
        parser.feed(result.body)
    except Exception:
        pass
    body_start = result.body[:4000].lower()
    not_found = "not found" in body_start and "pkg.go.dev" in body_start
    info.update({"title": parser.title, "valid": not not_found and parser.text_len > 500})
    return info


def generic_doc_guesses(name: str) -> list[str]:
    slug = slugify(name)
    if not slug or "." in slug:
        return []
    urls: list[str] = []
    for host in (f"{slug}.dev", f"{slug}.io", f"{slug}.org", f"{slug}.com"):
        urls.extend([f"https://{host}/docs", f"https://docs.{host}"])
    return urls


def normalize_inputs(args: argparse.Namespace) -> dict[str, Any]:
    raw_targets = args.target or []
    names: list[str] = []
    repos: list[str] = []
    local_paths: list[str] = []
    docs_urls: list[str] = []
    go_packages: list[str] = []
    llms_urls: list[str] = []

    def add_value(value: str) -> None:
        value = value.strip().strip("<>")
        if not value:
            return
        if value.endswith("/llms.txt") or value.endswith("/llms-full.txt"):
            llms_urls.append(with_scheme(value) if not is_url(value) else value)
            return
        pkg = pkg_from_pkg_go_dev(value) if is_url(value) else None
        if pkg:
            go_packages.append(pkg)
            return
        gh = parse_github_repo(value)
        if gh:
            owner, repo = gh
            repos.append(repo_url(owner, repo))
            if looks_like_go_import(f"github.com/{owner}/{repo}"):
                go_packages.append(f"github.com/{owner}/{repo}")
            return
        if looks_like_local_path(value):
            local_paths.append(os.path.abspath(os.path.expanduser(value)))
            return
        if is_url(value):
            docs_urls.append(value)
            return
        if looks_like_go_import(value):
            go_packages.append(value)
            gh2 = parse_github_repo(value)
            if gh2:
                repos.append(repo_url(*gh2))
            return
        names.append(value)

    for value in raw_targets:
        add_value(value)
    for value in args.github or []:
        gh = parse_github_repo(value)
        if gh:
            repos.append(repo_url(*gh))
    for value in args.docs or []:
        docs_urls.append(with_scheme(value) if not is_url(value) else value)
    for value in args.go_package or []:
        pkg = pkg_from_pkg_go_dev(value) if is_url(value) else value
        if pkg:
            go_packages.append(pkg)
    name = args.name or (names[0] if names else "")
    if not name:
        for source in go_packages + repos + docs_urls + llms_urls + local_paths:
            parsed = urllib.parse.urlparse(source)
            if parsed.scheme and parsed.netloc:
                pieces = [p for p in parsed.path.split("/") if p]
                name = pieces[-1].removesuffix(".git") if pieces else parsed.netloc.split(".")[0]
            else:
                name = os.path.basename(os.path.abspath(os.path.expanduser(source)))
            if name:
                break
    return {
        "names": unique(names),
        "name": name or "docs-target",
        "repos": unique(repos),
        "local_paths": unique(local_paths),
        "docs_urls": unique(docs_urls),
        "go_packages": unique(go_packages),
        "llms_urls": unique(llms_urls),
    }


def build_recommendation(report: dict[str, Any]) -> dict[str, Any]:
    name = report["normalized"]["name"]
    skill_slug = f"docs-{slugify(name)}"
    valid_llms = [item for item in report["llms_probes"] if item.get("valid")]
    docs_sites = sorted(report["docs_sites"], key=lambda item: item.get("score", 0), reverse=True)
    repos = sorted(report["github_repositories"], key=lambda item: item.get("score", 0), reverse=True)
    local_repos = sorted(report["local_repositories"], key=lambda item: item.get("score", 0), reverse=True)
    go_packages = [item for item in report["go_packages"] if item.get("valid")]
    route = {
        "primary": "needs-more-input",
        "confidence": "low",
        "why": [],
        "commands": [],
        "supplements": [],
        "skill_name": skill_slug,
    }
    if valid_llms:
        source = valid_llms[0]["url"]
        route.update(
            {
                "primary": "skillgen-llms-txt",
                "confidence": "high",
                "why": [f"Valid llms.txt endpoint found: {source}"],
                "commands": [
                    f"python3 .agents/skills/skillgen-llms-txt/scripts/create_skill_from_llms.py {source} --name {skill_slug}"
                ],
            }
        )
    elif local_repos and local_repos[0].get("score", 0) >= 20:
        repo = local_repos[0]
        route.update(
            {
                "primary": "skillgen-repo",
                "confidence": "medium" if repo.get("score", 0) < 60 else "high",
                "why": [
                    f"Local repository scored {repo.get('score')} with {len(repo.get('docs_files', []))} docs files, {len(repo.get('examples', []))} examples, and {len(repo.get('tests', []))} tests."
                ],
                "commands": [
                    f"python3 .agents/skills/skillgen-repo/scripts/analyze_repo.py {repo.get('path')}",
                    f"python3 .agents/skills/skillgen-repo/scripts/create_skill_from_repo.py {repo.get('path')} --name {skill_slug}",
                ],
            }
        )
    elif docs_sites and docs_sites[0].get("score", 0) >= 45:
        site = docs_sites[0]
        route.update(
            {
                "primary": "skillgen-website",
                "confidence": "medium" if site.get("score", 0) < 70 else "high",
                "why": [
                    f"Best docs site scored {site.get('score')} with {len(site.get('docs_links', []))} docs links and {len(site.get('sitemap_links', []))} sitemap links.",
                    f"JavaScript rendering risk: {site.get('js_risk')}.",
                ],
                "commands": [
                    f"mkdir -p .agents/skills/{skill_slug}/scripts .agents/skills/{skill_slug}/references\n"
                    f"cp .agents/skills/skillgen-website/scripts/scrape.py .agents/skills/{skill_slug}/scripts/scrape.py\n"
                    f"# Edit .agents/skills/{skill_slug}/scripts/scrape.py and populate PAGES from this report.\n"
                    f"cd .agents/skills/{skill_slug} && python3 scripts/scrape.py"
                ],
            }
        )
    elif repos and repos[0].get("score", 0) >= 20:
        repo = repos[0]
        route.update(
            {
                "primary": "skillgen-repo",
                "confidence": "medium" if repo.get("score", 0) < 60 else "high",
                "why": [
                    f"Best repository scored {repo.get('score')} with {len(repo.get('docs_files', []))} docs files, {len(repo.get('examples', []))} examples, and {len(repo.get('tests', []))} tests."
                ],
                "commands": [
                    f"python3 .agents/skills/skillgen-repo/scripts/analyze_repo.py {repo.get('url')}",
                    f"python3 .agents/skills/skillgen-repo/scripts/create_skill_from_repo.py {repo.get('url')} --name {skill_slug}",
                ],
            }
        )
    elif go_packages:
        pkg = go_packages[0]["path"]
        route.update(
            {
                "primary": "skillgen-go-package",
                "confidence": "medium",
                "why": [f"pkg.go.dev package page appears valid: {pkg}"],
                "commands": [
                    f"python3 .agents/skills/skillgen-go-package/scripts/create_skill_from_go_package.py {pkg} --name {skill_slug}"
                ],
            }
        )
    else:
        route["why"] = ["No high-confidence llms.txt, docs site, repository, or Go package was found."]
    if route["primary"] != "skillgen-repo" and local_repos and local_repos[0].get("score", 0) >= 20:
        route["supplements"].append(
            {
                "generator": "skillgen-repo",
                "reason": "Local repository has docs/examples/source evidence that may improve inferred guides.",
                "command": f"python3 .agents/skills/skillgen-repo/scripts/create_skill_from_repo.py {local_repos[0].get('path')} --name {skill_slug}-repo",
            }
        )
    elif route["primary"] != "skillgen-repo" and repos and repos[0].get("score", 0) >= 20:
        route["supplements"].append(
            {
                "generator": "skillgen-repo",
                "reason": "Repository has docs/examples/source evidence that may improve inferred guides.",
                "command": f"python3 .agents/skills/skillgen-repo/scripts/create_skill_from_repo.py {repos[0].get('url')} --name {skill_slug}-repo",
            }
        )
    if route["primary"] != "skillgen-go-package" and go_packages:
        route["supplements"].append(
            {
                "generator": "skillgen-go-package",
                "reason": "pkg.go.dev can add exported Go API reference and version metadata.",
                "command": f"python3 .agents/skills/skillgen-go-package/scripts/create_skill_from_go_package.py {go_packages[0]['path']} --name {skill_slug}-go",
            }
        )
    return route


def explore(args: argparse.Namespace) -> dict[str, Any]:
    normalized = normalize_inputs(args)
    report: dict[str, Any] = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "inputs": {
            "target": args.target,
            "github": args.github or [],
            "docs": args.docs or [],
            "go_package": args.go_package or [],
            "github_token_used": bool(os.environ.get(args.github_token_env)),
            "github_mode": args.github_mode,
        },
        "normalized": normalized,
        "github_search_results": [],
        "github_repositories": [],
        "local_repositories": [],
        "docs_sites": [],
        "llms_probes": [],
        "go_package_search_results": [],
        "go_packages": [],
        "recommendation": {},
    }
    names = normalized["names"]
    repos = list(normalized["repos"])
    local_paths = list(normalized["local_paths"])
    docs_urls = list(normalized["docs_urls"])
    go_packages = list(normalized["go_packages"])
    llms_urls = list(normalized["llms_urls"])

    if names and not args.no_github_search:
        for name in names[:3]:
            results = github_search(name, timeout=args.timeout, token_env=args.github_token_env, limit=args.max_github)
            report["github_search_results"].extend(results)
            for item in results:
                url = item.get("html_url") if isinstance(item, dict) else None
                if url:
                    repos.append(url)
    if names and not args.no_pkg_search:
        for name in names[:3]:
            pkgs = search_pkg_go_dev(name, timeout=args.timeout, token_env=args.github_token_env, limit=args.max_go_packages)
            report["go_package_search_results"].extend(pkgs)
            go_packages.extend(pkgs)
    for local_path in local_paths:
        local_info = analyze_local_repo(local_path)
        report["local_repositories"].append(local_info)
        if local_info.get("homepage") and looks_docs_url(local_info["homepage"]):
            docs_urls.append(local_info["homepage"])
        for link in local_info.get("readme_links", []):
            if "pkg.go.dev/" in link:
                pkg = pkg_from_pkg_go_dev(link)
                if pkg:
                    go_packages.append(pkg)
            elif looks_docs_url(link):
                docs_urls.append(link)
        for module in local_info.get("go_modules", []):
            go_packages.append(module)
    for repo_candidate in unique(repos)[: args.max_github]:
        gh = parse_github_repo(repo_candidate)
        if not gh:
            continue
        owner, repo = gh
        if args.github_mode == "none":
            repo_info = empty_github_repo_info(owner, repo, "GitHub repository inspection disabled by --github-mode none")
        elif args.github_mode == "api":
            repo_info = analyze_github_repo(owner, repo, timeout=args.timeout, token_env=args.github_token_env)
            repo_info["analysis_method"] = "github-api"
        else:
            repo_info = analyze_github_repo_via_git(owner, repo, timeout=args.git_timeout)
            if args.github_mode == "auto" and repo_info.get("error"):
                api_info = analyze_github_repo(owner, repo, timeout=args.timeout, token_env=args.github_token_env)
                api_info["analysis_method"] = "github-api-fallback"
                if not api_info.get("error"):
                    repo_info = api_info
        report["github_repositories"].append(repo_info)
        if repo_info.get("homepage") and looks_docs_url(repo_info["homepage"]):
            docs_urls.append(repo_info["homepage"])
        for link in repo_info.get("readme_links", []):
            if "pkg.go.dev/" in link:
                pkg = pkg_from_pkg_go_dev(link)
                if pkg:
                    go_packages.append(pkg)
            elif looks_docs_url(link):
                docs_urls.append(link)
        for module in repo_info.get("go_modules", []):
            go_packages.append(module)
        llms_urls.extend(repo_info.get("raw_llms_urls", []))
        pages = repo_info.get("github_pages") or {}
        if pages.get("html_url"):
            docs_urls.append(pages["html_url"])
        elif repo_info.get("gh_pages_branch"):
            docs_urls.append(f"https://{owner}.github.io/{repo}/")
    for name in names[:2]:
        docs_urls.extend(generic_doc_guesses(name))
    for base in unique(docs_urls):
        llms_urls.extend(llms_candidates_for_base(base))
    for url in unique(llms_urls)[: args.max_llms]:
        result = http_get(url, timeout=args.timeout, token_env=args.github_token_env, max_bytes=800_000)
        report["llms_probes"].append(
            {
                "url": url,
                "status": result.status,
                "content_type": result.content_type,
                "error": result.error,
                "valid": is_valid_llms_result(result),
                "bytes": len(result.body.encode("utf-8")),
            }
        )
    for url in unique(docs_urls)[: args.max_docs_sites]:
        report["docs_sites"].append(
            probe_docs_site(url, timeout=args.timeout, token_env=args.github_token_env, max_links=args.max_links)
        )
    for pkg in unique(go_packages)[: args.max_go_packages]:
        report["go_packages"].append(probe_go_package(pkg, timeout=args.timeout, token_env=args.github_token_env))
    report["recommendation"] = build_recommendation(report)
    return report


def format_list(values: list[Any], *, limit: int = 20) -> str:
    if not values:
        return "- None\n"
    lines: list[str] = []
    for value in values[:limit]:
        if isinstance(value, str):
            lines.append(f"- {value}")
        else:
            lines.append(f"- `{json.dumps(value, ensure_ascii=False)}`")
    if len(values) > limit:
        lines.append(f"- ... {len(values) - limit} more")
    return "\n".join(lines) + "\n"


def format_markdown(report: dict[str, Any]) -> str:
    rec = report["recommendation"]
    lines: list[str] = []
    lines.append("# Skillgen Auto Exploration Report\n")
    lines.append(f"> Generated: {report['generated_at']}\n")
    lines.append("## Recommended route\n")
    lines.append(f"- Primary: `{rec['primary']}`")
    lines.append(f"- Confidence: `{rec['confidence']}`")
    lines.append(f"- Suggested skill name: `{rec['skill_name']}`")
    lines.append("- Why:")
    for why in rec.get("why", []):
        lines.append(f"  - {why}")
    lines.append("\n### Suggested next commands\n")
    lines.extend(f"```bash\n{command}\n```\n" for command in rec.get("commands", []))
    if rec.get("supplements"):
        lines.append("### Optional supplements\n")
        for item in rec["supplements"]:
            lines.append(f"- `{item['generator']}`: {item['reason']}")
            lines.append(f"```bash\n{item['command']}\n```\n")
        lines.append(
            "If you create multiple `docs-*` skills for this target, edit every generated "
            "`SKILL.md` so the skills link to each other and explain which source each one covers."
        )
        lines.append("")
    lines.append("## Normalized inputs\n")
    lines.append("```json")
    lines.append(json.dumps(report["normalized"], indent=2, ensure_ascii=False))
    lines.append("```\n")
    valid_llms = [item for item in report["llms_probes"] if item.get("valid")]
    lines.append("## Valid llms.txt endpoints\n")
    lines.append(format_list([item["url"] for item in valid_llms]))
    lines.append("## Documentation sites\n")
    if not report["docs_sites"]:
        lines.append("- None\n")
    for site in sorted(report["docs_sites"], key=lambda item: item.get("score", 0), reverse=True)[:8]:
        lines.append(f"### {site.get('url')}")
        lines.append(f"- Status: `{site.get('status')}`")
        lines.append(f"- Score: `{site.get('score')}`")
        lines.append(f"- Title: {site.get('title') or 'unknown'}")
        lines.append(f"- Frameworks: {', '.join(site.get('frameworks') or []) or 'none detected'}")
        lines.append(f"- Text length: `{site.get('text_len')}`")
        lines.append(f"- JavaScript risk: `{site.get('js_risk')}`")
        lines.append(f"- Docs links: `{len(site.get('docs_links') or [])}`")
        lines.append(f"- Sitemap links: `{len(site.get('sitemap_links') or [])}`")
        suggested = site.get("suggested_pages") or []
        if suggested:
            lines.append("\nSuggested `PAGES` entries:")
            lines.append("```python")
            for page in suggested[:30]:
                lines.append(f'("{page["url"]}", "{page["subdir"]}", "{page["filename"]}"),')
            if len(suggested) > 30:
                lines.append(f"# ... {len(suggested) - 30} more")
            lines.append("```\n")
    lines.append("## GitHub repositories\n")
    if not report["github_repositories"]:
        lines.append("- None\n")
    for repo in report["github_repositories"][:8]:
        lines.append(f"### {repo.get('repo')}")
        lines.append(f"- Analysis method: `{repo.get('analysis_method') or 'unknown'}`")
        if repo.get("error"):
            lines.append(f"- Error: {repo.get('error')}")
            continue
        lines.append(f"- URL: {repo.get('url')}")
        lines.append(f"- Score: `{repo.get('score')}`")
        lines.append(f"- Description: {repo.get('description') or 'none'}")
        lines.append(f"- Homepage: {repo.get('homepage') or 'none'}")
        lines.append(f"- Default branch: `{repo.get('default_branch')}`")
        lines.append(f"- Frameworks: {', '.join(repo.get('frameworks') or []) or 'none detected'}")
        lines.append(f"- llms paths: `{len(repo.get('llms_paths') or [])}`")
        lines.append(f"- docs files: `{len(repo.get('docs_files') or [])}`")
        lines.append(f"- examples: `{len(repo.get('examples') or [])}`")
        lines.append(f"- tests: `{len(repo.get('tests') or [])}`")
        lines.append(f"- Go modules: {', '.join(repo.get('go_modules') or []) or 'none'}")
        if repo.get("docs_files"):
            lines.append("Top docs files:")
            lines.append(format_list(repo["docs_files"], limit=10).rstrip())
        lines.append("")
    lines.append("## Local repositories\n")
    if not report["local_repositories"]:
        lines.append("- None\n")
    for repo in report["local_repositories"][:8]:
        lines.append(f"### {repo.get('path')}")
        if repo.get("error"):
            lines.append(f"- Error: {repo.get('error')}")
            continue
        lines.append(f"- Score: `{repo.get('score')}`")
        lines.append(f"- Frameworks: {', '.join(repo.get('frameworks') or []) or 'none detected'}")
        lines.append(f"- llms paths: `{len(repo.get('llms_paths') or [])}`")
        lines.append(f"- docs files: `{len(repo.get('docs_files') or [])}`")
        lines.append(f"- examples: `{len(repo.get('examples') or [])}`")
        lines.append(f"- tests: `{len(repo.get('tests') or [])}`")
        lines.append(f"- Go modules: {', '.join(repo.get('go_modules') or []) or 'none'}")
        if repo.get("docs_files"):
            lines.append("Top docs files:")
            lines.append(format_list(repo["docs_files"], limit=10).rstrip())
        lines.append("")
    lines.append("## Go packages\n")
    valid_go = [pkg for pkg in report["go_packages"] if pkg.get("valid")]
    if not report["go_packages"]:
        lines.append("- None\n")
    for pkg in report["go_packages"][:12]:
        lines.append(f"- `{pkg.get('path')}` status=`{pkg.get('status')}` valid=`{pkg.get('valid')}` title={pkg.get('title') or 'unknown'}")
    lines.append("\n## GitHub search results\n")
    lines.append(format_list(report["github_search_results"], limit=12))
    if valid_go:
        lines.append("## Valid pkg.go.dev package URLs\n")
        lines.append(format_list([pkg["url"] for pkg in valid_go], limit=20))
    lines.append("## Notes\n")
    lines.append("- Exploration does not install dependencies, build docs, or execute project code.")
    lines.append("- Explicit GitHub repositories are shallow-cloned by default for local file analysis, then the temporary clone is removed.")
    lines.append("- GitHub REST API is only used for bare-name GitHub search or when `--github-mode api/auto` is selected.")
    lines.append("- If the primary route needs a docs build or dependency install, ask the user before running it.")
    lines.append("- If several unrelated official-looking targets appear, ask the user which one is intended.\n")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="*", help="Target name, URL, GitHub repo, Go import path, or pkg.go.dev URL.")
    parser.add_argument("--name", help="Override the generated docs skill base name.")
    parser.add_argument("--github", action="append", help="Explicit GitHub repository URL. Repeatable.")
    parser.add_argument("--docs", action="append", help="Explicit docs site URL. Repeatable.")
    parser.add_argument("--go-package", action="append", help="Explicit Go import path or pkg.go.dev URL. Repeatable.")
    parser.add_argument("--output", help="Write the report to this path.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds.")
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN", help="Environment variable for GitHub API token.")
    parser.add_argument(
        "--github-mode",
        choices=("git", "api", "auto", "none"),
        default="git",
        help=(
            "How to inspect explicit GitHub repositories: git=shallow clone and local scan "
            "(default), api=GitHub REST API, auto=git then API fallback, none=skip repo inspection."
        ),
    )
    parser.add_argument("--git-timeout", type=int, default=90, help="Timeout in seconds for shallow Git clone operations.")
    parser.add_argument("--max-github", type=int, default=8, help="Maximum repositories to inspect.")
    parser.add_argument("--max-docs-sites", type=int, default=10, help="Maximum docs sites to probe.")
    parser.add_argument("--max-links", type=int, default=80, help="Maximum docs links/pages to keep per site.")
    parser.add_argument("--max-llms", type=int, default=40, help="Maximum llms endpoints to probe.")
    parser.add_argument("--max-go-packages", type=int, default=10, help="Maximum Go packages to probe.")
    parser.add_argument("--no-github-search", action="store_true", help="Skip GitHub search for bare names.")
    parser.add_argument("--no-pkg-search", action="store_true", help="Skip pkg.go.dev search for bare names.")
    args = parser.parse_args(argv)
    if not args.target and not args.github and not args.docs and not args.go_package:
        parser.error("provide a target or at least one --github/--docs/--go-package hint")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    report = explore(args)
    rendered = json.dumps(report, indent=2, ensure_ascii=False) if args.json else format_markdown(report)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            if not rendered.endswith("\n"):
                handle.write("\n")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
