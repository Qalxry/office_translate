"""FastAPI 后端：GUI 的 REST 接口。

职责：
- 任务：新建 / 列表 / 提取 / 回填（复用 config.py + formats 适配器）
- AI 翻译：批量翻译（OpenAI 兼容 / Google 镜像站）
- 审核：不确定术语的接受 / 修改 / 拒绝，沉淀术语库
- 术语库：分类浏览 / 新增 / 编辑 / 删除
- 镜像站：列表 / 测试 / 排序
"""

from __future__ import annotations

import json
import os
import time
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

# 预置供应商（base_url + 常用模型）
DEFAULT_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
        "default_model": "gpt-4o-mini",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
    },
    "claude": {
        "name": "Claude (OpenAI 兼容)",
        "base_url": "https://api.anthropic.com/v1",
        "api_key": "",
        "models": ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5-20251001"],
        "default_model": "claude-sonnet-5",
    },
    "ollama": {
        "name": "Ollama (本地)",
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
        "models": ["qwen2.5", "llama3.1"],
        "default_model": "qwen2.5",
    },
}

GUI_CONFIG_DEFAULTS = {
    "ai": {
        "engine": "google",  # google | openai
        "providers": DEFAULT_PROVIDERS,
        "active_provider": "openai",
        "mirrors": DEFAULT_MIRRORS,
        "source_lang": "en",
        "target_lang": "zh-CN",
        "concurrency": 4,
    }
}


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
    settings_path = os.path.join(os.path.dirname(os.path.abspath(config_path)), "gui_settings.json")

    def _load_settings() -> dict:
        """读取 GUI 专属配置（与 config.yaml 分离），缺省用默认值。"""
        if os.path.isfile(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    # 浅合并，保证缺省项存在
                    merged = {**GUI_CONFIG_DEFAULTS}
                    for k, v in data.items():
                        if k in merged and isinstance(v, dict) and isinstance(merged[k], dict):
                            merged[k] = {**merged[k], **v}
                        else:
                            merged[k] = v
                    return merged
            except (json.JSONDecodeError, OSError):
                pass
        return json.loads(json.dumps(GUI_CONFIG_DEFAULTS))

    def _save_settings(data: dict) -> None:
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---------- 设置 ----------

    @app.get("/api/settings")
    def get_settings():
        return _load_settings()

    @app.put("/api/settings")
    def put_settings(body: dict):
        """保存 GUI 设置（前端把整个 settings 对象传回）。"""
        try:
            current = _load_settings()
            # 深合并用户改动
            for k, v in body.items():
                if k in current and isinstance(v, dict) and isinstance(current[k], dict):
                    current[k] = {**current[k], **v}
                else:
                    current[k] = v
            _save_settings(current)
            return current
        except OSError as e:
            raise HTTPException(500, f"保存设置失败: {e}") from e

    @app.post("/api/pick_file")
    def pick_file():
        """唤起系统原生文件选择器（tkinter），返回所选路径。"""
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口
            path = filedialog.askopenfilename(
                title="选择要翻译的文档",
                filetypes=[
                    ("Excel / Word", "*.xlsx *.xls *.docx"),
                    ("所有文件", "*.*"),
                ],
            )
            root.destroy()
            if not path:
                raise HTTPException(400, "未选择文件")
            return {"path": path}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"无法打开文件选择器: {e}") from e

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

    @app.post("/api/mirrors/test")
    def test_mirrors(body: dict):
        """测试镜像站连通性与延迟，返回排序后的结果。body: {mirrors}"""
        mirrors = body.get("mirrors") or DEFAULT_MIRRORS
        results = []
        for m in mirrors:
            start = time.time()
            try:
                provider = GoogleProvider([m])
                provider.translate("Hello", "en", "zh-CN")
                results.append({"url": m, "ok": True, "latency_ms": int((time.time() - start) * 1000)})
            except ProviderError:
                results.append({"url": m, "ok": False, "latency_ms": None})
        results.sort(key=lambda r: (not r["ok"], r["latency_ms"] or 99999))
        return {"results": results}

    def _translate_with_concurrency(texts, provider, source, target, concurrency, matched=None, use_glossary=False):
        """并发翻译（ThreadPoolExecutor），返回 results 列表。"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def translate_one(text):
            if use_glossary and isinstance(provider, OpenAICompatProvider):
                return translate_batch([text], provider, source, target, matched)[0]
            return {"id": 0, "translation": provider.translate(text, source, target), "uncertain_terms": []}

        results: list[Optional[dict]] = [None] * len(texts)
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = {pool.submit(translate_one, texts[i]): i for i in range(len(texts))}
            for fut in as_completed(futures):
                i = futures[fut]
                try:
                    r = fut.result()
                    r["id"] = i
                    results[i] = r
                except ProviderError:
                    results[i] = {
                        "id": i,
                        "translation": texts[i],
                        "uncertain_terms": [{"term": texts[i][:80], "reason": "翻译失败，保留原文", "candidate": ""}],
                    }
        return results

    @app.post("/api/translate")
    def translate(body: dict):
        """AI 翻译一批文本。body: {texts, source, target, engine, provider_config, glossary_categories}"""
        settings = _load_settings()
        ai_cfg = settings.get("ai", GUI_CONFIG_DEFAULTS["ai"])
        texts = body.get("texts", [])
        source = body.get("source", ai_cfg.get("source_lang", "en"))
        target = body.get("target", ai_cfg.get("target_lang", "zh-CN"))
        engine = body.get("engine", ai_cfg.get("engine", "google"))
        concurrency = int(body.get("concurrency", ai_cfg.get("concurrency", 4)))
        categories = body.get("glossary_categories")

        # 术语库匹配精简
        glossary = load_glossary(glossary_path)
        matched = match_terms(glossary, categories, texts)

        try:
            if engine == "google":
                mirrors = body.get("mirrors") or ai_cfg.get("mirrors") or DEFAULT_MIRRORS
                provider = GoogleProvider(mirrors)
                results = _translate_with_concurrency(
                    texts, provider, source, target, concurrency
                )
            elif engine == "openai":
                pc = body.get("provider_config") or {}
                provider = OpenAICompatProvider(
                    base_url=pc.get("base_url", "https://api.openai.com/v1"),
                    api_key=pc.get("api_key", ""),
                    model=pc.get("model", "gpt-4o-mini"),
                )
                results = _translate_with_concurrency(
                    texts, provider, source, target, concurrency, matched=matched, use_glossary=True
                )
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

    @app.put("/api/glossary/terms")
    def update_glossary_term(body: dict):
        """编辑术语：按 category+source 定位，更新 target/note。"""
        category = body.get("category", "")
        source = body.get("source", "")
        target = body.get("target", "")
        note = body.get("note", "")
        try:
            data = load_glossary(glossary_path)
            entries = data.get("categories", {}).get(category, [])
            for e in entries:
                if e["source"] == source:
                    if target:
                        e["target"] = target
                    if note is not None:
                        e["note"] = note
                    save_glossary(data, glossary_path)
                    return e
            raise HTTPException(404, f"术语不存在: {category}/{source}")
        except HTTPException:
            raise
        except GlossaryError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/api/glossary/terms")
    def delete_glossary_term(category: str, source: str):
        data = load_glossary(glossary_path)
        ok = remove_term(data, category, source)
        if ok:
            save_glossary(data, glossary_path)
        return {"removed": ok}

    @app.delete("/api/glossary/categories")
    def delete_glossary_category(category: str):
        """删除整个术语类别。"""
        data = load_glossary(glossary_path)
        categories = data.get("categories", {})
        if category not in categories:
            raise HTTPException(404, f"类别不存在: {category}")
        count = len(categories[category])
        del categories[category]
        save_glossary(data, glossary_path)
        return {"removed": True, "count": count}

    @app.post("/api/glossary/batch-delete")
    def delete_glossary_terms_batch(body: dict):
        """批量删除术语。body: {category, sources: [..]}"""
        category = body.get("category", "")
        sources = body.get("sources", [])
        data = load_glossary(glossary_path)
        entries = data.get("categories", {}).get(category, [])
        remaining = [e for e in entries if e["source"] not in set(sources)]
        removed = len(entries) - len(remaining)
        data["categories"][category] = remaining
        save_glossary(data, glossary_path)
        return {"removed": removed}

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
