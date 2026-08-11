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
from datetime import datetime
from typing import Any, Optional


class GlossaryError(Exception):
    """术语库操作错误。"""


DEFAULT_GLOSSARY_FILE = "data/glossary.json"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_glossary(path: str = DEFAULT_GLOSSARY_FILE) -> dict[str, Any]:
    """读取术语库；文件不存在时返回空结构。"""
    if not os.path.isfile(path):
        return {"categories": {}}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("categories"), dict):
        raise GlossaryError(f"术语库 {path} 格式非法：顶层需有 categories 映射。")
    return data


def save_glossary(data: dict[str, Any], path: str = DEFAULT_GLOSSARY_FILE) -> None:
    """写回术语库（保留已存在条目）。"""
    payload = {"categories": data.get("categories", {})}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


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
    if not source or not target:
        raise GlossaryError("source 与 target 不能为空")
    categories = data.setdefault("categories", {})
    category = category.strip() or "默认"
    entries = categories.setdefault(category, [])

    for entry in entries:
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
    entries = data.get("categories", {}).get(category, [])
    before = len(entries)
    data["categories"][category] = [e for e in entries if e["source"] != source]
    return len(data["categories"][category]) != before


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
