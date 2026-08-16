"""Apply structured translations to revision-checked XLSX files safely."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Iterable

import openpyxl
from openpyxl.cell.rich_text import CellRichText, TextBlock

from ...artifacts import SourceArtifact, TranslationArtifact, sha256_file
from ...escape import unescape_text
from ...storage import cleanup_file, make_temp_path
from .extractor import (
    WorkbookDiagnostic,
    cell_text,
    is_multi_run_rich_text,
    require_valid_workbook,
)


EXCEL_CELL_TEXT_LIMIT = 32_767
RICH_TEXT_POLICIES = {"preserve_original", "flatten"}


class TranslationError(Exception):
    """The workbook, mapping, or translation set is unsafe to apply."""

    def __init__(
        self,
        message: str,
        diagnostics: Iterable[WorkbookDiagnostic] = (),
    ) -> None:
        self.diagnostics = tuple(diagnostics)
        super().__init__(message)

    def diagnostics_as_dict(self) -> list[dict[str, Any]]:
        return [diagnostic.to_dict() for diagnostic in self.diagnostics]


def _load_translations(txt_path: str, expected_count: int) -> list[str]:
    with open(txt_path, "r", encoding="utf-8", newline="") as handle:
        raw = handle.read()
    if raw.endswith("\n"):
        raw = raw[:-1]
    lines = raw.split("\n") if raw != "" else []
    if len(lines) != expected_count:
        raise TranslationError(
            f"译文行数({len(lines)})与原文条数({expected_count})不一致，"
            "请检查 txt 是否被改动或丢失/多出空行。"
        )
    return [unescape_text(line) for line in lines]


def _ordered_mapping(mapping: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(mapping, key=lambda item: item.get("id", -1))
    ids = [item.get("id") for item in ordered]
    if ids != list(range(len(ordered))):
        raise TranslationError(f"JSON 的 id 不连续: {ids}")
    return ordered


def _cell_at(wb: Any, sheet_name: str, coordinate: str, item_id: int) -> Any:
    worksheets = {ws.title: ws for ws in wb.worksheets}
    ws = worksheets.get(sheet_name)
    if ws is None:
        raise TranslationError(f"原文 {item_id} 对应的工作表不存在: {sheet_name!r}")
    try:
        return ws[coordinate]
    except (KeyError, TypeError, ValueError) as exc:
        raise TranslationError(
            f"原文 {item_id} 的单元格坐标无效: {sheet_name}!{coordinate}"
        ) from exc


def _raw_cell_ref(raw_cell: Any, item_id: int) -> tuple[str, str]:
    if isinstance(raw_cell, dict):
        sheet_name = raw_cell.get("sheet")
        coordinate = raw_cell.get("coordinate")
    else:
        try:
            sheet_name, coordinate = raw_cell
        except (TypeError, ValueError) as exc:
            raise TranslationError(f"原文 {item_id} 的单元格位置无效") from exc
    if not isinstance(sheet_name, str) or not isinstance(coordinate, str):
        raise TranslationError(f"原文 {item_id} 的单元格位置无效")
    return sheet_name, coordinate


def _validate_source_cells(wb: Any, mapping: Iterable[dict[str, Any]]) -> None:
    for item in mapping:
        item_id = item["id"]
        original = item["text"]
        for raw_cell in item["cells"]:
            sheet_name, coordinate = _raw_cell_ref(raw_cell, item_id)
            cell = _cell_at(wb, sheet_name, coordinate, item_id)
            current = cell_text(cell.value) if cell.value is not None else None
            if current != original:
                raise TranslationError(
                    f"原文已变化: {sheet_name}!{coordinate}，"
                    f"提取时为 {original!r}，当前为 {current!r}，请重新提取"
                )


def _excel_text_length(value: str) -> int:
    """Count UTF-16 code units, matching Excel's character-limit boundary."""
    return len(value.encode("utf-16-le")) // 2


