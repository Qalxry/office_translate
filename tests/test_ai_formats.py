"""Strict text/json/xml protocol parsers and streaming preview extraction."""

import pytest

from office_translate.ai.contracts import (
    OutputContractError,
    TranslationRequestItem,
    escape_text_line,
    parse_result_by_format,
    parse_translation_text,
    parse_translation_result_xml,
    strip_text_sequence_prefix,
)
from office_translate.ai.streaming import extract_preview_items
from office_translate.ai.translator import build_request_payload, build_system_prompt


def test_json_request_and_prompt_separate_source_and_translation_fields():
    item = TranslationRequestItem(
        7,
        "Hello",
        source_id=7,
        offset_start=0,
        offset_end=5,
        segment_index=0,
        segment_count=1,
    )
    payload = build_request_payload([item], "json")
    assert payload == '{"source_items":[{"id":7,"source_text":"Hello"}]}'
    prompt = build_system_prompt("en", "zh-CN", "", "json")
    assert '"translation":"translated text"' in prompt
    assert "Never output text, source, or source_text" in prompt


def test_xml_parses_id_bearing_items_with_internal_newlines():
    content = (
        "<items>"
        '<item id="1"><translation>second</translation>'
        "<uncertain_terms/>"
        "</item>"
        '<item id="0"><translation>first\ncontinued</translation>'
        "<uncertain_terms>"
        '<term term="PPB" reason="abbr" candidate="parts per billion"/>'
        "</uncertain_terms>"
        "</item>"
        "</items>"
    )
    parsed = parse_translation_result_xml(content, [0, 1])
    assert [item.id for item in parsed] == [0, 1]
    assert parsed[0].translation == "first\ncontinued"
    assert parsed[0].uncertain_terms[0]["term"] == "PPB"


def test_xml_escapes_text_and_attributes():
    content = (
        "<items>"
        '<item id="0"><translation>a &lt;b&gt; &amp; c</translation>'
        '<uncertain_terms><term term="A&amp;B" reason="r" candidate="c"/></uncertain_terms>'
        "</item>"
        "</items>"
    )
    parsed = parse_translation_result_xml(content, [0])
    assert parsed[0].translation == "a <b> & c"
    assert parsed[0].uncertain_terms[0]["term"] == "A&B"


def test_xml_repairs_bare_ampersands_without_relaxing_structure():
    content = (
        "<items>"
        '<item id="0"><translation>AT&T and Sons</translation>'
        '<uncertain_terms><term term="A&B" reason="r" candidate="c"/></uncertain_terms>'
        "</item>"
        "</items>"
    )
    parsed = parse_translation_result_xml(content, [0])
    assert parsed[0].translation == "AT&T and Sons"
    assert parsed[0].uncertain_terms[0]["term"] == "A&B"


def test_xml_cdata_ampersands_are_not_double_escaped():
    content = (
        "<items>"
        '<item id="0"><translation><![CDATA[A&B]]></translation>'
        "<uncertain_terms/>"
        "</item>"
        "</items>"
    )
    parsed = parse_translation_result_xml(content, [0])
    assert parsed[0].translation == "A&B"


@pytest.mark.parametrize(
    ("content", "code"),
    [
        ("not xml", "malformed_xml"),
        ("<result/>", "invalid_schema"),
        ("<items><foo/></items>", "invalid_schema"),
        ("<items><item><translation>x</translation><uncertain_terms/></item></items>", "invalid_schema"),
        ('<items><item id="0" extra="1"><translation>x</translation><uncertain_terms/></item></items>', "invalid_schema"),
        ('<items><item id="0"><uncertain_terms/></item></items>', "invalid_schema"),
        ('<items><item id="0"><translation>x</translation></item></items>', "invalid_schema"),
        ('<items><item id="0"><translation>x</translation><uncertain_terms><foo/></uncertain_terms></item></items>', "invalid_schema"),
        (
            "<items>"
            '<item id="0"><translation>x</translation><uncertain_terms/></item>'
            '<item id="0"><translation>y</translation><uncertain_terms/></item>'
            "</items>",
            "duplicate_id",
        ),
        (
            '<items><item id="0"><translation>x</translation><uncertain_terms/></item></items>',
            "id_set_mismatch",
        ),
    ],
)
def test_xml_rejects_invalid_output(content, code):
    with pytest.raises(OutputContractError) as caught:
        parse_translation_result_xml(content, [0, 1])
    assert caught.value.code == code


