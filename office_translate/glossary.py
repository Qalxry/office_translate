"""分类术语库：加载 / 新增 / 匹配精简 / prompt 注入格式化。

持久化格式（glossary.json）：
    {
      "categories": {
        "<类别名>": [
          {"source": "...", "target": "...", "note": "...", "created": "..."},
          ...
        ]
      }
    }
"""

from __future__ import annotations

import json
import os
import copy
from datetime import datetime
from collections.abc import Callable, Mapping
from typing import Any, Optional

from .storage import LockRegistry, atomic_write_json


class GlossaryError(Exception):
    """术语库操作错误。"""


DEFAULT_GLOSSARY_FILE = "data/glossary.json"
_GLOSSARY_LOCKS = LockRegistry()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _validate_glossary(data: Any, *, path: str = "术语库") -> dict[str, Any]:
    if not isinstance(data, Mapping) or not isinstance(data.get("categories"), Mapping):
        raise GlossaryError(f"{path} 格式非法：顶层需有 categories 映射。")
    categories = data["categories"]
    for category, entries in categories.items():
        if not isinstance(category, str) or not category.strip():
            raise GlossaryError(f"{path} 类别名必须是非空字符串。")
        if not isinstance(entries, list):
            raise GlossaryError(f"{path} 类别 {category!r} 必须是术语数组。")
        for index, entry in enumerate(entries):
            if not isinstance(entry, Mapping):
                raise GlossaryError(f"{path} 类别 {category!r} 的第 {index + 1} 项必须是对象。")
            source = entry.get("source")
            target = entry.get("target")
            if not isinstance(source, str) or not source.strip():
                raise GlossaryError(f"{path} 类别 {category!r} 的第 {index + 1} 项 source 非法。")
            if not isinstance(target, str) or not target.strip():
                raise GlossaryError(f"{path} 类别 {category!r} 的第 {index + 1} 项 target 非法。")
            for optional in ("note", "created"):
                if optional in entry and not isinstance(entry[optional], str):
                    raise GlossaryError(
                        f"{path} 类别 {category!r} 的第 {index + 1} 项 {optional} 必须是字符串。"
                    )
    try:
        json.dumps(data, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise GlossaryError(f"{path} 含有不可保存的 JSON 值。") from exc
    return {"categories": copy.deepcopy(dict(categories))}


class GlossaryStore:
    """Lock and atomically persist one glossary JSON file.

    ``update`` is the important route-facing API: it loads, invokes the
    mutator, validates, and replaces the file while holding one re-entrant
    process-local lock.  Separate ``load``/``save`` methods remain available
    for read-only and current-version callers, but a route doing a
    read-modify-write should use ``update``.
    """

    def __init__(self, path: str | os.PathLike[str] = DEFAULT_GLOSSARY_FILE):
        self.path = os.path.abspath(os.fspath(path))

    def _load_unlocked(self) -> dict[str, Any]:
        if not os.path.isfile(self.path):
            return {"categories": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise GlossaryError(f"术语库 {self.path} 不是合法 JSON。") from exc
        except OSError as exc:
            raise GlossaryError(f"读取术语库失败: {self.path}: {exc}") from exc
        return _validate_glossary(data, path=f"术语库 {self.path}")

    def load(self) -> dict[str, Any]:
        with _GLOSSARY_LOCKS.hold(self.path):
            return self._load_unlocked()

    def save(self, data: Mapping[str, Any]) -> None:
        payload = _validate_glossary(data)
        with _GLOSSARY_LOCKS.hold(self.path):
            try:
                atomic_write_json(self.path, payload)
            except (OSError, TypeError, ValueError) as exc:
                raise GlossaryError(f"保存术语库失败: {self.path}: {exc}") from exc

    def update(self, mutator: Callable[[dict[str, Any]], Any]) -> Any:
        """Run a glossary read-modify-write transaction under one lock."""
        if not callable(mutator):
            raise GlossaryError("update 需要可调用的修改函数。")
        with _GLOSSARY_LOCKS.hold(self.path):
            data = self._load_unlocked()
            result = mutator(data)
            payload = _validate_glossary(data)
            try:
                atomic_write_json(self.path, payload)
            except (OSError, TypeError, ValueError) as exc:
                raise GlossaryError(f"保存术语库失败: {self.path}: {exc}") from exc
            return result


def update_glossary(
    path: str | os.PathLike[str], mutator: Callable[[dict[str, Any]], Any]
) -> Any:
    """Atomically apply one glossary read-modify-write transaction."""
    return GlossaryStore(path).update(mutator)


def load_glossary(path: str = DEFAULT_GLOSSARY_FILE) -> dict[str, Any]:
    """读取术语库；文件不存在时返回空结构。"""
    return GlossaryStore(path).load()


def save_glossary(data: dict[str, Any], path: str = DEFAULT_GLOSSARY_FILE) -> None:
    """写回术语库（保留已存在条目）。"""
    GlossaryStore(path).save(data)


def list_categories(data: dict[str, Any]) -> list[str]:
    return sorted(data.get("categories", {}).keys())


def add_term(
    data: dict[str, Any],
    category: str,
    source: str,
    target: str,
    note: str = "",
) -> dict[str, Any]:
    """向指定类别新增术语；source 已存在则更新 target/note。返回该词条。"""
    if not isinstance(category, str):
        raise GlossaryError("category 必须是字符串")
    if not isinstance(source, str) or not source.strip() or not isinstance(target, str) or not target.strip():
        raise GlossaryError("source 与 target 不能为空")
    if not isinstance(note, str):
        raise GlossaryError("note 必须是字符串")
    categories = data.setdefault("categories", {})
    if not isinstance(categories, dict):
        raise GlossaryError("术语库格式非法：categories 必须是映射。")
    category = category.strip() or "默认"
    entries = categories.setdefault(category, [])
    if not isinstance(entries, list):
        raise GlossaryError(f"术语类别 {category!r} 格式非法：必须是数组。")

    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("source"), str):
            raise GlossaryError(f"术语类别 {category!r} 含有格式非法的条目。")
        if entry["source"] == source:
            entry["target"] = target
            if note:
                entry["note"] = note
            return entry
    entry = {
        "source": source,
        "target": target,
        "note": note,
        "created": _now_iso(),
    }
    entries.append(entry)
    return entry


def remove_term(data: dict[str, Any], category: str, source: str) -> bool:
    """从指定类别删除术语。返回是否删除成功。"""
    if not isinstance(category, str) or not isinstance(source, str):
        raise GlossaryError("category 与 source 必须是字符串")
    categories = data.get("categories", {})
    if not isinstance(categories, dict):
        raise GlossaryError("术语库格式非法：categories 必须是映射。")
    entries = categories.get(category, [])
    if not isinstance(entries, list):
        raise GlossaryError(f"术语类别 {category!r} 格式非法：必须是数组。")
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("source"), str):
            raise GlossaryError(f"术语类别 {category!r} 含有格式非法的条目。")
    before = len(entries)
    categories[category] = [
        e for e in entries
        if e.get("source") != source
    ]
    return len(categories[category]) != before


