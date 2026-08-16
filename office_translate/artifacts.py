"""Validated, revision-bound artifacts for GUI translation jobs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

from .ai.contracts import OperationSummary, OutputContractError


SCHEMA_VERSION = 2
TRANSLATION_STATUSES = {"succeeded", "failed", "cancelled"}
REVIEW_STATUSES = {"pending", "accepted", "edited", "ignored"}
JOB_STAGES = {
    "created",
    "extracted",
    "translation_partial",
    "translated",
    "exported",
}


class ArtifactError(ValueError):
    """An artifact is malformed, inconsistent, or belongs to another revision."""


def canonical_sha256(value: Any) -> str:
    """Hash a JSON-compatible value using one stable serialization."""
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_sha256(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ArtifactError(f"{label} 不是有效 SHA-256")
    return value


def _validate_optional_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ArtifactError(f"{label} 必须是非空字符串或 null")
    return value


def _json_value(value: Any, label: str) -> Any:
    try:
        return json.loads(
            json.dumps(value, allow_nan=False, ensure_ascii=False)
        )
    except (TypeError, ValueError) as exc:
        raise ArtifactError(f"{label} 不是可保存的 JSON 数据") from exc


def review_id_for(
    source_revision: str,
    item_id: int,
    term: str,
    reason: str,
    candidate: str,
) -> str:
    """Return a deterministic ID for one review decision in one revision."""
    payload = {
        "source_revision": source_revision,
        "item_id": item_id,
        "term": term,
        "reason": reason,
        "candidate": candidate,
    }
    return "review-" + canonical_sha256(payload)[:32]


def build_review_items(
    source_revision: str,
    results: Iterable[dict[str, Any]],
    previous: Iterable[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Build validated review records while preserving previous decisions.

    The model owns only the candidate data.  Once a user has accepted, edited,
    or ignored a candidate, a later save of the same translation must not
    silently reset that decision.
    """
    previous_by_id: dict[str, dict[str, Any]] = {}
    for raw in previous:
        if not isinstance(raw, dict):
            continue
        review_id = raw.get("review_id") or raw.get("id")
        if isinstance(review_id, str):
            previous_by_id[review_id] = raw

    output: list[dict[str, Any]] = []
    for raw_result in results:
        if not isinstance(raw_result, dict):
            continue
        item_id = raw_result.get("id")
        terms = raw_result.get("uncertain_terms", [])
        if not isinstance(item_id, int) or isinstance(item_id, bool) or not isinstance(terms, list):
            continue
        for raw_term in terms:
            if not isinstance(raw_term, dict):
                continue
            term = raw_term.get("term")
            reason = raw_term.get("reason")
            candidate = raw_term.get("candidate")
            if not all(isinstance(value, str) for value in (term, reason, candidate)):
                continue
            review_id = review_id_for(source_revision, item_id, term, reason, candidate)
            old = previous_by_id.get(review_id, {})
            status = old.get("status", "pending")
            if status not in REVIEW_STATUSES:
                status = "pending"
            final_target = old.get("final_target")
            if final_target is not None and not isinstance(final_target, str):
                final_target = None
            if status == "accepted" and final_target is None:
                final_target = candidate
            output.append(
                {
                    "review_id": review_id,
                    "item_id": item_id,
                    "source_revision": source_revision,
                    "status": status,
                    "term": term,
                    "reason": reason,
                    "candidate": candidate,
                    "final_target": final_target,
                    "category": old.get("category", "") if isinstance(old.get("category", ""), str) else "",
                    "empty_translation_confirmed": bool(
                        old.get("empty_translation_confirmed", False)
                    ),
                    "apply_to_text": bool(old.get("apply_to_text", True)),
                }
            )
        if raw_result.get("status", "succeeded") == "succeeded" and raw_result.get(
            "translation", ""
        ) == "":
            reason = "该行译文为空"
            candidate = ""
            review_id = review_id_for(source_revision, item_id, "", reason, candidate)
            old = previous_by_id.get(review_id, {})
            status = old.get("status", "pending")
            if status not in REVIEW_STATUSES:
                status = "pending"
            confirmed = bool(
                raw_result.get("empty_translation_confirmed", False)
                or old.get("empty_translation_confirmed", False)
            )
            if status == "accepted" and not confirmed:
                status = "pending"
            output.append(
                {
                    "review_id": review_id,
                    "item_id": item_id,
                    "source_revision": source_revision,
                    "status": status,
                    "term": "",
                    "reason": reason,
                    "candidate": candidate,
                    "final_target": None,
                    "category": "",
                    "empty_translation_confirmed": confirmed,
                    "apply_to_text": False,
                }
            )
    return output