def _length_diagnostic(
    *,
    item_id: int,
    sheet_name: str,
    coordinate: str,
    mode: str,
    value: str,
) -> WorkbookDiagnostic | None:
    length = _excel_text_length(value)
    if length <= EXCEL_CELL_TEXT_LIMIT:
        return None
    return WorkbookDiagnostic(
        code="xlsx.cell_text_limit",
        severity="error",
        message=(
            f"{sheet_name}!{coordinate} 的 {mode} 单元格文本为 {length} 个字符，"
            f"超过 Excel 上限 {EXCEL_CELL_TEXT_LIMIT}。"
        ),
        action="缩短原文或译文后重试；系统不会自动截断内容。",
        sheet=sheet_name,
        coordinate=coordinate,
        details={
            "item_id": item_id,
            "mode": mode,
            "length": length,
            "max_length": EXCEL_CELL_TEXT_LIMIT,
            "excess": length - EXCEL_CELL_TEXT_LIMIT,
        },
    )


def _validate_rich_text_policy(policy: str) -> None:
    if policy not in RICH_TEXT_POLICIES:
        choices = ", ".join(sorted(RICH_TEXT_POLICIES))
        raise TranslationError(f"未知 rich_text_policy: {policy!r}，可选值: {choices}")


def _validate_export_plan(
    wb: Any,
    mapping: list[dict[str, Any]],
    translations: dict[int, str],
    mode_sep: str,
    rich_text_policy: str,
) -> int:
    """Validate every output cell before creating any candidate output file."""
    _validate_source_cells(wb, mapping)
    diagnostics: list[WorkbookDiagnostic] = []
    preserved_count = 0
    for item in mapping:
        item_id = item["id"]
        original = item["text"]
        try:
            translated = translations[item_id]
        except KeyError as exc:
            raise TranslationError(f"缺少译文 ID: {item_id}") from exc
        if not isinstance(translated, str):
            raise TranslationError(f"译文 {item_id} 必须是字符串")
        for raw_cell in item["cells"]:
            sheet_name, coordinate = _raw_cell_ref(raw_cell, item_id)
            cell = _cell_at(wb, sheet_name, coordinate, item_id)
            rich = is_multi_run_rich_text(cell.value)
            if rich and rich_text_policy == "preserve_original":
                preserved_count += 1
                translated_value = cell_text(cell.value)
                bilingual_value = translated_value
            else:
                translated_value = translated
                bilingual_value = original + mode_sep + translated
            for mode, value in (
                ("translated", translated_value),
                ("bilingual", bilingual_value),
            ):
                diagnostic = _length_diagnostic(
                    item_id=item_id,
                    sheet_name=sheet_name,
                    coordinate=coordinate,
                    mode=mode,
                    value=value,
                )
                if diagnostic is not None:
                    diagnostics.append(diagnostic)
    if diagnostics:
        raise TranslationError(
            "XLSX 导出预检失败；没有发布任何输出文件。",
            diagnostics,
        )
    return preserved_count


def _replace_single_run(value: CellRichText, translated: str) -> CellRichText:
    """Keep the inline font for a one-run rich-text value."""
    if len(value) != 1:
        return value
    part = value[0]
    if isinstance(part, str):
        return CellRichText([translated])
    return CellRichText([TextBlock(part.font, translated)])


