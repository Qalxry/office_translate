"""Context-safe translation chunking.

The old implementation only approximated a character limit and deliberately
left a single overlong line untouched.  That is unsafe for an LLM request:
the system prompt, glossary, output schema, and completion budget all consume
the same context window.  This module keeps the small ``chunk_for_engine``
API used by the GUI, and also exposes ``chunk_request_items`` for callers that
need lossless IDs and offsets when a source item is segmented.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Iterable, Mapping

from .contracts import OutputContractError, TranslationRequestItem


class ChunkingError(OutputContractError):
    """The requested context budget cannot safely represent an input item."""


def _estimate_tokens(text: str) -> int:
    """Conservative, deterministic token estimate for mixed-language text.

    This is intentionally an upper-bound-ish estimate rather than a claim to
    emulate a vendor tokenizer.  ASCII runs are charged at two characters per
    token; CJK and other non-ASCII characters are charged one token each.  A
    caller can therefore stay below its configured context on both CJK and
    mixed text without relying on the accidental behavior of ``len(text)``.
    """
    if not isinstance(text, str):
        raise ChunkingError("invalid_request", "分块输入必须是字符串")
    tokens = 0
    ascii_run = 0
    for char in text:
        if ord(char) < 128:
            ascii_run += 1
            continue
        if ascii_run:
            tokens += math.ceil(ascii_run / 2)
            ascii_run = 0
        tokens += 1
    if ascii_run:
        tokens += math.ceil(ascii_run / 2)
    return max(1, tokens) if text else 0


estimate_tokens = _estimate_tokens


@dataclass(frozen=True)
class ChunkBudget:
    """The complete accounting used to build one provider request."""

    context_tokens: int
    input_tokens: int
    output_tokens: int
    system_tokens: int
    prompt_tokens: int
    glossary_tokens: int
    schema_tokens: int

    @property
    def reserved_tokens(self) -> int:
        return (
            self.output_tokens
            + self.system_tokens
            + self.prompt_tokens
            + self.glossary_tokens
            + self.schema_tokens
        )

    def assert_fits(self, input_tokens: int) -> None:
        if input_tokens > self.input_tokens:
            raise ChunkingError(
                "context_budget_exceeded",
                f"输入估算 token 数 {input_tokens} 超过可用预算 {self.input_tokens}",
                diagnostic={"budget": asdict(self)},
            )


def calculate_chunk_budget(
    model_context: int,
    *,
    system_prompt: str = "",
    glossary: str = "",
    output_format: str = "xml",
    max_output_tokens: int | None = None,
    llm_ratio: float = 0.75,
    prompt_overhead_tokens: int = 64,
) -> ChunkBudget:
    """Calculate an input budget with all non-input context reserved.

    ``llm_ratio`` remains as a product-level safety cap.  An explicit
    ``max_output_tokens`` is additionally honored, so output reservation can
    never be accidentally ignored by a ratio-only calculation.
    """
    if not isinstance(model_context, int) or isinstance(model_context, bool) or model_context <= 0:
        raise ChunkingError("invalid_config", "model_context 必须是正整数")
    if not 0 < llm_ratio <= 1:
        raise ChunkingError("invalid_config", "llm_ratio 必须在 (0, 1] 范围内")
    if not isinstance(prompt_overhead_tokens, int) or prompt_overhead_tokens < 0:
        raise ChunkingError("invalid_config", "prompt_overhead_tokens 必须是非负整数")
    if max_output_tokens is not None:
        if (
            not isinstance(max_output_tokens, int)
            or isinstance(max_output_tokens, bool)
            or max_output_tokens <= 0
        ):
            raise ChunkingError("invalid_config", "max_output_tokens 必须是正整数")
        output_tokens = max_output_tokens
    else:
        # The historical 75% input ratio implies a 25% completion reserve.
        output_tokens = max(1, int(model_context * (1 - llm_ratio)))
    system_tokens = _estimate_tokens(system_prompt) if system_prompt else 256
    glossary_tokens = _estimate_tokens(glossary) if glossary else 0
    schema_tokens = {
        "json": 192,
        "xml": 128,
        "text": 32,
    }.get(output_format)
    if schema_tokens is None:
        raise ChunkingError("invalid_request", f"未知输出格式: {output_format!r}")
    input_tokens = (
        model_context
        - output_tokens
        - system_tokens
        - prompt_overhead_tokens
        - glossary_tokens
        - schema_tokens
    )
    if input_tokens < 1:
        raise ChunkingError(
            "context_budget_exceeded",
            "模型上下文不足以同时容纳系统提示、术语库、输出协议和输出预算",
            diagnostic={
                "context_tokens": model_context,
                "reserved_tokens": model_context - input_tokens,
            },
        )
    # Never exceed the ratio cap even when a small explicit output budget was
    # supplied.  This preserves a little room for provider-specific overhead.
    input_tokens = min(input_tokens, max(1, int(model_context * llm_ratio)))
    return ChunkBudget(
        context_tokens=model_context,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        system_tokens=system_tokens,
        prompt_tokens=prompt_overhead_tokens,
        glossary_tokens=glossary_tokens,
        schema_tokens=schema_tokens,
    )


def _split_text_to_tokens(text: str, max_tokens: int) -> list[tuple[str, int, int]]:
    """Split one item into contiguous, non-empty UTF-8 text segments."""
    if max_tokens <= 0:
        raise ChunkingError("context_budget_exceeded", "单条文本没有可用输入预算")
    if not text:
        return [("", 0, 0)]
    if _estimate_tokens(text) <= max_tokens:
        return [(text, 0, len(text))]

    segments: list[tuple[str, int, int]] = []
    start = 0
    while start < len(text):
        low, high = start + 1, len(text)
        best = start
        while low <= high:
            mid = (low + high) // 2
            if _estimate_tokens(text[start:mid]) <= max_tokens:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        if best == start:
            raise ChunkingError(
                "context_budget_exceeded",
                "单个字符的估算 token 数超过可用输入预算，无法安全分段",
                diagnostic={"offset": start},
            )
        # Prefer a natural boundary without ever exceeding the hard budget.
        boundary = best
        for marker in ("\n", "。", "！", "？", ".", "!", "?", " ", "，", ","):
            candidate = text.rfind(marker, start + 1, best)
            if candidate >= start:
                boundary = candidate + 1
                break
        part = text[start:boundary]
        segments.append((part, start, boundary))
        start = boundary
    return segments


_ITEM_OVERHEAD_TOKENS = 8


def _pack_items(
    items: Iterable[TranslationRequestItem],
    max_tokens: int,
    *,
    max_chars: int | None = None,
) -> list[list[TranslationRequestItem]]:
    chunks: list[list[TranslationRequestItem]] = []
    current: list[TranslationRequestItem] = []
    token_count = 0
    char_count = 0
    for item in items:
        item_tokens = _estimate_tokens(item.text)
        item_chars = len(item.text)
        if item_tokens + _ITEM_OVERHEAD_TOKENS > max_tokens:
            raise ChunkingError(
                "context_budget_exceeded",
                f"输入 ID {item.id} 在当前请求预算中仍然过长",
                diagnostic={"id": item.id, "estimated_tokens": item_tokens, "budget_tokens": max_tokens},
            )
        would_exceed = current and (
            token_count + item_tokens + _ITEM_OVERHEAD_TOKENS > max_tokens
            or (max_chars is not None and char_count + item_chars > max_chars)
        )
        if would_exceed:
            chunks.append(current)
            current = []
            token_count = 0
            char_count = 0
        current.append(item)
        token_count += item_tokens + _ITEM_OVERHEAD_TOKENS
        char_count += item_chars
    if current:
        chunks.append(current)
    return chunks


def chunk_request_items(
    items: list[TranslationRequestItem],
    engine: str,
    *,
    model_context: int | None = None,
    google_max_chars: int = 4500,
    system_prompt: str = "",
    glossary: str = "",
    output_format: str = "xml",
    max_output_tokens: int | None = None,
    llm_ratio: float = 0.75,
) -> list[list[TranslationRequestItem]]:
    """Chunk ID-bearing items and safely segment an overlong source item.

    Segmented items receive deterministic generated IDs and carry the original
    source ID plus half-open character offsets.  The original item IDs are
    retained for items that do not need segmentation.  Use
    :func:`reassemble_segments` after provider results return.
    """
    if not isinstance(items, list) or any(not isinstance(item, TranslationRequestItem) for item in items):
        raise ChunkingError("invalid_request", "items 必须是 TranslationRequestItem 数组")
    if engine not in {"google", "openai"}:
        raise ChunkingError("invalid_request", f"未知翻译引擎: {engine!r}")
    if len({item.id for item in items}) != len(items):
        raise ChunkingError("invalid_request", "输入 ID 不能重复")

    if engine == "google":
        if not isinstance(google_max_chars, int) or google_max_chars <= 0:
            raise ChunkingError("invalid_config", "google_max_chars 必须是正整数")
        # Google is constrained by query characters rather than an LLM token
        # context.  Keep token packing effectively unbounded and enforce chars.
        max_tokens = 2**63 - 1
        max_chars = max(1, google_max_chars - 1)
    else:
        if model_context is None:
            # A bounded default is safer than the old unlimited single-line
            # behavior, while callers with model metadata get exact accounting.
            max_tokens = 2000
            max_chars = None
        else:
            budget = calculate_chunk_budget(
                model_context,
                system_prompt=system_prompt,
                glossary=glossary,
                output_format=output_format,
                max_output_tokens=max_output_tokens,
                llm_ratio=llm_ratio,
            )
            max_tokens = budget.input_tokens
            max_chars = None

    next_id = max((item.id for item in items), default=-1) + 1
    expanded: list[TranslationRequestItem] = []
    for item in items:
        if engine == "google":
            parts = []
            start = 0
            segment_chars = max(1, google_max_chars - 1)
            while start < len(item.text):
                end = min(len(item.text), start + segment_chars)
                parts.append((item.text[start:end], start, end))
                start = end
            if not parts:
                parts = [("", 0, 0)]
        else:
            parts = _split_text_to_tokens(
                item.text, max(1, max_tokens - _ITEM_OVERHEAD_TOKENS)
            )
        if len(parts) == 1:
            expanded.append(item)
            continue
        segment_count = len(parts)
        for segment_index, (part, start, end) in enumerate(parts):
            expanded.append(
                TranslationRequestItem(
                    id=next_id,
                    text=part,
                    source_id=item.id,
                    offset_start=start,
                    offset_end=end,
                    segment_index=segment_index,
                    segment_count=segment_count,
                )
            )
            next_id += 1

    return _pack_items(expanded, max_tokens, max_chars=max_chars)


def validate_segment_offsets(
    segments: Iterable[TranslationRequestItem],
    source_texts: Mapping[int, str] | None = None,
) -> dict[int, tuple[TranslationRequestItem, ...]]:
    """Validate that segmented items form contiguous, non-overlapping inputs."""
    grouped: dict[int, list[TranslationRequestItem]] = {}
    for item in segments:
        if item.source_id is None:
            continue
        grouped.setdefault(item.source_id, []).append(item)
    result: dict[int, tuple[TranslationRequestItem, ...]] = {}
    for source_id, values in grouped.items():
        ordered = sorted(values, key=lambda value: value.offset_start or 0)
        expected_count = ordered[0].segment_count
        if expected_count != len(ordered) or any(
            value.segment_count != expected_count for value in ordered
        ):
            raise ChunkingError("segment_reassembly_invalid", "分段数量不一致")
        cursor = 0
        for value in ordered:
            if value.offset_start != cursor or value.offset_end != cursor + len(value.text):
                raise ChunkingError(
                    "segment_reassembly_invalid",
                    f"源 ID {source_id} 的分段偏移不连续",
                )
            cursor = value.offset_end
        if source_texts is not None:
            source = source_texts.get(source_id)
            if source is None or len(source) != cursor:
                raise ChunkingError(
                    "segment_reassembly_invalid",
                    f"源 ID {source_id} 的分段无法覆盖原文",
                )
        result[source_id] = tuple(ordered)
    return result


def reassemble_segments(
    segments: Iterable[TranslationRequestItem],
    translations: Mapping[int, str],
    source_texts: Mapping[int, str] | None = None,
) -> dict[int, str]:
    """Validate and concatenate translated segments in source order."""
    grouped = validate_segment_offsets(segments, source_texts)
    result: dict[int, str] = {}
    for source_id, values in grouped.items():
        parts: list[str] = []
        for value in values:
            translation = translations.get(value.id)
            if not isinstance(translation, str):
                raise ChunkingError(
                    "segment_reassembly_invalid",
                    f"缺少源 ID {source_id} 的分段结果 {value.id}",
                )
            parts.append(translation)
        result[source_id] = "".join(parts)
    return result


def split_by_lines(texts: list[str], max_chars: int) -> list[list[str]]:
    """Pack complete lines; a single oversized line remains intact.

    This low-level helper intentionally preserves its historical behavior.
    Use ``chunk_for_engine`` or ``chunk_request_items`` for provider-safe
    splitting of oversized items.
    """
    if not isinstance(max_chars, int) or max_chars <= 0:
        raise ChunkingError("invalid_config", "max_chars 必须是正整数")
    chunks: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for line in texts:
        if not isinstance(line, str):
            raise ChunkingError("invalid_request", "分块输入必须是字符串数组")
        line_len = len(line) + 1
        if line_len > max_chars:
            if current:
                chunks.append(current)
                current = []
                current_len = 0
            chunks.append([line])
            continue
        if current_len + line_len > max_chars and current:
            chunks.append(current)
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append(current)
    return chunks


def chunk_for_engine(
    texts: list[str],
    engine: str,
    model_context: int | None = None,
    google_max_chars: int = 4500,
    llm_ratio: float = 0.75,
    *,
    system_prompt: str = "",
    glossary: str = "",
    output_format: str = "xml",
    max_output_tokens: int | None = None,
) -> list[list[str]]:
    """Return provider-safe text chunks while retaining the small GUI API.

    For callers that need IDs/offsets, use ``chunk_request_items``.  This
    convenience function returns only text and therefore cannot be used to
    reassemble a segmented item by itself.
    """
    items = [TranslationRequestItem(id=index, text=text) for index, text in enumerate(texts)]
    chunks = chunk_request_items(
        items,
        engine,
        model_context=model_context,
        google_max_chars=google_max_chars,
        system_prompt=system_prompt,
        glossary=glossary,
        output_format=output_format,
        max_output_tokens=max_output_tokens,
        llm_ratio=llm_ratio,
    )
    return [[item.text for item in chunk] for chunk in chunks]
