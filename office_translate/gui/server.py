"""FastAPI 后端：GUI 的 REST 接口。

职责：
- 任务：新建 / 列表 / 提取 / 回填（复用 config.py + formats 适配器）
- AI 翻译：批量翻译（OpenAI 兼容 / Google 镜像站）
- 审核：不确定术语的接受 / 修改 / 拒绝，沉淀术语库
- 术语库：分类浏览 / 新增 / 编辑 / 删除
- 镜像站：列表 / 测试 / 排序
"""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import config as config_mod
from ..ai.provider import GoogleProvider, MirrorPool, OpenAICompatProvider, ProviderError
from ..ai.translator import translate_batch
from ..glossary import (
    GlossaryError,
    add_term,
    format_glossary_prompt,
    load_glossary,
    match_terms,
    remove_term,
    save_glossary,
)
from .. import extract as _extract
from .. import apply as _apply

# Google 镜像站默认列表（实测可用，按稳定性排序）
DEFAULT_MIRRORS = [
    "https://google-translate-proxy.tantu.com",
    "https://translate.renwole.com",
    "https://gt1.yifan.ai",
]


def create_app(config_path: str = "config.yaml", glossary_path: str = "glossary.json") -> FastAPI:
    """创建 FastAPI 应用。"""
    app = FastAPI(title="office_translate GUI")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    cfg = config_mod.load_config(config_path)
    glossary_path = os.path.abspath(glossary_path)

    # ---------- 任务 ----------

    @app.get("/api/jobs")
    def list_jobs():
        return config_mod.list_jobs(cfg)

    @app.post("/api/jobs")
    def create_job(body: dict):
        job = body.get("job")
        input_path = body.get("input")
        sep = body.get("sep")
        if not input_path:
            raise HTTPException(400, "缺少 input 字段")
        try:
            info = config_mod.init_job(cfg, job or "", input_path, sep)
            return info
        except config_mod.ConfigError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/jobs/{job}/extract")
    def job_extract(job: str):
        try:
            info = config_mod.load_job(cfg, job)
            adapter = _get_adapter(info["input"])
            result = adapter.extract(info["input"], info["source_txt"], info["map_json"])
            return {**info, **result}
        except Exception as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/api/jobs/{job}/source")
    def job_source(job: str):
        """返回 source.txt 的文本列表（供 AI 翻译使用）。"""
        try:
            info = config_mod.load_job(cfg, job)
            if not os.path.isfile(info["source_txt"]):
                raise HTTPException(400, "尚未提取，请先运行提取")
            with open(info["source_txt"], "r", encoding="utf-8") as f:
                texts = [line.rstrip("\n") for line in f]
            return {"texts": texts}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/jobs/{job}/translated")
    def job_save_translated(job: str, body: dict):
        """保存译文文本到 translated.txt。"""
        text = body.get("text", "")
        try:
            info = config_mod.load_job(cfg, job)
            with open(info["translated_txt"], "w", encoding="utf-8", newline="") as f:
                f.write(text)
                if text and not text.endswith("\n"):
                    f.write("\n")
            return {"ok": True}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/jobs/{job}/apply")
    def job_apply(job: str, body: dict):
        try:
            info = config_mod.load_job(cfg, job)
            adapter = _get_adapter(info["input"])
            os.makedirs(info["output_dir"], exist_ok=True)
            sep = body.get("sep") or info["sep"]
            result = adapter.apply(
                original=info["input"],
                json_path=info["map_json"],
                translated_txt=info["translated_txt"],
                output_translated=info["output_translated"],
                output_bilingual=info["output_bilingual"],
                sep=sep,
            )
            return result
        except Exception as e:
            raise HTTPException(400, str(e)) from e

    # ---------- AI 翻译 ----------

    @app.get("/api/mirrors")
    def get_mirrors():
        return {"mirrors": DEFAULT_MIRRORS}

    @app.post("/api/translate")
    def translate(body: dict):
        """AI 翻译一批文本。body: {texts, source, target, engine, provider_config, glossary_categories}"""
        texts = body.get("texts", [])
        source = body.get("source", "en")
        target = body.get("target", "zh-CN")
        engine = body.get("engine", "google")
        categories = body.get("glossary_categories")

        # 术语库匹配精简
        glossary = load_glossary(glossary_path)
        matched = match_terms(glossary, categories, texts)

        try:
            if engine == "google":
                provider = GoogleProvider(body.get("mirrors") or DEFAULT_MIRRORS)
                # Google 无自报，直接翻译
                translations = provider.translate_batch(texts, source, target)
                results = [
                    {"id": i, "translation": t, "uncertain_terms": []}
                    for i, t in enumerate(translations)
                ]
            elif engine == "openai":
                pc = body.get("provider_config", {})
                provider = OpenAICompatProvider(
                    base_url=pc.get("base_url", "https://api.openai.com/v1"),
                    api_key=pc.get("api_key", ""),
                    model=pc.get("model", "gpt-4o-mini"),
                )
                results = translate_batch(texts, provider, source, target, matched)
            else:
                raise HTTPException(400, f"未知引擎: {engine}")
            return {"results": results, "matched_glossary": matched}
        except HTTPException:
            raise
        except ProviderError as e:
            raise HTTPException(502, str(e)) from e
        except Exception as e:
            raise HTTPException(500, str(e)) from e

    # ---------- 审核与术语库 ----------

    @app.get("/api/glossary")
    def get_glossary():
        return load_glossary(glossary_path)

    @app.post("/api/glossary/terms")
    def add_glossary_term(body: dict):
        category = body.get("category", "默认")
        source = body.get("source", "")
        target = body.get("target", "")
        note = body.get("note", "")
        try:
            data = load_glossary(glossary_path)
            entry = add_term(data, category, source, target, note)
            save_glossary(data, glossary_path)
            return entry
        except GlossaryError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/api/glossary/terms")
    def delete_glossary_term(category: str, source: str):
        data = load_glossary(glossary_path)
        ok = remove_term(data, category, source)
        if ok:
            save_glossary(data, glossary_path)
        return {"removed": ok}

    # ---------- 静态前端 ----------

    web_dir = os.path.join(os.path.dirname(__file__), "web")
    if os.path.isdir(web_dir):
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app


def _get_adapter(path: str):
    from ..base import get_adapter

    ext = os.path.splitext(path)[1]
    try:
        return get_adapter(ext)()
    except Exception as e:
        raise HTTPException(400, str(e)) from e
