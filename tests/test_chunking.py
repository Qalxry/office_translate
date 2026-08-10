"""分块逻辑测试：按行划分、不截断行、引擎差异。"""

from office_translate.ai.chunking import chunk_for_engine, split_by_lines


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
