"""术语库（glossary）测试：加载/新增/匹配精简/prompt 格式化。"""

from __future__ import annotations

import threading

import pytest

from office_translate.glossary import (
    GlossaryError,
    GlossaryStore,
    add_term,
    format_glossary_prompt,
    load_glossary,
    match_terms,
    remove_term,
    save_glossary,
    update_glossary,
)


@pytest.fixture
def glossary_data():
    return {
        "categories": {
            "汽车行业": [
                {"source": "PPB", "target": "十亿分之几", "note": "单位", "created": "2026-01-01"},
                {"source": "Valeo", "target": "法雷奥", "note": "", "created": "2026-01-01"},
            ],
            "软件": [
                {"source": "API", "target": "应用程序接口", "note": "", "created": "2026-01-01"},
            ],
        }
    }


def test_load_missing_file_returns_empty(tmp_path):
    data = load_glossary(str(tmp_path / "none.json"))
    assert data == {"categories": {}}


def test_load_invalid_raises(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"not_categories": 1}', encoding="utf-8")
    with pytest.raises(GlossaryError):
        load_glossary(str(p))


def test_add_and_save(tmp_path):
    p = tmp_path / "glossary.json"
    data = load_glossary(str(p))
    add_term(data, "汽车行业", "QAP", "质量保证计划")
    save_glossary(data, str(p))

    reloaded = load_glossary(str(p))
    assert reloaded["categories"]["汽车行业"][0]["source"] == "QAP"


def test_add_existing_updates(glossary_data):
    add_term(glossary_data, "汽车行业", "PPB", "每十亿个的缺陷数")
    entries = glossary_data["categories"]["汽车行业"]
    assert entries[0]["target"] == "每十亿个的缺陷数"
    assert len(entries) == 2


def test_add_empty_raises(glossary_data):
    with pytest.raises(GlossaryError):
        add_term(glossary_data, "汽车行业", "", "x")
    with pytest.raises(GlossaryError):
        add_term(glossary_data, "汽车行业", "x", "")


def test_remove_term(glossary_data):
    assert remove_term(glossary_data, "汽车行业", "PPB") is True
    assert remove_term(glossary_data, "汽车行业", "不存在") is False


def test_match_terms_all_categories(glossary_data):
    texts = ["The PPB level must be checked", "call the API now"]
    matched = match_terms(glossary_data, None, texts)
    sources = {m["source"] for m in matched}
    assert sources == {"PPB", "API"}
    assert "Valeo" not in sources  # 未出现在文本中


def test_match_terms_selected_category(glossary_data):
    texts = ["The PPB level must be checked", "call the API now"]
    matched = match_terms(glossary_data, ["软件"], texts)
    sources = {m["source"] for m in matched}
    assert sources == {"API"}  # 只选软件类别


def test_match_case_insensitive(glossary_data):
    texts = ["the ppb level"]  # 小写
    matched = match_terms(glossary_data, None, texts)
    assert {m["source"] for m in matched} == {"PPB"}


def test_match_no_texts(glossary_data):
    assert match_terms(glossary_data, None, []) == []


def test_format_prompt(glossary_data):
    matched = match_terms(glossary_data, None, ["PPB level"])
    s = format_glossary_prompt(matched)
    assert "PPB = 十亿分之几" in s
    assert "已知术语表" in s
    assert format_glossary_prompt([]) == ""


def test_glossary_update_serializes_read_modify_write(tmp_path):
    path = tmp_path / "glossary.json"
    workers = 8
    barrier = threading.Barrier(workers)
    errors = []

    def worker(index):
        try:
            barrier.wait(timeout=2)
            update_glossary(
                path,
                lambda data: add_term(data, "并发", f"source-{index}", f"target-{index}"),
            )
        except BaseException as exc:  # report failures after all threads join
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    entries = load_glossary(path)["categories"]["并发"]
    assert {entry["source"] for entry in entries} == {
        f"source-{index}" for index in range(workers)
    }


def test_glossary_update_validation_failure_keeps_previous_file(tmp_path):
    path = tmp_path / "glossary.json"
    save_glossary({"categories": {"原有": [{"source": "A", "target": "a"}]}}, path)

    with pytest.raises(GlossaryError, match="target 非法"):
        update_glossary(
            path,
            lambda data: data["categories"]["原有"].append(
                {"source": "B", "target": ""}
            ),
        )

    assert load_glossary(path) == {
        "categories": {"原有": [{"source": "A", "target": "a"}]}
    }
    assert list(tmp_path.glob(".glossary.json.*")) == []


def test_glossary_invalid_json_is_explicit(tmp_path):
    path = tmp_path / "glossary.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(GlossaryError, match="合法 JSON"):
        GlossaryStore(path).load()


def test_glossary_atomic_save_failure_keeps_previous_file_and_cleans_temp(tmp_path, monkeypatch):
    path = tmp_path / "glossary.json"
    save_glossary({"categories": {"原有": [{"source": "A", "target": "a"}]}}, path)

    import office_translate.storage as storage

    def fail_replace(source, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(storage.os, "replace", fail_replace)
    with pytest.raises(GlossaryError, match="保存术语库失败"):
        save_glossary({"categories": {"新": [{"source": "B", "target": "b"}]}}, path)

    assert load_glossary(path) == {
        "categories": {"原有": [{"source": "A", "target": "a"}]}
    }
    assert list(tmp_path.glob(".glossary.json.*")) == []