def _fill_workbook(
    workbook: Any,
    mapping: list[dict[str, Any]],
    translations: dict[int, str],
    mode: str,
    sep: str,
    rich_text_policy: str,
) -> int:
    preserved_count = 0
    worksheets = {ws.title: ws for ws in workbook.worksheets}
    for item in mapping:
        item_id = item["id"]
        original = item["text"]
        translated = translations[item_id]
        if mode == "translated":
            new_value = translated
        elif mode == "bilingual":
            new_value = original + sep + translated
        else:
            raise TranslationError(f"未知输出模式: {mode!r}")

        for raw_cell in item["cells"]:
            sheet_name, coordinate = _raw_cell_ref(raw_cell, item_id)
            cell = worksheets[sheet_name][coordinate]
            if is_multi_run_rich_text(cell.value):
                if rich_text_policy == "preserve_original":
                    preserved_count += 1
                    continue
                # ``flatten`` is intentionally explicit.  The default policy
                # has already failed in _validate_export_plan before reaching
                # this function.
                cell.value = new_value
            elif isinstance(cell.value, CellRichText):
                cell.value = _replace_single_run(cell.value, new_value)
            else:
                cell.value = new_value
    return preserved_count


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _load_candidate(path: Path) -> Any:
    return openpyxl.load_workbook(
        path,
        data_only=False,
        keep_links=True,
        keep_vba=False,
        rich_text=True,
    )


def _build_candidate(
    original: str,
    candidate: Path,
    mapping: list[dict[str, Any]],
    translations: dict[int, str],
    mode: str,
    sep: str,
    rich_text_policy: str,
) -> None:
    shutil.copy2(original, candidate)
    workbook = _load_candidate(candidate)
    try:
        _validate_source_cells(workbook, mapping)
        _fill_workbook(
            workbook,
            mapping,
            translations,
            mode,
            sep,
            rich_text_policy,
        )
        workbook.save(candidate)
    finally:
        workbook.close()
    # An output is not considered a candidate until it is durable and can be
    # opened again.  This catches serializer failures before publication.
    _fsync_file(candidate)
    check = _load_candidate(candidate)
    check.close()


def _publish_candidates(candidates: list[tuple[Path, Path]]) -> None:
    """Publish one or two outputs with rollback on a partial os.replace."""
    targets = [target.resolve() for _, target in candidates]
    if len(set(targets)) != len(targets):
        raise TranslationError("译文版与双语版输出路径不能相同")
    backups: dict[Path, Path] = {}
    committed: list[Path] = []
    try:
        for target in targets:
            if target.is_dir():
                raise TranslationError(f"输出路径是目录，无法写入: {target}")
            if target.exists():
                backup = make_temp_path(target, suffix=".xlsx")
                os.replace(target, backup)
                backups[target] = backup
        for candidate, target in candidates:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(candidate, target)
            committed.append(target)
    except Exception:
        for target in committed:
            cleanup_file(target)
        for target, backup in backups.items():
            try:
                os.replace(backup, target)
            except OSError:
                pass
        raise
    finally:
        for backup in backups.values():
            cleanup_file(backup)


def _export_mapping(
    original: str,
    mapping: list[dict[str, Any]],
    translations: dict[int, str],
    output_translated: str | os.PathLike[str],
    output_bilingual: str | os.PathLike[str] | None,
    sep: str,
    rich_text_policy: str,
    expected_input_sha256: str | None = None,
) -> dict[str, Any]:
    _validate_rich_text_policy(rich_text_policy)
    if not isinstance(sep, str):
        raise TranslationError("双语分隔符必须是字符串")
    require_valid_workbook(original)
    validation_wb = _load_candidate(Path(original))
    try:
        preserved_count = _validate_export_plan(
            validation_wb,
            mapping,
            translations,
            sep,
            rich_text_policy,
        )
    finally:
        validation_wb.close()

    translated_target = Path(output_translated)
    bilingual_target = Path(output_bilingual) if output_bilingual is not None else None
    original_target = Path(original).resolve()
    if translated_target.resolve() == original_target or (
        bilingual_target is not None and bilingual_target.resolve() == original_target
    ):
        raise TranslationError("输出路径不能覆盖输入工作簿")
    temp_translated = make_temp_path(translated_target, suffix=".xlsx")
    temp_bilingual = (
        make_temp_path(bilingual_target, suffix=".xlsx")
        if bilingual_target is not None
        else None
    )
    try:
        _build_candidate(
            original,
            temp_translated,
            mapping,
            translations,
            "translated",
            sep,
            rich_text_policy,
        )
        if temp_bilingual is not None and bilingual_target is not None:
            _build_candidate(
                original,
                temp_bilingual,
                mapping,
                translations,
                "bilingual",
                sep,
                rich_text_policy,
            )
        if expected_input_sha256 is not None and sha256_file(original) != expected_input_sha256:
            raise TranslationError("生成输出期间输入工作簿发生变化，请重试")
        pairs = [(temp_translated, translated_target)]
        if temp_bilingual is not None and bilingual_target is not None:
            pairs.append((temp_bilingual, bilingual_target))
        _publish_candidates(pairs)
    finally:
        cleanup_file(temp_translated)
        cleanup_file(temp_bilingual)

    result: dict[str, Any] = {
        "unique_texts": len(mapping),
        "cells_filled": sum(len(item["cells"]) for item in mapping) - preserved_count,
    }
    if preserved_count:
        result["rich_text_preserved"] = preserved_count
    return result


