"""解析 xlsx，导出「位置映射 JSON」与「去重原文 TXT」。

输出约定：
- JSON：list[CellPos]，其中 CellPos = {"id": int, "text": 原始文本, "cells": [(sheet, coord), ...]}
        同一原文文本的所有出现位置聚合到同一条记录。
- TXT ：每行一条文本（首行 id=0，按首次出现顺序），CR/LF 已转义，保证一行一条。

只导出可翻译的字符串单元格；数值、布尔、公式、日期等不导出。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Iterable

import openpyxl

from ...escape import escape_text


@dataclass
class _TextGroup:
    """同一个原文文本的所有出现位置。"""

    text: str
    cells: list[tuple[str, str]] = field(default_factory=list)
    id: int = -1


def _is_translatable(cell) -> bool:
    """判断单元格是否为「应翻译的字符串」。

    - data_type 为 's'（shared string / 内联 string）的才视为文本；
    - 以 '=' 开头视为公式，跳过；
    - 空字符串不导出。
    """
    if cell.data_type != "s":
        return False
    val = cell.value
    if not isinstance(val, str):
        return False
    if val == "":
        return False
    if val.startswith("="):
        return False
    return True


def extract(
    xlsx_path: str | os.PathLike,
    txt_path: str | os.PathLike,
    json_path: str | os.PathLike,
) -> dict[str, Any]:
    """从 xlsx 提取可翻译文本，写出 txt（去重原文）与 json（位置映射）。

    Returns:
        统计信息 dict：
            {"sheets": [...], "cells_total": int, "cells_translatable": int,
             "unique_texts": int, "txt_path": ..., "json_path": ...}
    """
    xlsx_path = os.fspath(xlsx_path)
    txt_path = os.fspath(txt_path)
    json_path = os.fspath(json_path)

    wb = openpyxl.load_workbook(xlsx_path, data_only=False, keep_vba=False)

    groups: list[_TextGroup] = []
    index_by_text: dict[str, int] = {}
    sheets_seen: list[str] = []
    cells_total = 0
    cells_translatable = 0

    for ws in wb.worksheets:
        sheets_seen.append(ws.title)
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                cells_total += 1
                if not _is_translatable(cell):
                    continue
                cells_translatable += 1
                text = cell.value
                if text not in index_by_text:
                    g = _TextGroup(text=text)
                    g.id = len(groups)
                    index_by_text[text] = g.id
                    groups.append(g)
                else:
                    g = groups[index_by_text[text]]
                g.cells.append((ws.title, cell.coordinate))

    # 写 txt：一行一条，按 id 顺序，CR/LF 转义。
    with open(txt_path, "w", encoding="utf-8", newline="") as f:
        for g in groups:
            f.write(escape_text(g.text))
            f.write("\n")

    # 写 json：保留原始文本与位置列表，便于回写。
    payload = [
        {"id": g.id, "text": g.text, "cells": g.cells}
        for g in groups
    ]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return {
        "sheets": sheets_seen,
        "cells_total": cells_total,
        "cells_translatable": cells_translatable,
        "unique_texts": len(groups),
        "txt_path": txt_path,
        "json_path": json_path,
    }
