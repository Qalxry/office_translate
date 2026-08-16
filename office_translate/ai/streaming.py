"""Incremental preview extraction for streaming model protocols.

These helpers are display-only: they return structurally complete fragments
from accumulated model output before the block finishes. Final acceptance is
always decided by the strict parsers in ``contracts``.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from typing import Any

from .contracts import (
    OutputContractError,
    decode_text_line,
    strip_text_sequence_prefix,
)


def _json_preview_items(content: str) -> list[dict[str, Any]]:
    key = content.find('"items"')
    if key < 0:
        return []
    colon = content.find(":", key + 7)
    if colon < 0:
        return []
    bracket = content.find("[", colon)
    if bracket < 0:
        return []
    i = bracket + 1
    items: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    while i < len(content):
        while i < len(content) and content[i] in " \t\r\n,":
            i += 1
        if i >= len(content):
            break
        if content[i] == "]":
            break
        if content[i] != "{":
            i += 1
            continue
        end, ok = _match_json_object(content, i)
        if not ok:
            partial = _partial_json_item(content, i)
            if partial and partial["id"] not in seen_ids:
                seen_ids.add(partial["id"])
                items.append(partial)
            break
        raw = content[i : end + 1]
        i = end + 1
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(obj, dict)
            and isinstance(obj.get("id"), int)
            and not isinstance(obj.get("id"), bool)
            and isinstance(obj.get("translation"), str)
        ):
            if obj["id"] in seen_ids:
                continue
            seen_ids.add(obj["id"])
            item: dict[str, Any] = {
                "id": obj["id"],
                "translation": obj["translation"],
            }
            terms = obj.get("uncertain_terms")
            if isinstance(terms, list):
                safe_terms = []
                for term in terms:
                    if (
                        isinstance(term, dict)
                        and all(
                            isinstance(term.get(name), str)
                            for name in ("term", "reason", "candidate")
                        )
                    ):
                        safe_terms.append(
                            {
                                name: term[name]
                                for name in ("term", "reason", "candidate")
                            }
                        )
                item["uncertain_terms"] = safe_terms
            items.append(item)
    return items


def _match_json_string(text: str, start: int) -> tuple[int | None, str | None]:
    """Return (end_index, decoded_value) when a JSON string is complete."""
    if start >= len(text) or text[start] != '"':
        return None, None
    buf: list[str] = []
    i = start + 1
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            if i + 1 >= len(text):
                return None, None
            buf.append(text[i : i + 2])
            i += 2
            continue
        if ch == '"':
            try:
                return i, json.loads('"' + "".join(buf) + '"')
            except json.JSONDecodeError:
                return None, None
        buf.append(ch)
        i += 1
    return None, None


def _partial_json_item(content: str, start: int) -> dict[str, Any] | None:
    """Extract a display preview when translation is complete but item isn't."""
    segment = content[start:]
    id_match = re.search(r'"id"\s*:\s*(\d+)', segment)
    if not id_match:
        return None
    translation_match = re.search(r'"translation"\s*:\s*', segment)
    if not translation_match:
        return None
    _, translation = _match_json_string(segment, translation_match.end())
    if translation is None:
        return None
    return {"id": int(id_match.group(1)), "translation": translation}


def _match_json_object(text: str, start: int) -> tuple[int, bool]:
    depth = 0
    in_string = False
    escaped = False
    i = start
    while i < len(text):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i, True
        i += 1
    return len(text) - 1, False


_ITEM_START = re.compile(r"<item(?=[\s>])")


def _xml_preview_items(content: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for match in _ITEM_START.finditer(content):
        start = match.start()
        end_tag = content.find("</item>", start)
        if end_tag < 0:
            break
        fragment = content[start : end_tag + 7]
        try:
            el = ET.fromstring(fragment)
        except ET.ParseError:
            continue
        if el.tag != "item" or set(el.attrib) != {"id"}:
            continue
        try:
            item_id = int(el.attrib["id"])
        except ValueError:
            continue
        if item_id < 0:
            continue
        translation = None
        for sub in el:
            if sub.tag == "translation":
                translation = sub.text or ""
                break
        if translation is None:
            continue
        items.append({"id": item_id, "translation": translation})
    return items


def _text_preview_items(
    content: str,
    start_id: int,
    expected_ids: Iterable[int] | None = None,
) -> list[dict[str, Any]]:
    if content == "":
        return []
    if content.endswith("\n"):
        complete_text = content[:-1]
    else:
        last_newline = content.rfind("\n")
        complete_text = content[:last_newline] if last_newline >= 0 else ""
    mapped_ids = tuple(expected_ids) if expected_ids is not None else None
    items: list[dict[str, Any]] = []
    for offset, line in enumerate(complete_text.split("\n")):
        if mapped_ids is not None and offset >= len(mapped_ids):
            break
        try:
            translation = strip_text_sequence_prefix(decode_text_line(line))
        except OutputContractError:
            continue
        item_id = mapped_ids[offset] if mapped_ids is not None else start_id + offset
        items.append({"id": item_id, "translation": translation})
    return items


def extract_preview_items(
    content: str,
    output_format: str,
    *,
    start_id: int = 0,
    expected_ids: Iterable[int] | None = None,
) -> list[dict[str, Any]]:
    """Return display-only completed fragments from accumulated model output."""
    if output_format == "json":
        return _json_preview_items(content)
    if output_format == "xml":
        return _xml_preview_items(content)
    if output_format == "text":
        return _text_preview_items(content, start_id, expected_ids)
    raise ValueError(f"未知输出格式: {output_format!r}")
