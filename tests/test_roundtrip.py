"""顶层 extract()/apply() 端到端测试：构造小 xlsx，验证去重、回填、样式保留。"""

import openpyxl
import pytest

from office_translate import apply, extract


@pytest.fixture
def sample_xlsx(tmp_path):
    path = tmp_path / "sample.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"] = "Hello"
    ws["B1"] = "World"
    ws["A2"] = "重复文本"  # 去重测试：同一原文出现两次
    ws["B2"] = "重复文本"
    ws["A3"] = 42  # 数值不导出
    ws["A4"] = "=SUM(1,2)"  # 公式不导出
    ws["A5"] = "Merged"
    ws.merge_cells("A5:B5")  # 合并单元格
    ws["A1"].font = openpyxl.styles.Font(bold=True, color="FF0000")
    ws2 = wb.create_sheet("Sheet2")
    ws2["A1"] = "Hello"  # 跨工作表重复
    wb.save(path)
    return path


def _translate(source_txt, translated_txt):
    mapping = {"Hello": "你好", "World": "世界", "重复文本": "重复译文", "Merged": "合并"}
    lines = source_txt.read_text(encoding="utf-8").splitlines()
    translated_txt.write_text("\n".join(mapping[l] for l in lines) + "\n", encoding="utf-8")


def test_extract(sample_xlsx, tmp_path):
    txt = tmp_path / "source.txt"
    js = tmp_path / "map.json"
    info = extract(sample_xlsx, txt, js)

    assert info["sheets"] == ["Sheet1", "Sheet2"]
    assert info["cells_total"] == 8
    assert info["cells_translatable"] == 6  # 数值/公式各 1 个被排除
    assert info["unique_texts"] == 4  # Hello 在两张表去重

    lines = txt.read_text(encoding="utf-8").splitlines()
    assert lines == ["Hello", "World", "重复文本", "Merged"]

    mapping = js.read_text(encoding="utf-8")
    assert '"cells"' in mapping and 'Sheet2' in mapping


def test_roundtrip(sample_xlsx, tmp_path):
    txt = tmp_path / "source.txt"
    js = tmp_path / "map.json"
    extract(sample_xlsx, txt, js)

    translated = tmp_path / "translated.txt"
    _translate(txt, translated)

    out_t = tmp_path / "out_translated.xlsx"
    out_b = tmp_path / "out_bilingual.xlsx"
    result = apply(sample_xlsx, js, translated, out_t, out_b, sep="\n")
    assert result["unique_texts"] == 4
    assert result["cells_filled"] == 6

    # 仅译文版：译文落在正确位置，数值与样式保留
    wb = openpyxl.load_workbook(out_t)
    ws = wb["Sheet1"]
    assert ws["A1"].value == "你好"
    assert ws["B1"].value == "世界"
    assert ws["A2"].value == "重复译文"
    assert ws["B2"].value == "重复译文"
    assert ws["A3"].value == 42
    assert ws["A4"].value == "=SUM(1,2)"
    assert ws["A5"].value == "合并"
    assert wb["Sheet2"]["A1"].value == "你好"
    # 样式保留：加粗红字字体、合并单元格
    assert ws["A1"].font.bold is True
    assert ws["A1"].font.color.rgb in ("FF0000", "00FF0000")
    assert any(str(r) == "A5:B5" for r in ws.merged_cells.ranges)

    # 对照版：原文 + 分隔符 + 译文
    wb2 = openpyxl.load_workbook(out_b)
    ws2 = wb2["Sheet1"]
    assert ws2["A1"].value == "Hello\n你好"
    assert ws2["B1"].value == "World\n世界"


def test_apply_without_bilingual(sample_xlsx, tmp_path):
    txt = tmp_path / "source.txt"
    js = tmp_path / "map.json"
    extract(sample_xlsx, txt, js)
    translated = tmp_path / "translated.txt"
    _translate(txt, translated)

    out_t = tmp_path / "only.xlsx"
    result = apply(sample_xlsx, js, translated, out_t, sep="\n")
    assert result["bilingual_output"] is None
    assert out_t.is_file()


def test_line_count_mismatch_raises(sample_xlsx, tmp_path):
    txt = tmp_path / "source.txt"
    js = tmp_path / "map.json"
    extract(sample_xlsx, txt, js)

    translated = tmp_path / "translated.txt"
    translated.write_text("只有一行\n", encoding="utf-8")

    with pytest.raises(Exception, match="行数"):
        apply(sample_xlsx, js, translated, tmp_path / "out.xlsx")


def test_unsupported_format_raises(tmp_path):
    with pytest.raises(Exception, match="暂不支持"):
        extract(tmp_path / "notes.docx", tmp_path / "s.txt", tmp_path / "m.json")
