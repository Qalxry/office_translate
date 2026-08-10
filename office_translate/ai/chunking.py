"""翻译分块：按行划分、避免行中间截断。

- LLM（DeepSeek 等）：按模型最大上下文的 75% 分块（token 估算）。
- Google：按字数分块。
- 分块边界永远在行末（\n），绝不在一行中间截断。
"""

from __future__ import annotations


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数：中文约 1.5 字符/token，英文约 4 字符/token。"""
    # 中文字符占 1 token，ASCII 约 4 字符 1 token
    cn = sum(1 for c in text if ord(c) > 0x2E7F)
    en = len(text) - cn
    return cn + int(en / 4) + 1


def split_by_lines(texts: list[str], max_chars: int) -> list[list[str]]:
    """按行划分文本，每块不超过 max_chars，绝不在一行中间截断。

    Args:
        texts: 待译文本（每元素一行，是源文件的一行）。
        max_chars: 每块最大字符数（按行边界调整）。

    Returns:
        分块后的块列表，每块是若干行的列表。
    """
    chunks: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for line in texts:
        line_len = len(line) + 1  # +1 换行
        # 单行超长则单独成块（无法避免）
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
) -> list[list[str]]:
    """按引擎分块。

    Args:
        texts: 待译文本（每元素一行）。
        engine: "google" 或 "openai"。
        model_context: 模型最大上下文 token 数（LLM 用，如 DeepSeek 128K）。
        google_max_chars: Google 每块最大字符数。
        llm_ratio: LLM 用上下文的多少比例（默认 75%）。

    Returns:
        分块后的块列表。
    """
    if engine == "google":
        return split_by_lines(texts, google_max_chars)
    # LLM：按模型上下文 75% 估算
    if model_context:
        max_tokens = int(model_context * llm_ratio)
        # 换算成字符：中英混合按 token 估算反推（保守取 2 字符/token）
        max_chars = max(500, max_tokens * 2)
    else:
        max_chars = 8000  # 默认（约 4K token）
    return split_by_lines(texts, max_chars)
