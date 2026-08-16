"""Strict contracts for model translation output and operation outcomes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping
import xml.etree.ElementTree as ET


TRANSLATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "minimum": 0},
                    "translation": {"type": "string"},
                    "uncertain_terms": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "term": {"type": "string"},
                                "reason": {"type": "string"},
                                "candidate": {"type": "string"},
                            },
                            "required": ["term", "reason", "candidate"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["id", "translation", "uncertain_terms"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

SUMMARY_KEYS = {
    "status",
    "total",
    "succeeded",
    "failed",
    "cancelled",
    "succeeded_ids",
    "failed_ids",
    "cancelled_ids",
}
SUMMARY_STATUSES = {"succeeded", "partial", "failed", "cancelled"}


class OutputContractError(ValueError):
    """The provider completed, but its output cannot be trusted."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        diagnostic: Any = None,
        retryable: bool = True,
    ):
        super().__init__(message)
        self.code = code
        self.diagnostic = diagnostic
        self.retryable = retryable


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _strict_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        details = []
        if missing:
            details.append(f"缺少字段 {missing}")
        if unknown:
            details.append(f"包含未知字段 {unknown}")
        raise OutputContractError(
            "invalid_schema",
            f"{label}不符合严格 schema：{'；'.join(details)}",
        )


def _validate_expected_ids(expected_ids: Iterable[int]) -> tuple[int, ...]:
    expected = tuple(expected_ids)
    if len(set(expected)) != len(expected) or any(
        not _is_int(item_id) or item_id < 0 for item_id in expected
    ):
        raise OutputContractError("invalid_request", "期望 ID 集合非法")
    return expected


@dataclass(frozen=True)
class TranslationRequestItem:
    id: int
    text: str
    # Long source items may be split by the core chunker.  These fields are
    # deliberately optional so the GUI's existing id/text requests remain
    # unchanged, while a coordinator can carry enough information to safely
    # reassemble a segmented item after translation.
    source_id: int | None = None
    offset_start: int | None = None
    offset_end: int | None = None
    segment_index: int | None = None
    segment_count: int | None = None

    def __post_init__(self) -> None:
        if not _is_int(self.id) or self.id < 0:
            raise OutputContractError("invalid_request", f"非法输入 ID: {self.id!r}")
        if not isinstance(self.text, str):
            raise OutputContractError(
                "invalid_request", f"输入 {self.id} 的 text 必须是字符串"
            )
        metadata = (
            self.source_id,
            self.offset_start,
            self.offset_end,
            self.segment_index,
            self.segment_count,
        )
        if any(value is not None for value in metadata):
            if self.source_id is None or self.offset_start is None or self.offset_end is None:
                raise OutputContractError(
                    "invalid_request",
                    f"输入 {self.id} 的分段元数据必须包含 source_id/offset_start/offset_end",
                )
            if not all(_is_int(value) for value in metadata if value is not None):
                raise OutputContractError(
                    "invalid_request", f"输入 {self.id} 的分段元数据必须是整数"
                )
            if self.source_id < 0 or self.offset_start < 0 or self.offset_end < self.offset_start:
                raise OutputContractError(
                    "invalid_request", f"输入 {self.id} 的分段偏移非法"
                )
            if self.segment_index is None or self.segment_count is None:
                raise OutputContractError(
                    "invalid_request",
                    f"输入 {self.id} 的分段元数据必须包含 segment_index/segment_count",
                )
            if self.segment_count <= 0 or not 0 <= self.segment_index < self.segment_count:
                raise OutputContractError(
                    "invalid_request", f"输入 {self.id} 的分段序号非法"
                )

    def to_dict(self) -> dict[str, Any]:
        result = {"id": self.id, "text": self.text}
        if self.source_id is not None:
            result.update(
                {
                    "source_id": self.source_id,
                    "offset_start": self.offset_start,
                    "offset_end": self.offset_end,
                    "segment_index": self.segment_index,
                    "segment_count": self.segment_count,
                }
            )
        return result


@dataclass(frozen=True)
class TranslationResultItem:
    id: int
    translation: str
    uncertain_terms: tuple[dict[str, str], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "translation": self.translation,
            "uncertain_terms": [dict(term) for term in self.uncertain_terms],
        }


