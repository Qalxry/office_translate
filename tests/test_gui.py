"""GUI 后端（FastAPI）接口测试：任务/提取/翻译/审核/apply/术语库。"""

import openpyxl
import pytest
from fastapi.testclient import TestClient

from office_translate.gui.server import create_app


@pytest.fixture
def app(tmp_path):
    """临时项目 + FastAPI 应用。"""
    (tmp_path / "config.yaml").write_text(
        "work_dir: work\noutput_dir: output\nsep: '\\n'\n", encoding="utf-8"
    )
    in_dir = tmp_path / "input"
    in_dir.mkdir()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "Hello"
    ws["B1"] = "World"
    wb.save(in_dir / "sample.xlsx")
    return create_app(config_path=str(tmp_path / "config.yaml"),
                      glossary_path=str(tmp_path / "glossary.json"))


@pytest.fixture
def client(app):
    return TestClient(app)


def test_health(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert r.json() == []


def test_create_and_extract(client, tmp_path):
    # 新建任务
    r = client.post("/api/jobs", json={"job": "job1", "input": str(tmp_path / "input" / "sample.xlsx")})
    assert r.status_code == 200, r.text
    assert (tmp_path / "work" / "job1" / "job.yaml").is_file()

    # 提取
    r = client.post("/api/jobs/job1/extract")
    assert r.status_code == 200, r.text
    info = r.json()
    assert info["unique_texts"] == 2

    # 读 source
    r = client.get("/api/jobs/job1/source")
    assert r.status_code == 200
    assert r.json()["texts"] == ["Hello", "World"]

    # 保存译文
    r = client.post("/api/jobs/job1/translated", json={"text": "你好\n世界"})
    assert r.status_code == 200

    # apply
    r = client.post("/api/jobs/job1/apply", json={"sep": "\\n"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["translated_output"].endswith("job1_translated.xlsx")
    wb = openpyxl.load_workbook(out["translated_output"])
    assert wb.active["A1"].value == "你好"


def test_glossary_flow(client):
    # 初始为空
    r = client.get("/api/glossary")
    assert r.json()["categories"] == {}

    # 新增
    r = client.post("/api/glossary/terms", json={"category": "汽车行业", "source": "PPB", "target": "十亿分之几"})
    assert r.status_code == 200, r.text
    r = client.get("/api/glossary")
    assert r.json()["categories"]["汽车行业"][0]["source"] == "PPB"

    # 删除
    r = client.delete("/api/glossary/terms", params={"category": "汽车行业", "source": "PPB"})
    assert r.json()["removed"] is True


def test_translate_google_mocked(client, monkeypatch):
    # mock GoogleProvider，避免真请求
    class FakeGoogle:
        name = "google"

        def __init__(self, mirrors):
            pass

        def translate_batch(self, texts, source, target):
            return [f"译:{t}" for t in texts]

    import office_translate.gui.server as server_mod
    monkeypatch.setattr(server_mod, "GoogleProvider", FakeGoogle)

    r = client.post("/api/translate", json={"texts": ["Hello", "World"], "engine": "google"})
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert results[0]["translation"] == "译:Hello"
    assert results[1]["translation"] == "译:World"


def test_translate_unknown_engine(client):
    r = client.post("/api/translate", json={"texts": ["Hello"], "engine": "nope"})
    assert r.status_code == 400