def validate_review_items(
    review_items: Any,
    source_revision: str,
    source_ids: Iterable[int],
) -> list[dict[str, Any]]:
    """Validate review records and their binding to the current source."""
    if not isinstance(review_items, list):
        raise ArtifactError("审核项必须是数组")
    allowed_ids = set(source_ids)
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    required = {
        "review_id", "item_id", "source_revision", "status", "term",
        "reason", "candidate", "final_target", "category",
        "empty_translation_confirmed",
        "apply_to_text",
    }
    for index, raw in enumerate(review_items):
        if not isinstance(raw, dict):
            raise ArtifactError(f"审核项 {index} 必须是对象")
        if set(raw) != required:
            raise ArtifactError(f"审核项 {index} 字段不完整或包含未知字段")
        review_id = raw["review_id"]
        item_id = raw["item_id"]
        if not isinstance(review_id, str) or not review_id or review_id in seen:
            raise ArtifactError(f"审核项 {index} 的 review_id 无效或重复")
        if not isinstance(item_id, int) or isinstance(item_id, bool) or item_id not in allowed_ids:
            raise ArtifactError(f"审核项 {index} 的 item_id 不属于当前原文")
        if raw["source_revision"] != source_revision:
            raise ArtifactError(f"审核项 {index} 不属于当前 source_revision")
        if raw["status"] not in REVIEW_STATUSES:
            raise ArtifactError(f"审核项 {index} 的状态非法")
        if not all(isinstance(raw[key], str) for key in ("term", "reason", "candidate", "category")):
            raise ArtifactError(f"审核项 {index} 的文本字段非法")
        if raw["final_target"] is not None and not isinstance(raw["final_target"], str):
            raise ArtifactError(f"审核项 {index} 的 final_target 非法")
        if not isinstance(raw["empty_translation_confirmed"], bool):
            raise ArtifactError(f"审核项 {index} 的空译文确认标记非法")
        if not isinstance(raw["apply_to_text"], bool):
            raise ArtifactError(f"审核项 {index} 的 apply_to_text 标记非法")
        expected = review_id_for(
            source_revision, item_id, raw["term"], raw["reason"], raw["candidate"]
        )
        if review_id != expected:
            raise ArtifactError(f"审核项 {index} 的 review_id 与内容不一致")
        if raw["status"] == "accepted" and raw["term"] == "" and not raw["empty_translation_confirmed"]:
            raise ArtifactError(f"审核项 {index} 的空译文尚未确认")
        if raw["status"] == "accepted" and raw["term"] != "" and not raw["final_target"]:
            raise ArtifactError(f"审核项 {index} 已接受但没有 final_target")
        if raw["status"] == "edited" and raw["term"] != "" and raw["final_target"] is None:
            raise ArtifactError(f"审核项 {index} 已编辑但没有 final_target")
        seen.add(review_id)
        normalized.append(dict(raw))
    return normalized


@dataclass(frozen=True)
class CellRef:
    sheet: str
    coordinate: str

    def to_dict(self) -> dict[str, str]:
        return {"sheet": self.sheet, "coordinate": self.coordinate}

    @classmethod
    def from_value(cls, value: Any) -> "CellRef":
        if isinstance(value, dict):
            sheet = value.get("sheet")
            coordinate = value.get("coordinate")
        elif isinstance(value, (list, tuple)) and len(value) == 2:
            sheet, coordinate = value
        else:
            raise ArtifactError(f"非法单元格位置: {value!r}")
        if not isinstance(sheet, str) or not sheet:
            raise ArtifactError("单元格位置缺少工作表名称")
        if not isinstance(coordinate, str) or not coordinate:
            raise ArtifactError("单元格位置缺少坐标")
        return cls(sheet=sheet, coordinate=coordinate)


@dataclass(frozen=True)
class SourceItem:
    id: int
    text: str
    cells: tuple[CellRef, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "cells": [cell.to_dict() for cell in self.cells],
        }

    @classmethod
    def from_dict(cls, value: Any) -> "SourceItem":
        if not isinstance(value, dict):
            raise ArtifactError("原文条目必须是对象")
        item_id = value.get("id")
        text = value.get("text")
        cells = value.get("cells")
        if not isinstance(item_id, int) or isinstance(item_id, bool) or item_id < 0:
            raise ArtifactError(f"非法原文 ID: {item_id!r}")
        if not isinstance(text, str):
            raise ArtifactError(f"原文 {item_id} 的 text 必须是字符串")
        if not isinstance(cells, list) or not cells:
            raise ArtifactError(f"原文 {item_id} 没有单元格位置")
        return cls(
            id=item_id,
            text=text,
            cells=tuple(CellRef.from_value(cell) for cell in cells),
        )


