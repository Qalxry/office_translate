"""escape.py 的转义/还原测试。"""

from office_translate.escape import decode_escapes, escape_text, unescape_text


def test_roundtrip():
    samples = [
        "",
        "plain text",
        "line1\nline2",
        "a\r\nb",
        "back\\slash",
        "混\\合\n文本\r",
        "\n\n\n",
        "\\n",
    ]
    for s in samples:
        assert unescape_text(escape_text(s)) == s


def test_escape_literals():
    assert escape_text("a\nb") == "a\\nb"
    assert escape_text("a\r\nb") == "a\\r\\nb"
    assert escape_text("\\") == "\\\\"
    assert escape_text("\n") == "\\n"


def test_unescape_literals():
    assert unescape_text("a\\nb") == "a\nb"
    assert unescape_text("a\\r\\nb") == "a\r\nb"
    assert unescape_text("\\\\n") == "\\n"  # 转义的反斜杠 + 字面 n


def test_unknown_escape_preserved():
    # 未知转义原样保留，不吞字符
    assert unescape_text("a\\tb") == "a\\tb"
    assert unescape_text("a\\qb") == "a\\qb"


def test_crlf_mixed_no_loss():
    assert unescape_text("\\r\\n") == "\r\n"
    assert unescape_text("a\\rb\\nc") == "a\rb\nc"


def test_decode_escapes():
    assert decode_escapes("\\n") == "\n"
    assert decode_escapes("\\t") == "\t"
    assert decode_escapes("\\r") == "\r"
    assert decode_escapes("\\\\") == "\\"
    assert decode_escapes("中文") == "中文"
    assert decode_escapes("中文\\n分隔") == "中文\n分隔"
    assert decode_escapes("\\q") == "\\q"  # 未知转义原样
