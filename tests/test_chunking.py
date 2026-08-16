"""分块逻辑测试：预算核算、混合文本和可重组长文本分段。"""

import pytest

from office_translate.ai.chunking import (
    ChunkingError,
    calculate_chunk_budget,
    chunk_for_engine,
    chunk_request_items,
    estimate_tokens,
    reassemble_segments,
    split_by_lines,
)
from office_translate.ai.contracts import TranslationRequestItem


def test_split_by_lines_basic():
    texts = ["a", "bb", "ccc", "dddd", "eeeee"]
    # 每块最多 6 字符（含换行），应分成多块
    chunks = split_by_lines(texts, max_chars=6)
    # 行数不变
    assert sum(len(c) for c in chunks) == len(texts)
    # 每块不超过 6 字符（单行超长除外）
    for c in chunks:
        total = sum(len(l) + 1 for l in c)
        assert total <= 6


def test_split_by_lines_no_midline_break():
    """分块绝不能把一行从中间截断。"""
    texts = ["line one", "line two", "line three"]
    chunks = split_by_lines(texts, max_chars=10)
    flat = [l for c in chunks for l in c]
    assert flat == texts  # 行完整保留


def test_split_single_long_line():
    """单行超长应单独成块，不截断。"""
    long_line = "x" * 100
    chunks = split_by_lines([long_line], max_chars=10)
    assert chunks == [[long_line]]  # 完整保留


def test_chunk_for_google_by_chars():
    texts = ["a" * 100, "b" * 100, "c" * 100]
    chunks = chunk_for_engine(texts, "google", google_max_chars=150)
    assert sum(len(c) for c in chunks) == 3
    # 每块接近但不超过 150 字符
    for c in chunks:
        assert sum(len(l) + 1 for l in c) <= 150


def test_chunk_for_llm_by_context():
    texts = ["line" * 50 for _ in range(100)]  # 每行 200 字符
    # 模型上下文 8000 token → 75% = 6000 token → 约 12000 字符
    chunks = chunk_for_engine(texts, "openai", model_context=8000)
    flat = [l for c in chunks for l in c]
    assert flat == texts  # 行完整
    assert len(chunks) > 1  # 确实分块了
    # 每块字符数应在限制内
    for c in chunks:
        chars = sum(len(l) + 1 for l in c)
        assert chars <= 8000 * 0.75 * 2 + 500  # 宽松上限


def test_chunk_for_llm_no_context_default():
    texts = ["a" * 100] * 200
    chunks = chunk_for_engine(texts, "openai", model_context=None)
    assert sum(len(c) for c in chunks) == 200


def test_context_budget_reserves_prompt_glossary_schema_and_output():
    budget = calculate_chunk_budget(
        4096,
        system_prompt="translate faithfully",
        glossary="PPB = parts per billion\n" * 20,
        output_format="json",
        max_output_tokens=768,
        prompt_overhead_tokens=80,
    )
    assert budget.output_tokens == 768
    assert budget.glossary_tokens == estimate_tokens("PPB = parts per billion\n" * 20)
    assert budget.schema_tokens > 0
    assert budget.input_tokens + budget.reserved_tokens <= budget.context_tokens


def test_large_glossary_fails_before_any_oversized_request_is_built():
    with pytest.raises(ChunkingError) as caught:
        calculate_chunk_budget(
            1024,
            glossary="术语=译词\n" * 1000,
            max_output_tokens=128,
        )
    assert caught.value.code == "context_budget_exceeded"


def test_cjk_and_mixed_text_chunks_stay_inside_calculated_budget():
    context = 2048
    glossary = "术语=terminology\n" * 10
    budget = calculate_chunk_budget(
        context,
        glossary=glossary,
        max_output_tokens=256,
    )
    texts = [
        "中文句子，包含标点。" * 80,
        "mixed English 与中文 12345 " * 80,
        "ASCII only sentence. " * 100,
    ]
    chunks = chunk_for_engine(
        texts,
        "openai",
        model_context=context,
        glossary=glossary,
        max_output_tokens=256,
    )
    assert len(chunks) > 1
    for chunk in chunks:
        assert sum(estimate_tokens(text) + 8 for text in chunk) <= budget.input_tokens


def test_long_item_is_split_with_ids_offsets_and_validated_reassembly():
    source = "长文本。" * 600
    chunks = chunk_request_items(
        [TranslationRequestItem(id=7, text=source)],
        "openai",
        model_context=1024,
        max_output_tokens=128,
    )
    segments = [item for chunk in chunks for item in chunk]
    assert len(segments) > 1
    assert len({item.id for item in segments}) == len(segments)
    assert all(item.source_id == 7 for item in segments)
    assert "".join(item.text for item in segments) == source
    assert [(item.offset_start, item.offset_end) for item in segments][0][0] == 0
    assert segments[-1].offset_end == len(source)

    translated = {item.id: f"<{item.segment_index}>" for item in segments}
    reassembled = reassemble_segments(segments, translated, {7: source})
    assert reassembled == {
        7: "".join(f"<{index}>" for index in range(len(segments)))
    }


def test_reassembly_rejects_missing_segment_result():
    source = "文" * 1000
    segments = [
        item
        for chunk in chunk_request_items(
            [TranslationRequestItem(id=3, text=source)],
            "openai",
            model_context=1024,
            max_output_tokens=128,
        )
        for item in chunk
    ]
    with pytest.raises(ChunkingError) as caught:
        reassemble_segments(
            segments,
            {item.id: "译" for item in segments[:-1]},
            {3: source},
        )
    assert caught.value.code == "segment_reassembly_invalid"
