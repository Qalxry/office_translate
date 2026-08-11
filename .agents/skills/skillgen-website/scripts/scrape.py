#!/usr/bin/env python3
"""
Generic docs website scraper: fetch HTML pages and convert to Markdown.

Usage:
    1. Edit the PAGES list below with your URLs and categories.
    2. If needed, adjust CONTENT_SELECTOR for the target site.
    3. Run:  python3 scripts/scrape.py
    4. To regenerate INDEX.md only:  python3 scripts/scrape.py --index

Requirements:
    pip3 install beautifulsoup4 html2text

How it works:
    - Fetches each URL with plain urllib (no JS rendering).
    - Finds the main content area by CSS selector.
    - Strips decorative elements (SVGs, anchor icons).
    - Converts HTML to Markdown via html2text.
    - Saves to references/<category>/<filename>.md.
    - Generates a centralized references/INDEX.md.
"""

import os
import re
import sys
import time
import urllib.request
import urllib.error
from bs4 import BeautifulSoup
import html2text

# ──────────────────────────────────────────────────────────────────────
# CONFIGURATION — Edit these for your target docs site
# ──────────────────────────────────────────────────────────────────────

# CSS selector for the main content area on the target site.
# Common selectors for popular doc frameworks:
#   Starlight/Astro:      ".sl-markdown-content"
#   Docusaurus (v2/v3):   ".theme-doc-markdown, article"
#   GitBook:              ".page-body, main"
#   ReadTheDocs/Sphinx:   ".document, .section"
#   mdBook:               "main, .content"
#   Custom:               "main, article"
#   Fallback:             "main, article, body"
CONTENT_SELECTOR = ".sl-markdown-content, main, article"

# Delay between requests (seconds) — be polite to the server
REQUEST_DELAY = 0.3

# ──────────────────────────────────────────────────────────────────────
# PAGES LIST — Each entry: (url, category_subdir, filename.md)
# Use "." for category = top-level (no subdirectory).
# ──────────────────────────────────────────────────────────────────────

PAGES = [
    # Example: Top-level pages
    # ("https://example.com/docs/intro/",     ".",  "introduction.md"),
    # ("https://example.com/docs/overview/",  ".",  "overview.md"),

    # Example: Grouped by language/concept
    # ("https://example.com/docs/go/setup/",     "go",  "getting-started.md"),
    # ("https://example.com/docs/go/errors/",    "go",  "errors.md"),
    # ("https://example.com/docs/web/setup/",    "web", "getting-started.md"),
]

# ──────────────────────────────────────────────────────────────────────
# END OF CONFIGURATION
# ──────────────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFS_DIR = os.path.join(BASE_DIR, "references")


def clean_markdown(md: str, url: str, title: str) -> str:
    """Post-process html2text output into clean, readable Markdown."""
    # Remove "Section titled" anchor-link artifacts (Starlight-specific)
    md = re.sub(r'^Section titled .*$\n', '', md, flags=re.MULTILINE)
    # Remove empty anchor links like [](#section-name)
    md = re.sub(r'\[\]\(#[^)]*\)\s*', '', md)
    # Remove "---" that leaks from decomposed SVGs
    md = re.sub(r'\n---\n', '\n', md)
    # Trim trailing whitespace per line
    lines = [line.rstrip() for line in md.split('\n')]
    md = '\n'.join(lines)
    # Collapse excessive blank lines
    md = re.sub(r'\n{4,}', '\n\n\n', md)

    # Build header with title and source URL
    header = f"# {title}\n\n"
    header += f"> Source: [{url}]({url})\n\n"

    # Remove duplicate h1 that html2text may have included
    md = re.sub(r'^# .+\n?', '', md, count=1)
    md = md.lstrip('\n')

    return header + md.strip() + '\n'


def fetch_page(url: str) -> str:
    """Fetch HTML content from a URL."""
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (compatible; DocsScraper/1.0)'},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        raise Exception(f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise Exception(f"URL Error: {e.reason}")


def extract_title(soup: BeautifulSoup) -> str:
    """Extract page title from h1."""
    h1 = soup.select_one('h1')
    return h1.get_text(strip=True) if h1 else "Untitled"


def find_main_content(soup: BeautifulSoup) -> BeautifulSoup | None:
    """Find the main content area using configured CSS selectors."""
    for selector in CONTENT_SELECTOR.split(","):
        selector = selector.strip()
        main = soup.select_one(selector)
        if main:
            return main
    return None


def convert_page(url: str) -> str:
    """Fetch, parse, and convert a single page to Markdown."""
    html = fetch_page(url)
    soup = BeautifulSoup(html, 'html.parser')
    title = extract_title(soup)

    main = find_main_content(soup)
    if not main:
        raise Exception(f"Could not find content with selectors: {CONTENT_SELECTOR}")

    # Strip decorative elements that don't carry content
    for selector in ['.sl-anchor-icon', '.sr-only', '.anchor-icon', 'svg']:
        for el in main.select(selector):
            el.decompose()

    # Configure html2text
    h = html2text.HTML2Text()
    h.body_width = 0
    h.ignore_links = False
    h.ignore_images = False
    h.ignore_tables = False
    h.escape_snob = False
    h.images_to_alt = True
    h.emphasis_mark = '*'
    h.strong_mark = '**'

    md = h.handle(str(main))
    return clean_markdown(md, url, title)


def rebuild_index():
    """Rebuild a single centralized INDEX.md from PAGES."""
    groups: dict[str, list[tuple[str, str]]] = {}
    for url, subdir, basename in PAGES:
        groups.setdefault(subdir, []).append((url, basename))

    label_map = {".": "Top-Level"}
    lines = ["# Documentation Index\n"]
    lines.append(f"> Total pages: **{len(PAGES)}**\n")

    for subdir in sorted(groups.keys()):
        title = label_map.get(subdir, subdir)
        lines.append(f"## {title}\n")
        prefix = "" if subdir == "." else f"{subdir}/"
        for _, basename in sorted(groups[subdir]):
            lines.append(f"- [{prefix}{basename}]({prefix}{basename})")
        lines.append("")

    path = os.path.join(REFS_DIR, "INDEX.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("  INDEX.md rebuilt.")


def main():
    os.makedirs(REFS_DIR, exist_ok=True)

    if len(sys.argv) > 1 and sys.argv[1] == "--index":
        rebuild_index()
        return

    if not PAGES:
        print("ERROR: PAGES list is empty. Edit scripts/scrape.py to add your URLs first.")
        sys.exit(1)

    success = 0
    failures = []

    for url, subdir, basename in PAGES:
        target = REFS_DIR if subdir == "." else os.path.join(REFS_DIR, subdir)
        os.makedirs(target, exist_ok=True)
        filepath = os.path.join(target, basename)

        sys.stdout.write(f"[{success + len(failures) + 1}/{len(PAGES)}] {url}... ")
        sys.stdout.flush()

        try:
            md = convert_page(url)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md)
            size = os.path.getsize(filepath)
            print(f"OK ({size // 1024} KB)")
            success += 1
        except Exception as e:
            print(f"ERROR: {e}")
            failures.append(url)

        time.sleep(REQUEST_DELAY)

    print(f"\nTotal: {len(PAGES)} | OK: {success} | Failed: {len(failures)}")
    if failures:
        print("Failures:")
        for u in failures:
            print(f"  - {u}")

    rebuild_index()
    print("Done!")


if __name__ == "__main__":
    main()