def _validate_contiguous_ids(items: Iterable[SourceItem]) -> tuple[SourceItem, ...]:
    ordered = tuple(sorted(items, key=lambda item: item.id))
    ids = [item.id for item in ordered]
    if ids != list(range(len(ordered))):
        raise ArtifactError(f"原文 ID 必须连续且从 0 开始，实际为 {ids}")
    return ordered


@dataclass(frozen=True)
class SourceArtifact:
    input_sha256: str
    source_revision: str
    items: tuple[SourceItem, ...]
    stats: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        input_sha256: str,
        items: Iterable[SourceItem],
        stats: dict[str, Any] | None = None,
    ) -> "SourceArtifact":
        input_sha256 = _validate_sha256(input_sha256, "input_sha256")
        ordered = _validate_contiguous_ids(items)
        revision_payload = {
            "schema_version": SCHEMA_VERSION,
            "input_sha256": input_sha256,
            "items": [item.to_dict() for item in ordered],
        }
        return cls(
            input_sha256=input_sha256,
            source_revision=canonical_sha256(revision_payload),
            items=ordered,
            stats=_json_value(stats or {}, "提取统计"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "input_sha256": self.input_sha256,
            "source_revision": self.source_revision,
            "items": [item.to_dict() for item in self.items],
            "stats": self.stats,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "SourceArtifact":
        if not isinstance(value, dict):
            raise ArtifactError("原文产物必须是对象")
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ArtifactError(
                f"不支持的原文产物版本: {value.get('schema_version')!r}"
            )
        input_sha256 = value.get("input_sha256")
        declared_revision = value.get("source_revision")
        raw_items = value.get("items")
        input_sha256 = _validate_sha256(input_sha256, "原文产物 input_sha256")
        if not isinstance(declared_revision, str):
            raise ArtifactError("原文产物缺少 source_revision")
        if not isinstance(raw_items, list):
            raise ArtifactError("原文产物 items 必须是数组")
        stats = value.get("stats", {})
        if not isinstance(stats, dict):
            raise ArtifactError("原文产物 stats 必须是对象")
        created = cls.create(
            input_sha256=input_sha256,
            items=(SourceItem.from_dict(item) for item in raw_items),
            stats=stats,
        )
        if created.source_revision != declared_revision:
            raise ArtifactError("原文产物内容与 source_revision 不一致")
        return created

    def item_by_id(self) -> dict[int, SourceItem]:
        return {item.id: item for item in self.items}


@dataclass(frozen=True)
class TranslationItem:
    id: int
    source: str
    translation: str
    status: str = "succeeded"
    error: str | None = None
    uncertain_terms: list[dict[str, Any]] = field(default_factory=list)
    empty_translation_confirmed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "translation": self.translation,
            "status": self.status,
            "error": self.error,
            "uncertain_terms": self.uncertain_terms,
            "empty_translation_confirmed": self.empty_translation_confirmed,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "TranslationItem":
        if not isinstance(value, dict):
            raise ArtifactError("译文条目必须是对象")
        item_id = value.get("id")
        source = value.get("source")
        translation = value.get("translation")
        status = value.get("status", "succeeded")
        error = value.get("error")
        uncertain_terms = value.get("uncertain_terms", [])
        empty_translation_confirmed = value.get("empty_translation_confirmed", False)
        if not isinstance(item_id, int) or isinstance(item_id, bool) or item_id < 0:
            raise ArtifactError(f"非法译文 ID: {item_id!r}")
        if not isinstance(source, str) or not isinstance(translation, str):
            raise ArtifactError(f"译文 {item_id} 的 source/translation 必须是字符串")
        if status not in TRANSLATION_STATUSES:
            raise ArtifactError(f"译文 {item_id} 的状态非法: {status!r}")
        if error is not None and not isinstance(error, str):
            raise ArtifactError(f"译文 {item_id} 的 error 必须是字符串或 null")
        if not isinstance(uncertain_terms, list):
            raise ArtifactError(f"译文 {item_id} 的 uncertain_terms 必须是数组")
        if not isinstance(empty_translation_confirmed, bool):
            raise ArtifactError(f"译文 {item_id} 的空译文确认标记非法")
        return cls(
            id=item_id,
            source=source,
            translation=translation,
            status=status,
            error=error,
            uncertain_terms=_json_value(uncertain_terms, "不确定术语"),
            empty_translation_confirmed=empty_translation_confirmed,
        )


@dataclass(frozen=True)
class TranslationArtifact:
    source_revision: str
    translation_revision: str
    items: tuple[TranslationItem, ...]
    summary: dict[str, Any]
    blocks: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    review_items: list[dict[str, Any]] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        source: SourceArtifact,
        results: Iterable[dict[str, Any]],
        summary: dict[str, Any] | None = None,
        blocks: list[dict[str, Any]] | None = None,
        diagnostics: list[dict[str, Any]] | None = None,
        review_items: list[dict[str, Any]] | None = None,
    ) -> "TranslationArtifact":
        source_by_id = source.item_by_id()
        raw_results = list(results)
        translated: list[TranslationItem] = []
        seen: set[int] = set()
        for raw in raw_results:
            if not isinstance(raw, dict):
                raise ArtifactError("译文 results 中存在非对象条目")
            item_id = raw.get("id")
            if not isinstance(item_id, int) or isinstance(item_id, bool):
                raise ArtifactError(f"译文缺少有效 ID: {item_id!r}")
            if item_id in seen:
                raise ArtifactError(f"译文 ID 重复: {item_id}")
            source_item = source_by_id.get(item_id)
            if source_item is None:
                raise ArtifactError(f"译文 ID 不属于当前原文修订: {item_id}")
            seen.add(item_id)
            status = raw.get("status")
            if status is None:
                status = "failed" if raw.get("error") else "succeeded"
            translated.append(
                TranslationItem.from_dict(
                    {
                        "id": item_id,
                        "source": source_item.text,
                        "translation": raw.get("translation", ""),
                        "status": status,
                        "error": raw.get("error"),
                        "uncertain_terms": raw.get("uncertain_terms", []),
                        "empty_translation_confirmed": raw.get(
                            "empty_translation_confirmed", False
                        ),
                    }
                )
            )
        ordered = tuple(sorted(translated, key=lambda item: item.id))
        expected_ids = tuple(item.id for item in source.items)
        if summary is None:
            actual = {item.id: item.status for item in ordered}
            succeeded_ids = [
                item_id for item_id, status in actual.items() if status == "succeeded"
            ]
            failed_ids = [
                item_id for item_id, status in actual.items() if status == "failed"
            ]
            cancelled_ids = [
                item_id
                for item_id in expected_ids
                if actual.get(item_id) == "cancelled" or item_id not in actual
            ]
            operation_summary = OperationSummary.from_outcomes(
                expected_ids,
                succeeded_ids=succeeded_ids,
                failed_ids=failed_ids,
                cancelled_ids=cancelled_ids,
            )
        else:
            try:
                operation_summary = OperationSummary.from_dict(
                    summary,
                    expected_ids,
                )
            except OutputContractError as exc:
                raise ArtifactError(str(exc)) from exc
            if {item.id for item in ordered} != set(expected_ids):
                raise ArtifactError(
                    "带 summary 的译文必须为每个原文 ID 保存成功、失败或取消条目"
                )
            statuses = {item.id: item.status for item in ordered}
            for item_id in operation_summary.succeeded_ids:
                if statuses.get(item_id) != "succeeded":
                    raise ArtifactError(f"summary 与译文 {item_id} 的成功状态不一致")
            for item_id in operation_summary.failed_ids:
                if statuses.get(item_id) != "failed":
                    raise ArtifactError(f"summary 与译文 {item_id} 的失败状态不一致")
            for item_id in operation_summary.cancelled_ids:
                if statuses.get(item_id) != "cancelled":
                    raise ArtifactError(f"summary 与译文 {item_id} 的取消状态不一致")
        safe_blocks = _json_value(blocks or [], "思考块")
        safe_diagnostics = _json_value(diagnostics or [], "翻译诊断")
        if review_items is None:
            safe_review = build_review_items(
                source.source_revision,
                raw_results,
            )
        else:
            safe_review = validate_review_items(
                review_items,
                source.source_revision,
                expected_ids,
            )
        revision_payload = {
            "schema_version": SCHEMA_VERSION,
            "source_revision": source.source_revision,
            "items": [item.to_dict() for item in ordered],
            "summary": operation_summary.to_dict(),
            "diagnostics": safe_diagnostics,
            "review_items": safe_review,
        }
        return cls(
            source_revision=source.source_revision,
            translation_revision=canonical_sha256(revision_payload),
            items=ordered,
            summary=operation_summary.to_dict(),
            blocks=safe_blocks,
            diagnostics=safe_diagnostics,
            review_items=safe_review,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_revision": self.source_revision,
            "translation_revision": self.translation_revision,
            "items": [item.to_dict() for item in self.items],
            "summary": self.summary,
            "blocks": self.blocks,
            "diagnostics": self.diagnostics,
            "review_items": self.review_items,
        }

    @classmethod
    def from_dict(cls, value: Any, source: SourceArtifact) -> "TranslationArtifact":
        if not isinstance(value, dict):
            raise ArtifactError("译文产物必须是对象")
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ArtifactError(
                f"不支持的译文产物版本: {value.get('schema_version')!r}"
            )
        if value.get("source_revision") != source.source_revision:
            raise ArtifactError("译文产物不属于当前 source_revision")
        raw_items = value.get("items")
        if not isinstance(raw_items, list):
            raise ArtifactError("译文产物 items 必须是数组")
        declared_revision = value.get("translation_revision")
        results = []
        source_by_id = source.item_by_id()
        for raw in raw_items:
            item = TranslationItem.from_dict(raw)
            source_item = source_by_id.get(item.id)
            if source_item is None or item.source != source_item.text:
                raise ArtifactError(f"译文 {item.id} 的 source 与当前原文不一致")
            results.append(item.to_dict())
        blocks = value.get("blocks", [])
        summary = value.get("summary")
        diagnostics = value.get("diagnostics", [])
        review_items = value.get("review_items", [])
        if not isinstance(summary, dict):
            raise ArtifactError("译文产物 summary 必须是对象")
        if not isinstance(blocks, list):
            raise ArtifactError("译文产物 blocks 必须是数组")
        if not isinstance(review_items, list):
            raise ArtifactError("译文产物 review_items 必须是数组")
        if not isinstance(diagnostics, list):
            raise ArtifactError("译文产物 diagnostics 必须是数组")
        created = cls.create(
            source=source,
            results=results,
            summary=summary,
            blocks=blocks,
            diagnostics=diagnostics,
            review_items=review_items,
        )
        if created.translation_revision != declared_revision:
            raise ArtifactError("译文产物内容与 translation_revision 不一致")
        return created

    def is_complete_for(self, source: SourceArtifact) -> bool:
        expected_ids = [item.id for item in source.items]
        actual_ids = [item.id for item in self.items]
        return (
            self.source_revision == source.source_revision
            and self.summary.get("status") == "succeeded"
            and actual_ids == expected_ids
            and all(item.status == "succeeded" for item in self.items)
            and all(
                item.translation != "" or item.empty_translation_confirmed
                for item in self.items
            )
            and all(item.get("status") != "pending" for item in self.review_items)
        )

    def pending_review_items(self) -> list[dict[str, Any]]:
        return [item for item in self.review_items if item.get("status") == "pending"]

    def as_results(self) -> list[dict[str, Any]]:
        return [
            {
                "id": item.id,
                "translation": item.translation,
                "status": item.status,
                "error": item.error,
                "uncertain_terms": item.uncertain_terms,
                "empty_translation_confirmed": item.empty_translation_confirmed,
            }
            for item in self.items
        ]


@dataclass(frozen=True)
class JobManifest:
    job_id: str
    input_filename: str
    input_sha256: str
    stage: str = "created"
    source_revision: str | None = None
    source_artifact: str | None = None
    translation_revision: str | None = None
    translation_artifact: str | None = None
    output_revision: str | None = None
    outputs: dict[str, str] = field(default_factory=dict)
    operation: dict[str, Any] = field(
        default_factory=lambda: {"status": "idle", "kind": None}
    )
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.job_id or not self.input_filename:
            raise ArtifactError("任务 manifest 缺少 job_id 或 input_filename")
        _validate_sha256(self.input_sha256, "任务 manifest input_sha256")
        if self.stage not in JOB_STAGES:
            raise ArtifactError(f"非法任务阶段: {self.stage!r}")
        _validate_optional_string(self.source_artifact, "source_artifact")
        _validate_optional_string(self.translation_artifact, "translation_artifact")
        if self.source_revision is not None:
            _validate_sha256(self.source_revision, "source_revision")
        if self.translation_revision is not None:
            _validate_sha256(self.translation_revision, "translation_revision")
        if self.output_revision is not None:
            _validate_sha256(self.output_revision, "output_revision")
        if not isinstance(self.outputs, dict) or not all(
            isinstance(key, str)
            and key
            and isinstance(value, str)
            and value
            for key, value in self.outputs.items()
        ):
            raise ArtifactError("任务 manifest outputs 非法")
        if not isinstance(self.operation, dict):
            raise ArtifactError("任务 manifest operation 非法")

        has_source = bool(self.source_revision and self.source_artifact)
        has_translation = bool(
            self.translation_revision and self.translation_artifact
        )
        if bool(self.source_revision) != bool(self.source_artifact):
            raise ArtifactError("source_revision 与 source_artifact 必须同时存在")
        if bool(self.translation_revision) != bool(self.translation_artifact):
            raise ArtifactError(
                "translation_revision 与 translation_artifact 必须同时存在"
            )
        if self.stage == "created" and (has_source or has_translation):
            raise ArtifactError("待提取任务不能声明原文或译文修订")
        if self.stage != "created" and not has_source:
            raise ArtifactError(f"任务阶段 {self.stage!r} 缺少原文修订")
        if self.stage == "extracted" and has_translation:
            raise ArtifactError("已提取任务不能声明译文修订")
        if self.stage in {"translation_partial", "translated", "exported"} and not has_translation:
            raise ArtifactError(f"任务阶段 {self.stage!r} 缺少译文修订")
        if self.stage == "exported":
            if not self.output_revision or set(self.outputs) != {
                "translated",
                "bilingual",
            }:
                raise ArtifactError("已导出任务缺少完整输出修订")
        elif self.output_revision is not None or self.outputs:
            raise ArtifactError("未导出任务不能声明输出文件")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "input_filename": self.input_filename,
            "input_sha256": self.input_sha256,
            "stage": self.stage,
            "source_revision": self.source_revision,
            "source_artifact": self.source_artifact,
            "translation_revision": self.translation_revision,
            "translation_artifact": self.translation_artifact,
            "output_revision": self.output_revision,
            "outputs": self.outputs,
            "operation": self.operation,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "JobManifest":
        if not isinstance(value, dict):
            raise ArtifactError("任务 manifest 必须是对象")
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ArtifactError(
                f"不支持的任务 manifest 版本: {value.get('schema_version')!r}"
            )
        required_strings = ("job_id", "input_filename", "input_sha256", "stage")
        for key in required_strings:
            if not isinstance(value.get(key), str) or not value[key]:
                raise ArtifactError(f"任务 manifest 缺少 {key}")
        outputs = value.get("outputs", {})
        operation = value.get("operation", {"status": "idle", "kind": None})
        if not isinstance(outputs, dict):
            raise ArtifactError("任务 manifest outputs 非法")
        return cls(
            job_id=value["job_id"],
            input_filename=value["input_filename"],
            input_sha256=value["input_sha256"],
            stage=value["stage"],
            source_revision=value.get("source_revision"),
            source_artifact=value.get("source_artifact"),
            translation_revision=value.get("translation_revision"),
            translation_artifact=value.get("translation_artifact"),
            output_revision=value.get("output_revision"),
            outputs=dict(outputs),
            operation=_json_value(operation, "任务操作状态"),
        )

    def with_source(self, source: SourceArtifact, filename: str) -> "JobManifest":
        return replace(
            self,
            input_sha256=source.input_sha256,
            stage="extracted",
            source_revision=source.source_revision,
            source_artifact=filename,
            translation_revision=None,
            translation_artifact=None,
            output_revision=None,
            outputs={},
            operation={"status": "idle", "kind": None},
        )

    def with_translation(
        self,
        translation: TranslationArtifact,
        filename: str,
        complete: bool,
    ) -> "JobManifest":
        return replace(
            self,
            stage="translated" if complete else "translation_partial",
            translation_revision=translation.translation_revision,
            translation_artifact=filename,
            output_revision=None,
            outputs={},
            operation={"status": "idle", "kind": None},
        )

    def with_outputs(
        self,
        translated: str,
        bilingual: str,
        output_revision: str,
    ) -> "JobManifest":
        if not self.translation_revision:
            raise ArtifactError("没有 translation_revision，不能发布输出")
        return replace(
            self,
            stage="exported",
            output_revision=output_revision,
            outputs={"translated": translated, "bilingual": bilingual},
            operation={"status": "idle", "kind": None},
        )