def apply_artifacts(
    original_xlsx: str | os.PathLike[str],
    source: SourceArtifact,
    translation: TranslationArtifact,
    output_translated: str | os.PathLike[str],
    output_bilingual: str | os.PathLike[str],
    sep: str = "\n",
    *,
    rich_text_policy: str = "flatten",
) -> dict[str, Any]:
    """Apply structured translations with preflight and atomic publication.

    ``flatten`` translates multi-run rich text by replacing it with a normal
    string and intentionally discarding local run formatting.  The explicit
    ``preserve_original`` policy leaves those cells unchanged in both outputs.
    No output is published until both output workbooks pass serialization/open
    checks.
    """
    original = os.fspath(original_xlsx)
    if sha256_file(original) != source.input_sha256:
        raise TranslationError("输入工作簿摘要已变化，请重新提取")
    if translation.source_revision != source.source_revision:
        raise TranslationError("译文与原文的 source_revision 不一致")
    if not translation.is_complete_for(source):
        raise TranslationError("译文 ID 不完整或含失败状态，不能导出")

    mapping = [
        {
            "id": item.id,
            "text": item.text,
            "cells": [cell.to_dict() for cell in item.cells],
        }
        for item in source.items
    ]
    translations = {item.id: item.translation for item in translation.items}
    result = _export_mapping(
        original,
        mapping,
        translations,
        output_translated,
        output_bilingual,
        sep,
        rich_text_policy,
        expected_input_sha256=source.input_sha256,
    )
    return result


def apply(
    original_xlsx: str | os.PathLike[str],
    json_path: str | os.PathLike[str],
    translated_txt: str | os.PathLike[str],
    output_translated: str | os.PathLike[str],
    output_bilingual: str | os.PathLike[str] | None = None,
    sep: str = "\n",
    *,
    rich_text_policy: str = "flatten",
) -> dict[str, Any]:
    """Internal format adapter using the same guarded export path."""
    original = os.fspath(original_xlsx)
    with open(json_path, "r", encoding="utf-8") as handle:
        raw_mapping = json.load(handle)
    if not isinstance(raw_mapping, list):
        raise TranslationError("位置映射 JSON 顶层必须是数组")
    mapping = _ordered_mapping(raw_mapping)
    translations_list = _load_translations(os.fspath(translated_txt), len(mapping))
    translations = {item["id"]: translations_list[item["id"]] for item in mapping}
    result = _export_mapping(
        original,
        mapping,
        translations,
        output_translated,
        output_bilingual,
        sep,
        rich_text_policy,
        expected_input_sha256=sha256_file(original),
    )
    result.update(
        {
            "translated_output": os.fspath(output_translated),
            "bilingual_output": (
                os.fspath(output_bilingual) if output_bilingual is not None else None
            ),
        }
    )
    return result
