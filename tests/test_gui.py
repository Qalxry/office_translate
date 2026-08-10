"""GUI 后端（FastAPI）接口测试：任务/提取/翻译/审核/apply/术语库。"""

import os

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


def test_upload_file(client, tmp_path):
    # 浏览器原生文件选择器 → 上传 → 保存到 input/
    r = client.post("/api/upload", files={"file": ("问卷.xlsx", b"fake-xlsx-content", "application/octet-stream")})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["filename"] == "问卷.xlsx"
    assert data["path"].endswith("问卷.xlsx")
    assert os.path.isfile(data["path"])
    assert open(data["path"], "rb").read() == b"fake-xlsx-content"


def test_create_job_auto_name(client, tmp_path):
    # 不传 job → 自动按时间戳命名
    r = client.post("/api/jobs", json={"job": None, "input": str(tmp_path / "input" / "sample.xlsx")})
    assert r.status_code == 200, r.text
    info = r.json()
    import re
    assert re.fullmatch(r"\d{8}_\d{6}", info["job"]), info["job"]
    assert os.path.isdir(tmp_path / "work" / info["job"])


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

    # 读取译文（translated_file）
    r = client.get("/api/jobs/job1/translated_file")
    assert r.status_code == 200
    assert r.json()["text"] == "你好\n世界\n"

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

        def translate(self, text, source, target):
            return f"译:{text}"

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


def test_glossary_edit_and_delete(client):
    # 新增
    r = client.post("/api/glossary/terms", json={"category": "软件", "source": "API", "target": "接口"})
    assert r.status_code == 200

    # 编辑
    r = client.put("/api/glossary/terms", json={"category": "软件", "source": "API", "target": "应用程序接口", "note": "更新"})
    assert r.status_code == 200
    assert r.json()["target"] == "应用程序接口"

    # 编辑不存在的 → 404
    r = client.put("/api/glossary/terms", json={"category": "软件", "source": "不存在", "target": "x"})
    assert r.status_code == 404

    # 删除
    r = client.delete("/api/glossary/terms", params={"category": "软件", "source": "API"})
    assert r.json()["removed"] is True


def test_mirrors_test_mocked(client, monkeypatch):
    import office_translate.gui.server as server_mod

    class FakeGoogle:
        name = "google"

        def __init__(self, mirrors):
            pass

        def translate(self, text, source, target):
            return "ok"

    monkeypatch.setattr(server_mod, "GoogleProvider", FakeGoogle)
    r = client.post("/api/mirrors/test", json={"mirrors": ["https://a.example", "https://b.example"]})
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert len(results) == 2
    assert all(x["ok"] for x in results)
    assert results[0]["url"] == "https://a.example"


def test_mirrors_default(client):
    r = client.get("/api/mirrors")
    assert r.status_code == 200
    assert len(r.json()["mirrors"]) == 3


def test_settings_roundtrip(client):
    # 读取默认
    r = client.get("/api/settings")
    assert r.status_code == 200
    settings = r.json()
    assert settings["ai"]["engine"] == "google"
    assert "openai" in settings["ai"]["providers"]

    # 修改镜像站 + 引擎
    settings["ai"]["mirrors"] = ["https://custom.example"]
    settings["ai"]["engine"] = "openai"
    r = client.put("/api/settings", json=settings)
    assert r.status_code == 200
    assert r.json()["ai"]["mirrors"] == ["https://custom.example"]

    # 重新读取（持久化）
    r = client.get("/api/settings")
    assert r.json()["ai"]["mirrors"] == ["https://custom.example"]


def test_glossary_category_delete(client):
    client.post("/api/glossary/terms", json={"category": "甲", "source": "A", "target": "a"})
    client.post("/api/glossary/terms", json={"category": "甲", "source": "B", "target": "b"})
    client.post("/api/glossary/terms", json={"category": "乙", "source": "C", "target": "c"})

    r = client.delete("/api/glossary/categories", params={"category": "甲"})
    assert r.json() == {"removed": True, "count": 2}
    g = client.get("/api/glossary").json()
    assert "甲" not in g["categories"]
    assert "乙" in g["categories"]


def test_glossary_batch_delete(client):
    client.post("/api/glossary/terms", json={"category": "丙", "source": "X", "target": "x"})
    client.post("/api/glossary/terms", json={"category": "丙", "source": "Y", "target": "y"})
    r = client.post("/api/glossary/batch-delete", json={"category": "丙", "sources": ["X"]})
    assert r.json() == {"removed": 1}
    g = client.get("/api/glossary").json()
    assert [e["source"] for e in g["categories"]["丙"]] == ["Y"]