@dataclass(frozen=True)
class ProviderCompletion:
    """Provider completion metadata required before parsing model content."""

    content: str
    finish_reason: str | None
    refusal: Any = None
    raw_response: Any = None

    def require_complete(self) -> None:
        if self.refusal not in (None, "", False, []):
            raise OutputContractError(
                "refusal",
                "模型拒绝了翻译请求",
                diagnostic=self.diagnostic(),
            )
        if self.finish_reason == "length":
            raise OutputContractError(
                "truncated",
                "模型输出因长度限制被截断",
                diagnostic=self.diagnostic(),
            )
        if self.finish_reason != "stop":
            reason = self.finish_reason or "missing"
            raise OutputContractError(
                "incomplete_completion",
                f"模型没有正常结束（finish_reason={reason}）",
                diagnostic=self.diagnostic(),
            )
        if not isinstance(self.content, str) or not self.content.strip():
            raise OutputContractError(
                "empty_response",
                "模型返回了空响应",
                diagnostic=self.diagnostic(),
            )

    def diagnostic(self) -> dict[str, Any]:
        return {
            "finish_reason": self.finish_reason,
            "refusal": self.refusal,
            "raw_response": _json_safe(self.raw_response),
        }


def _json_safe(value: Any) -> Any:
    """Return JSON-only provider diagnostics without request secrets or headers."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            lowered = name.lower()
            if lowered in {
                "api_key",
                "apikey",
                "authorization",
                "headers",
                "request_headers",
            }:
                safe[name] = "[REDACTED]"
            else:
                safe[name] = _json_safe(item)
        return safe
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _json_safe(model_dump(mode="json"))
        except TypeError:
            return _json_safe(model_dump())
    return {"type": type(value).__name__}


def parse_translation_result(
    content: str,
    expected_ids: Iterable[int],
) -> tuple[TranslationResultItem, ...]:
    """Parse one complete JSON object and verify its exact item ID set."""
    expected = _validate_expected_ids(expected_ids)
    if not isinstance(content, str) or not content.strip():
        raise OutputContractError("empty_response", "模型返回了空响应")
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        raise OutputContractError(
            "malformed_json",
            f"模型输出不是完整 JSON：{exc.msg}",
            diagnostic={"content": content},
        ) from exc
    if not isinstance(value, dict):
        raise OutputContractError("invalid_schema", "模型输出根节点必须是对象")
    _strict_keys(value, {"items"}, "模型输出")
    return validate_result_items(value["items"], expected)


def validate_result_items(
    raw_items: Any,
    expected_ids: Iterable[int],
) -> tuple[TranslationResultItem, ...]:
    """Validate a list of result dicts against the strict ID-bearing schema."""
    expected = _validate_expected_ids(expected_ids)
    if not isinstance(raw_items, list):
        raise OutputContractError("invalid_schema", "模型输出 items 必须是数组")

    parsed: list[TranslationResultItem] = []
    seen: set[int] = set()
    for index, raw in enumerate(raw_items):
        item = validate_result_item(raw, index)
        if item.id in seen:
            raise OutputContractError("duplicate_id", f"模型输出 ID 重复: {item.id}")
        seen.add(item.id)
        parsed.append(item)

    actual = set(seen)
    expected_set = set(expected)
    missing = sorted(expected_set - actual)
    unknown = sorted(actual - expected_set)
    if missing or unknown:
        details = []
        if missing:
            details.append(f"缺少 ID {missing}")
        if unknown:
            details.append(f"未知 ID {unknown}")
        raise OutputContractError("id_set_mismatch", "模型输出 ID 集合不完整：" + "；".join(details))
    by_id = {item.id: item for item in parsed}
    return tuple(by_id[item_id] for item_id in expected)


def validate_result_item(raw: Any, index: int = 0) -> TranslationResultItem:
    """Validate one result dict; does not check the full ID set."""
    if not isinstance(raw, dict):
        raise OutputContractError(
            "invalid_schema", f"模型输出 items[{index}] 必须是对象"
        )
    _strict_keys(raw, {"id", "translation", "uncertain_terms"}, f"items[{index}]")
    item_id = raw["id"]
    if not _is_int(item_id) or item_id < 0:
        raise OutputContractError(
            "invalid_schema", f"items[{index}].id 必须是非负整数"
        )
    translation = raw["translation"]
    if not isinstance(translation, str):
        raise OutputContractError(
            "invalid_schema", f"items[{index}].translation 必须是字符串"
        )
    raw_terms = raw["uncertain_terms"]
    if not isinstance(raw_terms, list):
        raise OutputContractError(
            "invalid_schema", f"items[{index}].uncertain_terms 必须是数组"
        )
    terms: list[dict[str, str]] = []
    for term_index, term in enumerate(raw_terms):
        if not isinstance(term, dict):
            raise OutputContractError(
                "invalid_schema",
                f"items[{index}].uncertain_terms[{term_index}] 必须是对象",
            )
        _strict_keys(
            term,
            {"term", "reason", "candidate"},
            f"items[{index}].uncertain_terms[{term_index}]",
        )
        if not all(isinstance(term[name], str) for name in ("term", "reason", "candidate")):
            raise OutputContractError(
                "invalid_schema",
                f"items[{index}].uncertain_terms[{term_index}] 字段必须都是字符串",
            )
        terms.append(
            {
                "term": term["term"],
                "reason": term["reason"],
                "candidate": term["candidate"],
            }
        )
    return TranslationResultItem(
        id=item_id,
        translation=translation,
        uncertain_terms=tuple(terms),
    )


_XML_ENTITY_RE = re.compile(r"&(?:#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);")


def _escape_bare_ampersands(xml_text: str) -> str:
    """Escape bare & characters that would make XML invalid.

    CDATA sections are skipped so their content is not modified. This repairs
    common model mistakes without relaxing structural validation afterwards.
    """
    out: list[str] = []
    i = 0
    while i < len(xml_text):
        if xml_text.startswith("<![CDATA[", i):
            end = xml_text.find("]]>", i + 9)
            if end < 0:
                out.append(xml_text[i:])
                break
            out.append(xml_text[i : end + 3])
            i = end + 3
            continue
        if xml_text[i] == "&":
            match = _XML_ENTITY_RE.match(xml_text, i)
            if match:
                out.append(match.group(0))
                i = match.end()
                continue
            out.append("&amp;")
            i += 1
            continue
        out.append(xml_text[i])
        i += 1
    return "".join(out)


def parse_translation_result_xml(
    content: str,
    expected_ids: Iterable[int],
) -> tuple[TranslationResultItem, ...]:
    """Parse one complete ID-bearing XML document and verify its exact item set."""
    expected = _validate_expected_ids(expected_ids)
    if not isinstance(content, str) or not content.strip():
        raise OutputContractError("empty_response", "模型返回了空响应")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        repaired = _escape_bare_ampersands(content)
        if repaired == content:
            raise OutputContractError(
                "malformed_xml",
                f"模型输出不是完整 XML：{exc}",
                diagnostic={"content": content},
            ) from exc
        try:
            root = ET.fromstring(repaired)
        except ET.ParseError as exc2:
            raise OutputContractError(
                "malformed_xml",
                f"模型输出不是完整 XML：{exc2}",
                diagnostic={"content": content, "repaired": repaired},
            ) from exc2
    if root.tag != "items" or root.attrib:
        raise OutputContractError(
            "invalid_schema", "XML 根节点必须是 <items> 且无属性"
        )

    raw_items: list[dict[str, Any]] = []
    for child in root:
        if child.tag != "item":
            raise OutputContractError(
                "invalid_schema", f"<items> 包含未知元素 <{child.tag}>"
            )
        if set(child.attrib) != {"id"}:
            raise OutputContractError(
                "invalid_schema", "<item> 必须只有 id 属性"
            )
        try:
            item_id = int(child.attrib["id"])
        except ValueError:
            item_id = -1
        if not _is_int(item_id) or item_id < 0:
            raise OutputContractError(
                "invalid_schema",
                f"<item id={child.attrib['id']!r}> 的 id 必须是非负整数",
            )
        if child.text and child.text.strip():
            raise OutputContractError(
                "invalid_schema", "<item> 不能包含非空白文本"
            )

        translation_el: Any = None
        terms_el: Any = None
        for sub in child:
            if translation_el is None and sub.tag == "translation":
                translation_el = sub
            elif terms_el is None and sub.tag == "uncertain_terms":
                terms_el = sub
            else:
                raise OutputContractError(
                    "invalid_schema",
                    f"<item> 包含未知或重复元素 <{sub.tag}>",
                )
        if translation_el is None or terms_el is None:
            raise OutputContractError(
                "invalid_schema",
                "<item> 必须包含 translation 和 uncertain_terms 两个子元素",
            )
        if translation_el.attrib or list(translation_el):
            raise OutputContractError(
                "invalid_schema", "<translation> 不能有属性或子元素"
            )
        if terms_el.attrib or (terms_el.text and terms_el.text.strip()):
            raise OutputContractError(
                "invalid_schema", "<uncertain_terms> 不能有属性或非空白文本"
            )

        terms: list[dict[str, str]] = []
        for term in terms_el:
            if term.tag != "term" or list(term) or (term.text and term.text.strip()):
                raise OutputContractError(
                    "invalid_schema",
                    "<uncertain_terms> 的子元素必须是空的 <term>",
                )
            if set(term.attrib) != {"term", "reason", "candidate"}:
                raise OutputContractError(
                    "invalid_schema", "<term> 必须只有 term/reason/candidate 属性"
                )
            terms.append(
                {name: term.attrib[name] for name in ("term", "reason", "candidate")}
            )
        raw_items.append(
            {
                "id": item_id,
                "translation": translation_el.text or "",
                "uncertain_terms": terms,
            }
        )
    return validate_result_items(raw_items, expected)


_TEXT_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "f": "\f",
    "v": "\v",
    "b": "\b",
    "0": "\0",
    "\\": "\\",
}


def escape_text_line(text: str) -> str:
    """Escape every non-space whitespace and backslash for the text protocol."""
    out: list[str] = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\v":
            out.append("\\v")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\0":
            out.append("\\0")
        else:
            out.append(ch)
    return "".join(out)


def decode_text_line(line: str) -> str:
    """Decode literal \\n/\\t/\\r/\\\\ escapes from one text-protocol line."""
    out: list[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= len(line):
            raise OutputContractError("malformed_escape", "文本行以未完成的转义结尾")
        esc = line[i + 1]
        if esc not in _TEXT_ESCAPES:
            raise OutputContractError(
                "malformed_escape", f"文本行包含未知转义序列 \\{esc}"
            )
        out.append(_TEXT_ESCAPES[esc])
        i += 2
    return "".join(out)


_SEQUENCE_PREFIX_RE = re.compile(
    r"^(?:\[\d{1,4}\]\s+|\d{1,4}\s*[、．]\s*|\d{1,4}\s*[.)）]\s+)"
)


def strip_text_sequence_prefix(line: str) -> str:
    """Remove a leading sequence number such as '1. ' or '[2] '.

    Only prefixes followed by whitespace are removed, so legitimate content
    like '1.5 版本' or '2024年' is untouched. If stripping would leave an
    empty line, the original line is kept instead of losing content.
    """
    stripped = _SEQUENCE_PREFIX_RE.sub("", line, count=1)
    return stripped if stripped else line


def parse_translation_text(
    content: str,
    expected_ids: Iterable[int],
) -> tuple[TranslationResultItem, ...]:
    """Parse the strict line-per-item text protocol.

    Each output line maps to one input item in order. Line-internal line
    breaks, tabs, and other non-space whitespace must be escaped with literal
    sequences such as \\n and \\t, and are decoded back after line counting.
    """
    expected = _validate_expected_ids(expected_ids)
    if not isinstance(content, str) or content == "":
        raise OutputContractError("empty_response", "模型返回了空响应")
    if content.endswith("\n"):
        content = content[:-1]
    lines = content.split("\n")
    if len(lines) != len(expected):
        raise OutputContractError(
            "line_count_mismatch",
            f"文本输出行数 {len(lines)} 与输入条数 {len(expected)} 不一致",
        )
    parsed: list[TranslationResultItem] = []
    for item_id, line in zip(expected, lines):
        try:
            translation = strip_text_sequence_prefix(decode_text_line(line))
        except OutputContractError as exc:
            exc.diagnostic = {"line_index": item_id, "line": line}
            raise
        parsed.append(
            TranslationResultItem(
                id=item_id,
                translation=translation,
                uncertain_terms=(),
            )
        )
    return tuple(parsed)


def parse_result_by_format(
    content: str,
    expected_ids: Iterable[int],
    output_format: str,
) -> tuple[TranslationResultItem, ...]:
    """Parse model output using the strict parser for the selected protocol."""
    if output_format == "json":
        return parse_translation_result(content, expected_ids)
    if output_format == "xml":
        return parse_translation_result_xml(content, expected_ids)
    if output_format == "text":
        return parse_translation_text(content, expected_ids)
    raise OutputContractError("invalid_request", f"未知输出格式: {output_format!r}")


@dataclass(frozen=True)
class TranslationBlockResult:
    status: str
    expected_ids: tuple[int, ...]
    items: tuple[TranslationResultItem, ...] = field(default_factory=tuple)
    error_code: str | None = None
    error: str | None = None
    diagnostic: Any = None
    thinking: str = ""

    def __post_init__(self) -> None:
        if self.status not in {"succeeded", "failed", "cancelled"}:
            raise OutputContractError("invalid_block", f"非法块状态: {self.status!r}")
        if self.status == "succeeded":
            if tuple(item.id for item in self.items) != self.expected_ids:
                raise OutputContractError("invalid_block", "成功块的结果 ID 不完整")
            if self.error_code or self.error:
                raise OutputContractError("invalid_block", "成功块不能携带失败信息")
        elif self.items:
            raise OutputContractError("invalid_block", "失败或取消块不能携带成功条目")


@dataclass(frozen=True)
class OperationSummary:
    status: str
    total: int
    succeeded: int
    failed: int
    cancelled: int
    succeeded_ids: tuple[int, ...]
    failed_ids: tuple[int, ...]
    cancelled_ids: tuple[int, ...]

    @classmethod
    def from_outcomes(
        cls,
        expected_ids: Iterable[int],
        *,
        succeeded_ids: Iterable[int] = (),
        failed_ids: Iterable[int] = (),
        cancelled_ids: Iterable[int] = (),
    ) -> "OperationSummary":
        expected = tuple(expected_ids)
        succeeded = tuple(sorted(succeeded_ids))
        failed = tuple(sorted(failed_ids))
        cancelled = tuple(sorted(cancelled_ids))
        if len(set(expected)) != len(expected):
            raise OutputContractError("invalid_summary", "summary 的期望 ID 重复")
        outcomes = succeeded + failed + cancelled
        if len(set(outcomes)) != len(outcomes) or set(outcomes) != set(expected):
            raise OutputContractError(
                "invalid_summary", "summary 的成功、失败和取消 ID 必须恰好覆盖全部输入"
            )
        total = len(expected)
        if len(succeeded) == total:
            status = "succeeded"
        elif len(failed) == total:
            status = "failed"
        elif len(cancelled) == total:
            status = "cancelled"
        else:
            status = "partial"
        return cls(
            status=status,
            total=total,
            succeeded=len(succeeded),
            failed=len(failed),
            cancelled=len(cancelled),
            succeeded_ids=succeeded,
            failed_ids=failed,
            cancelled_ids=cancelled,
        )

    @classmethod
    def from_dict(
        cls,
        value: Any,
        expected_ids: Iterable[int] | None = None,
    ) -> "OperationSummary":
        if not isinstance(value, dict):
            raise OutputContractError("invalid_summary", "summary 必须是对象")
        _strict_keys(value, SUMMARY_KEYS, "summary")
        for name in ("total", "succeeded", "failed", "cancelled"):
            if not _is_int(value[name]) or value[name] < 0:
                raise OutputContractError(
                    "invalid_summary", f"summary.{name} 必须是非负整数"
                )
        if value["status"] not in SUMMARY_STATUSES:
            raise OutputContractError("invalid_summary", "summary.status 非法")
        id_fields: dict[str, tuple[int, ...]] = {}
        for name in ("succeeded_ids", "failed_ids", "cancelled_ids"):
            ids = value[name]
            if not isinstance(ids, list) or any(
                not _is_int(item_id) or item_id < 0 for item_id in ids
            ):
                raise OutputContractError(
                    "invalid_summary", f"summary.{name} 必须是非负整数数组"
                )
            id_fields[name] = tuple(ids)
        if value["total"] != value["succeeded"] + value["failed"] + value["cancelled"]:
            raise OutputContractError(
                "invalid_summary", "summary 计数不满足 total=succeeded+failed+cancelled"
            )
        if value["succeeded"] != len(id_fields["succeeded_ids"]):
            raise OutputContractError("invalid_summary", "summary.succeeded 计数不一致")
        if value["failed"] != len(id_fields["failed_ids"]):
            raise OutputContractError("invalid_summary", "summary.failed 计数不一致")
        if value["cancelled"] != len(id_fields["cancelled_ids"]):
            raise OutputContractError("invalid_summary", "summary.cancelled 计数不一致")
        expected = (
            tuple(expected_ids)
            if expected_ids is not None
            else tuple(range(value["total"]))
        )
        created = cls.from_outcomes(
            expected,
            succeeded_ids=id_fields["succeeded_ids"],
            failed_ids=id_fields["failed_ids"],
            cancelled_ids=id_fields["cancelled_ids"],
        )
        if created.to_dict() != value:
            raise OutputContractError(
                "invalid_summary", "summary.status、计数或 ID 排序与结果不一致"
            )
        return created

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "succeeded_ids": list(self.succeeded_ids),
            "failed_ids": list(self.failed_ids),
            "cancelled_ids": list(self.cancelled_ids),
        }