def match_terms(
    data: dict[str, Any],
    categories: Optional[list[str]],
    texts: list[str],
) -> list[dict[str, Any]]:
    """匹配精简化：只返回出现在 texts 中的术语条目（不区分大小写）。

    Args:
        data: 术语库数据。
        categories: 要使用的类别；None 或空 = 全部类别。
        texts: 本次待译文本列表。

    Returns:
        匹配到的术语条目列表。
    """
    if not texts:
        return []
    cats = list_categories(data) if not categories else [c for c in categories if c in data.get("categories", {})]

    # 归一化：统一大小写用于匹配
    text_blob = "\n".join(texts).lower()

    matched: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cat in cats:
        for entry in data["categories"].get(cat, []):
            key = entry["source"].lower()
            if key and key not in seen and key in text_blob:
                matched.append(entry)
                seen.add(key)
    return matched


def format_glossary_prompt(entries: list[dict[str, Any]]) -> str:
    """把匹配到的术语格式化为 prompt 片段（含在 system 消息中）。

    格式：每行 "原文 = 译文"；无匹配时返回空字符串。
    """
    if not entries:
        return ""
    lines = [f"{e['source']} = {e['target']}" for e in entries]
    return "已知术语表（必须优先采用这些译法）：\n" + "\n".join(lines)
