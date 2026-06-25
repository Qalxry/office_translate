"""文本转义工具。

txt 文件中「一行代表一条完整文本」是套件的核心约定。
为此把原始文本里的 CR / LF 转义成可见字面量，回写时再还原。

约定（与 Python 标准字符串转义一致，便于人工核对）：
    \r  ->  字面序列 反斜杠 + r
    \n  ->  字面序列 反斜杠 + n
    \\  ->  字面序列 反斜杠 + 反斜杠

`escape_text` 与 `unescape_text` 互为逆运算。
"""

from __future__ import annotations


def escape_text(text: str) -> str:
    """把原始文本转义为「单行安全」形式。

    处理顺序很关键：必须先处理反斜杠，再处理 CR/LF，
    否则会把上一步产生的反斜杠再次转义。
    """
    # 先把单独的反斜杠翻倍，避免后续产生的 \r \n 被误还原。
    text = text.replace("\\", "\\\\")
    text = text.replace("\r", "\\r")
    text = text.replace("\n", "\\n")
    return text


def unescape_text(text: str) -> str:
    """把转义形式的单行文本还原为原始文本（含真实 CR/LF）。"""
    # 'unicode_escape' 无法正确处理混杂的 \\r\\n（会把 \r\n 当成单个换行处理丢失），
    # 因此手写状态机解析，逐字符消费。
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "\\":
                out.append("\\")
                i += 2
                continue
            if nxt == "r":
                out.append("\r")
                i += 2
                continue
            if nxt == "n":
                out.append("\n")
                i += 2
                continue
            # 未知转义：原样保留反斜杠与下一字符
            out.append("\\")
            out.append(nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)