def test_text_parses_lines_and_decodes_escapes():
    content = "第一行\\n继续\\t制表\\\\反斜杠\n第二行"
    parsed = parse_translation_text(content, [0, 1])
    assert parsed[0].translation == "第一行\n继续\t制表\\反斜杠"
    assert parsed[1].translation == "第二行"
    assert parsed[0].uncertain_terms == ()


def test_text_allows_trailing_line_separator_and_empty_translations():
    parsed = parse_translation_text("\n\n", [0, 1])
    assert [item.translation for item in parsed] == ["", ""]
    assert parse_translation_text("a\nb\n", [0, 1])[1].translation == "b"


def test_text_strips_sequence_prefixes_from_translations():
    parsed = parse_translation_text(
        "1. 你好\n[2] 世界\n3、测试\n4) 测试",
        [0, 1, 2, 3],
    )
    assert [item.translation for item in parsed] == ["你好", "世界", "测试", "测试"]


def test_text_prefix_stripping_keeps_legitimate_numbered_content():
    assert strip_text_sequence_prefix("1.5 版本") == "1.5 版本"
    assert strip_text_sequence_prefix("2024年报告") == "2024年报告"
    assert strip_text_sequence_prefix("1.") == "1."


@pytest.mark.parametrize(
    ("content", "code"),
    [
        ("only one", "line_count_mismatch"),
        ("a\nb\nc", "line_count_mismatch"),
        ("", "empty_response"),
    ],
)
def test_text_rejects_invalid_output(content, code):
    with pytest.raises(OutputContractError) as caught:
        parse_translation_text(content, [0, 1])
    assert caught.value.code == code


@pytest.mark.parametrize(
    "content",
    ["bad\\q escape", "trailing\\"],
)
def test_text_rejects_bad_escape(content):
    with pytest.raises(OutputContractError) as caught:
        parse_translation_text(content, [0])
    assert caught.value.code == "malformed_escape"


def test_escape_and_decode_are_inverse():
    original = "A\nB\tC\\D\rE\fF\vG\0H"
    assert parse_translation_text(escape_text_line(original) + "\n", [0])[0].translation == original


def test_parse_result_by_format_rejects_unknown_format():
    with pytest.raises(OutputContractError):
        parse_result_by_format("x", [0], "yaml")


def test_json_stream_preview_extracts_completed_items_only():
    content = (
        '{"items":[{"id":0,"translation":"first\\nline","uncertain_terms":[]},'
        '{"id":1,"translation":"seco'
    )
    items = extract_preview_items(content, "json")
    assert items == [{"id": 0, "translation": "first\nline", "uncertain_terms": []}]


def test_json_stream_preview_extracts_closed_translation_before_item_closes():
    content = '{"items":[{"id":3,"translation":"完成译文","uncertain_terms":'
    items = extract_preview_items(content, "json")
    assert items == [{"id": 3, "translation": "完成译文"}]


def test_json_stream_preview_handles_escaped_quotes_in_partial_translation():
    content = '{"items":[{"id":1,"translation":"含\\"引号\\"文本","uncertain_terms":'
    items = extract_preview_items(content, "json")
    assert items == [{"id": 1, "translation": '含"引号"文本'}]


def test_xml_stream_preview_extracts_completed_items_only():
    content = (
        "<items>"
        '<item id="1"><translation>second</translation><uncertain_terms/></item>'
        '<item id="0"><translation>unfinished'
    )
    items = extract_preview_items(content, "xml")
    assert items == [{"id": 1, "translation": "second"}]


def test_text_stream_preview_extracts_completed_lines_and_decodes():
    content = "第一\\n行\n第二"
    items = extract_preview_items(content, "text", start_id=5)
    assert items == [{"id": 5, "translation": "第一\n行"}]


def test_text_stream_preview_strips_sequence_prefixes():
    items = extract_preview_items("1. 你好\n", "text", start_id=0)
    assert items == [{"id": 0, "translation": "你好"}]


def test_text_stream_preview_treats_final_separator_as_complete_line():
    items = extract_preview_items("甲\n乙\n", "text", start_id=0)
    assert items == [{"id": 0, "translation": "甲"}, {"id": 1, "translation": "乙"}]
