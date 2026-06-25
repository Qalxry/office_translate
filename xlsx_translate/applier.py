"""把译文回填到 xlsx，输出「原文-译文对照」与「仅译文」两份文件。

策略：
1) 以原 xlsx 为模板，逐字物理拷贝得到目标文件（保留所有样式、列宽、合并等）。
2) 用 openpyxl 打开拷贝，按 JSON 位置映射把译文写回对应单元格。
   - 仅译文版：单元格值 = 译文
   - 对照版：单元格值 = 原文 + 分隔符 + 译文
3) 全程不改任何样式属性，仅替换 value。

输入文本约定：译文 txt 每行一条，行序 = JSON 中 id 序（从 0 起）；
CR/LF 须转义（与 extract 输出一致），回填前会 unescape 还原。
"""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

import openpyxl

from .escape import unescape_text


class TranslationError(Exception):
    """回填过程中的校验错误。"""


def _load_translations(txt_path: str, expected_count: int) -> list[str]:
    """读取译文 txt，返回按行序（= id）排列的还原后译文列表。"""
    with open(txt_path, "r", encoding="utf-8", newline="") as f:
        raw = f.read()

    # 按约定每行一条；去掉文件末尾的一个换行再按 \n 切分，
    # 这样既兼容末尾换行，又能保留空行（可能代表空译文）。
    if raw.endswith("\n"):
        raw = raw[:-1]
    lines = raw.split("\n") if raw != "" else []

    if len(lines) != expected_count:
        raise TranslationError(
            f"译文行数({len(lines)})与原文条数({expected_count})不一致，"
            f"请检查 txt 是否被改动或丢失/多出空行。"
        )

    return [unescape_text(line) for line in lines]


def _fill_workbook(
    src_xlsx: str,
    out_xlsx: str,
    mapping: list[dict[str, Any]],
    translations: list[str],
    mode: str,
    sep: str,
) -> None:
    """拷贝 src 到 out，并按 mode 填入译文。"""
    # 物理拷贝，最大程度保留样式与结构。
    shutil.copy2(src_xlsx, out_xlsx)

    wb = openpyxl.load_workbook(out_xlsx, data_only=False, keep_vba=False)

    # 建立 sheet 名 -> worksheet 索引，避免标题重复时取错。
    ws_by_name: dict[str, openpyxl.worksheet.worksheet.Worksheet] = {}
    for ws in wb.worksheets:
        ws_by_name[ws.title] = ws

    # text -> 译文，便于直接查表（mapping 已按 id 升序，但用 id 更稳）。
    id_to_translation = {m["id"]: translations[m["id"]] for m in mapping}

    for m in mapping:
        tid = m["id"]
        original = m["text"]
        translated = id_to_translation[tid]
        if mode == "translated":
            new_val = translated
        elif mode == "bilingual":
            # 原文在后则不便阅读；约定：原文 + 分隔符 + 译文。
            new_val = original + sep + translated
        else:
            raise ValueError(f"未知 mode: {mode!r}")

        for sheet_name, coord in m["cells"]:
            ws = ws_by_name.get(sheet_name)
            if ws is None:
                raise TranslationError(f"找不到工作表: {sheet_name!r}")
            cell = ws[coord]
            cell.value = new_val

    wb.save(out_xlsx)


def apply(
    original_xlsx: str | os.PathLike,
    json_path: str | os.PathLike,
    translated_txt: str | os.PathLike,
    output_translated: str | os.PathLike,
    output_bilingual: str | os.PathLike | None = None,
    sep: str = "\n",
) -> dict[str, Any]:
    """根据译文 txt 回填 xlsx，输出「仅译文」与（可选）「原文-译文对照」文件。

    Args:
        original_xlsx: 原始 xlsx（作为样式模板，不会被修改）。
        json_path:     extract 产出的位置映射 JSON。
        translated_txt: 用户翻译后的 txt（行序对应 JSON 的 id）。
        output_translated: 仅译文版输出路径。
        output_bilingual:  原文-译文对照版输出路径；为 None 则不生成。
        sep: 对照版原文与译文之间的分隔符，默认换行。

    Returns:
        统计信息 dict。
    """
    original_xlsx = os.fspath(original_xlsx)
    json_path = os.fspath(json_path)
    translated_txt = os.fspath(translated_txt)
    output_translated = os.fspath(output_translated)

    with open(json_path, "r", encoding="utf-8") as f:
        mapping: list[dict[str, Any]] = json.load(f)

    # 期望译文条数 = 去重后的原文条数
    expected = len(mapping)
    translations = _load_translations(translated_txt, expected)

    # 幂等性：mapping 必须有连续的 0..N-1 的 id
    ids = sorted(m["id"] for m in mapping)
    if ids != list(range(expected)):
        # 修正：某些情况下 extract 可能未保证有序，按 id 排序后再校验连续性
        mapping_sorted = sorted(mapping, key=lambda m: m["id"])
        ids = [m["id"] for m in mapping_sorted]
        if ids != list(range(expected)):
            raise TranslationError(f"JSON 的 id 不连续: {ids}")
        mapping = mapping_sorted

    _fill_workbook(original_xlsx, output_translated, mapping, translations, "translated", sep)

    result: dict[str, Any] = {
        "translated_output": output_translated,
        "bilingual_output": None,
        "unique_texts": expected,
        "cells_filled": sum(len(m["cells"]) for m in mapping),
    }

    if output_bilingual is not None:
        output_bilingual = os.fspath(output_bilingual)
        _fill_workbook(original_xlsx, output_bilingual, mapping, translations, "bilingual", sep)
        result["bilingual_output"] = output_bilingual

    return result
