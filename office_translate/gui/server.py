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
import logging
import os
import time
import copy
import threading
import uuid
from hashlib import sha256
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import config as config_mod
from ..ai.contracts import (
    OperationSummary,
    OutputContractError,
    TranslationRequestItem,
    validate_result_item,
    validate_result_items,
)
from ..ai.chunking import chunk_request_items, reassemble_segments
from ..ai.provider import GoogleProvider, MirrorPool, OpenAICompatProvider, ProviderError
from ..ai.streaming import extract_preview_items
from ..ai.translator import build_system_prompt, translate_batch
from ..glossary import (
    GlossaryError,
    GlossaryStore,
    add_term,
    format_glossary_prompt,
    load_glossary,
    match_terms,
    remove_term,
    update_glossary,
)
from ..jobs import JobError, JobService
from ..settings import SettingsError, SettingsStore
from ..formats.xlsx.applier import TranslationError
from ..formats.xlsx.extractor import preflight_workbook
from ..storage import cleanup_file, make_temp_path

# Google 镜像站默认列表（实测可用，按稳定性排序）
DEFAULT_MIRRORS = [
    "https://google-translate-proxy.tantu.com",
    "https://translate.renwole.com",
    "https://gt1.yifan.ai",
]

# 预置供应商（base_url + 常用模型 + 模型上下文 token 数，用于分块）
# model_configs：模型级参数 {模型名: {model_context, temperature, max_tokens, top_p, ...}}，
# 支持 OpenAI 兼容 API 的任意请求参数（thinking / reasoning_effort / top_k 等放 extra）。
DEFAULT_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
        "default_model": "gpt-4o-mini",
        "model_context": 128000,
        "model_configs": {
            "gpt-4o-mini": {"model_context": 128000, "temperature": 0.6, "max_tokens": 8192},
            "gpt-4o": {"model_context": 128000, "temperature": 0.6, "max_tokens": 16384},
            "gpt-4.1-mini": {"model_context": 1000000, "temperature": 0.6, "max_tokens": 32768},
        },
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
        "model_context": 128000,
        "model_configs": {
            "deepseek-chat": {"model_context": 128000, "temperature": 0.6, "max_tokens": 8192},
            "deepseek-reasoner": {
                "model_context": 128000, "temperature": 1.0, "max_tokens": 8192,
                "thinking": {"type": "enabled"},
            },
        },
    },
    "claude": {
        "name": "Claude (OpenAI 兼容)",
        "base_url": "https://api.anthropic.com/v1",
        "api_key": "",
        "models": ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5-20251001"],
        "default_model": "claude-sonnet-5",
        "model_context": 200000,
        "model_configs": {
            "claude-sonnet-5": {"model_context": 200000, "temperature": 0.6, "max_tokens": 8192},
            "claude-opus-5": {"model_context": 200000, "temperature": 0.6, "max_tokens": 8192},
            "claude-haiku-4-5-20251001": {"model_context": 200000, "temperature": 0.6, "max_tokens": 8192},
        },
    },
    "ollama": {
        "name": "Ollama (本地)",
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
        "models": ["qwen2.5", "llama3.1"],
        "default_model": "qwen2.5",
        "model_context": 32768,
        "model_configs": {
            "qwen2.5": {"model_context": 32768, "temperature": 0.6, "max_tokens": 8192},
            "llama3.1": {"model_context": 32768, "temperature": 0.6, "max_tokens": 8192},
        },
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


def _diagnostic_logger(config_path: str) -> logging.Logger:
    """Create one local rolling diagnostic logger per application workspace.

    Records intentionally contain only event codes and non-sensitive context.  In
    particular, exception messages and request bodies are never written here: a
    provider may include credentials or document text in either one.
    """

    base_dir = (
        os.path.dirname(os.path.abspath(config_path))
        if config_path
        else os.getcwd()
    )
    log_dir = os.path.join(base_dir, "data", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "office_translate.log")
    logger_name = "office_translate.gui." + sha256(log_path.encode("utf-8")).hexdigest()[:12]
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def create_app(config_path: str = "config.yaml", glossary_path: str = "data/glossary.json") -> FastAPI:
    """创建 FastAPI 应用。"""
    app = FastAPI(title="office_translate GUI")

    cfg = config_mod.load_config(config_path)
    glossary_path = os.path.abspath(glossary_path)
    settings_path = os.path.join(os.path.dirname(os.path.abspath(config_path)), "data", "gui_settings.json")
    job_service = JobService(cfg)
    settings_store = SettingsStore(settings_path, GUI_CONFIG_DEFAULTS)
    glossary_store = GlossaryStore(glossary_path)
    diagnostic_logger = _diagnostic_logger(config_path)
    operation_guard = threading.RLock()
    operation_registry: dict[str, dict[str, Any]] = {}
    app.state.operation_registry = operation_registry
    app.state.operation_guard = operation_guard
    app.state.diagnostic_log_path = next(
        (
            handler.baseFilename
            for handler in diagnostic_logger.handlers
            if isinstance(handler, RotatingFileHandler)
        ),
        None,
    )

    def _log_failure(
        error_code: str,
        operation: str,
        *,
        job: str | None = None,
        exc: BaseException | None = None,
    ) -> None:
        diagnostic_logger.error(
            "event=operation_failed error_code=%s operation=%s job=%s exception_type=%s",
            error_code,
            operation,
            job or "-",
            type(exc).__name__ if exc is not None else "-",
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        _log_failure(
            "internal_error",
            request.url.path,
            exc=exc,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "发生内部错误，请重试；若问题持续，请复制诊断编号。",
                "error_code": "internal_error",
            },
        )

    def _load_settings() -> dict:
        """Read the internal settings snapshot, including secrets for server use."""
        return settings_store.load()

    def _mask_secret(value: Any) -> str:
        if not isinstance(value, str) or not value:
            return ""
        return "••••••••" + value[-4:]

    def _public_settings(data: dict) -> dict:
        """Remove provider secrets before a settings object crosses the API."""
        public = copy.deepcopy(data)
        ai = public.get("ai")
        if not isinstance(ai, dict):
            return public
        providers = ai.get("providers")
        if not isinstance(providers, dict):
            return public
        internal_ai = data.get("ai")
        internal_providers = internal_ai.get("providers", {}) if isinstance(internal_ai, dict) else {}
        for key, provider in providers.items():
            if not isinstance(provider, dict):
                continue
            internal = internal_providers.get(key, {})
            secret = internal.get("api_key") if isinstance(internal, dict) else ""
            provider.pop("api_key", None)
            provider["api_key_configured"] = bool(secret)
            provider["api_key_masked"] = _mask_secret(secret)
        return public

    def _merge_settings_payload(current: dict, body: dict) -> dict:
        """Merge public GUI settings while retaining secrets server-side.

        A provider's api_key is accepted only as an explicit save input.  The
        response is always sanitized by _public_settings, and a masked/absent
        key means "keep the already stored secret".  clear_api_key is the only
        way to remove one.
        """
        if not isinstance(body, dict):
            raise SettingsError("设置请求必须是 JSON 对象。")
        merged = copy.deepcopy(current)
        incoming_ai = body.get("ai")
        if "ai" in body and not isinstance(incoming_ai, dict):
            raise SettingsError("ai 必须是对象。")
        if not isinstance(incoming_ai, dict):
            return {**merged, **body}

        for key, value in body.items():
            if key != "ai":
                merged[key] = copy.deepcopy(value)

        current_ai = merged.setdefault("ai", {})
        for key, value in incoming_ai.items():
            if key != "providers":
                current_ai[key] = copy.deepcopy(value)

        if "providers" not in incoming_ai:
            return merged
        incoming_providers = incoming_ai["providers"]
        if not isinstance(incoming_providers, dict):
            raise SettingsError("ai.providers 必须是对象。")
        existing_providers = current_ai.get("providers", {})
        if not isinstance(existing_providers, dict):
            existing_providers = {}
        providers: dict[str, dict] = {}
        for provider_key, raw_provider in incoming_providers.items():
            if not isinstance(raw_provider, dict):
                raise SettingsError(f"供应商 {provider_key!r} 配置必须是对象。")
            provider = copy.deepcopy(raw_provider)
            previous = existing_providers.get(provider_key, {})
            previous_secret = previous.get("api_key", "") if isinstance(previous, dict) else ""
            supplied_secret = provider.pop("api_key", None)
            masked = provider.pop("api_key_masked", "")
            provider.pop("api_key_configured", None)
            clear_secret = bool(provider.pop("clear_api_key", False))
            if clear_secret:
                provider["api_key"] = ""
            elif isinstance(supplied_secret, str) and supplied_secret and supplied_secret != masked:
                provider["api_key"] = supplied_secret
            else:
                provider["api_key"] = previous_secret
            providers[str(provider_key)] = provider
        current_ai["providers"] = providers
        return merged

    def _validate_ai_selection(settings: dict[str, Any]) -> dict[str, Any]:
        """Reject settings whose active provider/model no longer exists."""
        ai = settings.get("ai")
        if not isinstance(ai, dict):
            raise SettingsError("ai 设置必须是对象。")
        providers = ai.get("providers")
        if not isinstance(providers, dict) or not providers:
            raise SettingsError("至少需要一个 AI 供应商。")
        active_provider = ai.get("active_provider")
        if not isinstance(active_provider, str) or active_provider not in providers:
            raise SettingsError("当前供应商已不存在，请重新选择后保存。")
        provider = providers[active_provider]
        if not isinstance(provider, dict):
            raise SettingsError("当前供应商配置无效。")
        model_configs = provider.get("model_configs")
        if not isinstance(model_configs, dict) or not model_configs:
            raise SettingsError("当前供应商没有可用模型，请先添加模型。")
        active_model = ai.get("active_model") or provider.get("default_model")
        if not isinstance(active_model, str) or active_model not in model_configs:
            raise SettingsError("当前模型已不存在，请重新选择后保存。")
        return settings

    def _preflight_or_error(path: str) -> dict[str, Any]:
        """Validate an XLSX before it can enter the task lifecycle."""
        result = preflight_workbook(path)
        if not result.ok:
            first = result.blocking_diagnostics[0] if result.blocking_diagnostics else None
            message = first.message if first else "文件未通过 XLSX 预检"
            action = first.action if first else "请重新选择文件"
            raise HTTPException(400, f"{message} {action}")
        return result.to_dict()

    def _new_operation(*, total: int, job: str | None = None) -> str:
        operation_id = uuid.uuid4().hex
        with operation_guard:
            operation_registry[operation_id] = {
                "operation_id": operation_id,
                "status": "running",
                "total": total,
                "job": job,
                "cancel_event": threading.Event(),
                "created_at": time.time(),
                "completed": 0,
                "succeeded": 0,
                "failed": 0,
                "cancelled": 0,
            }
        return operation_id

    def _finish_operation(operation_id: str, summary: dict[str, Any]) -> None:
        with operation_guard:
            record = operation_registry.get(operation_id)
            if record is None:
                return
            record.update(
                {
                    "status": summary.get("status", "failed"),
                    "completed": summary.get("succeeded", 0)
                    + summary.get("failed", 0)
                    + summary.get("cancelled", 0),
                    "succeeded": summary.get("succeeded", 0),
                    "failed": summary.get("failed", 0),
                    "cancelled": summary.get("cancelled", 0),
                    "summary": copy.deepcopy(summary),
                    "finished_at": time.time(),
                }
            )

    # ---------- 设置 ----------

    @app.get("/api/settings")
    def get_settings():
        try:
            return _public_settings(_load_settings())
        except SettingsError as exc:
            _log_failure("settings_load_failed", "settings.load", exc=exc)
            raise HTTPException(500, "设置文件无法读取，请检查本地诊断日志。") from exc

    @app.put("/api/settings")
    def put_settings(body: dict):
        """保存 GUI 设置（前端把整个 settings 对象传回）。"""
        try:
            updated = settings_store.update(
                lambda current: _validate_ai_selection(
                    _merge_settings_payload(current, body)
                )
            )
            return _public_settings(updated)
        except SettingsError as exc:
            _log_failure("settings_save_failed", "settings.save", exc=exc)
            raise HTTPException(400, "设置格式无效或保存失败，请检查后重试。") from exc

    def _resolve_openai_config(
        ai_cfg: dict,
        body: dict,
    ) -> tuple[str, str, str]:
        """Resolve provider credentials only from the server-owned settings.

        The browser may select a provider and model, but it must not send an
        API key back with every translation request.
        """
        request_provider = body.get("provider_config") or {}
        if not isinstance(request_provider, dict):
            raise HTTPException(400, "供应商配置格式无效。")
        provider_key = (
            body.get("provider_id")
            or body.get("provider_key")
            or request_provider.get("provider_id")
            or ai_cfg.get("active_provider")
        )
        providers = ai_cfg.get("providers")
        provider = providers.get(provider_key) if isinstance(providers, dict) else None
        if not isinstance(provider, dict):
            raise HTTPException(400, "未找到有效的 AI 供应商，请先在设置中保存。")
        model_config = body.get("model_config") or {}
        if not isinstance(model_config, dict):
            raise HTTPException(400, "供应商配置格式无效。")
        base_url = str(provider.get("base_url") or "").strip()
        model = str(
            body.get("model")
            or request_provider.get("model")
            or provider.get("default_model")
            or ""
        ).strip()
        api_key = provider.get("api_key") or ""
        if not isinstance(api_key, str):
            raise HTTPException(400, "供应商 API Key 配置无效，请重新保存。")
        if not base_url or not model:
            raise HTTPException(400, "供应商缺少 Base URL 或模型，请先在设置中保存。")
        return base_url, api_key, model

    def _effective_model_config(
        ai_cfg: dict,
        body: dict,
    ) -> dict[str, Any]:
        """Build one validated model snapshot for sync, stream and retry paths.

        Saved model settings provide the baseline.  The request may carry the
        same model-level protocol snapshot selected by the GUI; credentials
        and provider identity are never taken from that payload.
        """
        request_provider = body.get("provider_config") or {}
        if not isinstance(request_provider, dict):
            raise HTTPException(400, "供应商配置格式无效。")
        provider_key = (
            body.get("provider_id")
            or body.get("provider_key")
            or request_provider.get("provider_id")
            or ai_cfg.get("active_provider")
        )
        providers = ai_cfg.get("providers")
        provider = providers.get(provider_key) if isinstance(providers, dict) else None
        if not isinstance(provider, dict):
            raise HTTPException(400, "未找到有效的 AI 供应商，请先在设置中保存。")
        model = str(
            body.get("model")
            or request_provider.get("model")
            or provider.get("default_model")
            or ""
        ).strip()
        model_configs = provider.get("model_configs")
        if not isinstance(model_configs, dict) or model not in model_configs:
            raise HTTPException(400, "当前模型已不存在，请先在设置中重新选择。")
        saved = model_configs[model]
        if not isinstance(saved, dict):
            raise HTTPException(400, "当前模型没有有效配置，请先在设置中保存。")
        supplied = body.get("model_config") or {}
        if not isinstance(supplied, dict):
            raise HTTPException(400, "model_config 必须是对象。")
        effective = copy.deepcopy(saved)
        effective.update(copy.deepcopy(supplied))
        return effective

    # ---------- 任务 ----------

    @app.get("/api/jobs")
    def list_jobs():
        return job_service.list()

    @app.get("/api/jobs/{job}/status")
    def job_status(job: str):
        try:
            return job_service.status(job)
        except JobError as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/api/jobs/{job}/download")
    def job_download(job: str, kind: str = "translated"):
        """下载任务输出文件（translated / bilingual）。"""
        from fastapi.responses import FileResponse

        try:
            path = job_service.download(job, kind)
        except JobError as e:
            raise HTTPException(404, str(e)) from e
        return FileResponse(
            str(path),
            filename=f"{job}_{kind}{path.suffix}",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.delete("/api/jobs/{job}")
    def delete_job(job: str):
        """删除任务（工作目录）。"""
        try:
            removed = job_service.delete(job)
        except (JobError, OSError) as e:
            raise HTTPException(400, str(e)) from e
        return {"removed": removed}

    @app.post("/api/jobs")
    def create_job(body: dict):
        job = body.get("job")
        input_path = body.get("input")
        sep = body.get("sep")
        if not input_path:
            raise HTTPException(400, "缺少 input 字段")
        if Path(str(input_path)).suffix.lower() != ".xlsx":
            raise HTTPException(
                400,
                "当前只支持 .xlsx。请在 Excel/WPS 中选择“另存为”，保存为 .xlsx 后重新选择。",
            )
        try:
            _preflight_or_error(str(input_path))
            return job_service.create(job, input_path, sep)
        except JobError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/upload")
    async def upload_file(file: UploadFile = File(...)):
        """浏览器原生文件选择器选中的文件上传到这里，保存到 input/ 并返回路径。"""
        filename = os.path.basename(file.filename or "upload.bin")
        # 不可断行空格规范化（与 init_job 一致）
        filename = filename.replace(" ", " ")
        if os.path.splitext(filename)[1].lower() != ".xlsx":
            raise HTTPException(
                400,
                "当前只支持 .xlsx。请在 Excel/WPS 中选择“另存为”，保存为 .xlsx 后重新上传。",
            )
        input_dir = os.path.join(os.path.dirname(settings_path), "input")
        os.makedirs(input_dir, exist_ok=True)
        destination = Path(input_dir) / filename
        if destination.exists():
            destination = Path(input_dir) / f"{uuid.uuid4().hex[:12]}_{filename}"
        temp_path = make_temp_path(destination, suffix=".xlsx")
        try:
            with temp_path.open("wb") as handle:
                while True:
                    content = await file.read(1024 * 1024)
                    if not content:
                        break
                    handle.write(content)
            _preflight_or_error(str(temp_path))
            os.replace(temp_path, destination)
        except HTTPException:
            cleanup_file(temp_path)
            raise
        except OSError as e:
            cleanup_file(temp_path)
            raise HTTPException(500, f"保存上传文件失败，请重试。({type(e).__name__})") from e
        finally:
            await file.close()
        return {
            "path": str(destination),
            "filename": filename,
            "stored_filename": destination.name,
        }

    @app.post("/api/jobs/{job}/extract")
    def job_extract(job: str):
        try:
            return job_service.extract(job)
        except Exception as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/api/jobs/{job}/source")
    def job_source(job: str):
        """返回带 source_revision 的结构化原文列表。"""
        try:
            return job_service.source(job)
        except JobError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/jobs/{job}/translated")
    def job_save_translated(job: str, body: dict):
        """保存结构化译文。"""
        source_revision = body.get("source_revision")
        if not isinstance(source_revision, str) or not source_revision:
            raise HTTPException(409, "缺少 source_revision，请重新载入任务")
        try:
            results = body.get("items")
            if isinstance(results, list):
                return job_service.save_translation(
                    job,
                    source_revision=source_revision,
                    results=results,
                    summary=body.get("summary") if isinstance(body.get("summary"), dict) else None,
                    blocks=body.get("blocks") if isinstance(body.get("blocks"), list) else [],
                    diagnostics=body.get("diagnostics") if isinstance(body.get("diagnostics"), list) else [],
                    review_items=body.get("review_items") if "review_items" in body else None,
                )
            raise HTTPException(400, "items 必须是数组")
        except JobError as e:
            raise HTTPException(409, str(e)) from e

    @app.get("/api/jobs/{job}/translated_file")
    def job_read_translated(job: str):
        """读取当前 revision 的结构化译文。"""
        try:
            return job_service.read_translation(job)
        except JobError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/jobs/{job}/ai_output")
    def job_save_ai_output(job: str, body: dict):
        """保存与 source_revision 绑定的 AI 翻译完整输出。"""
        source_revision = body.get("source_revision")
        if not isinstance(source_revision, str) or not source_revision:
            raise HTTPException(409, "缺少 source_revision，请重新载入任务")
        try:
            results = body.get("results", [])
            if not isinstance(results, list):
                raise HTTPException(400, "results 必须是数组")
            summary = body.get("summary")
            if not isinstance(summary, dict):
                raise HTTPException(400, "AI 输出必须包含完整 summary")
            diagnostics = body.get("diagnostics", [])
            if not isinstance(diagnostics, list):
                raise HTTPException(400, "diagnostics 必须是数组")
            return job_service.save_translation(
                job,
                source_revision=source_revision,
                results=results,
                summary=summary,
                blocks=body.get("blocks") if isinstance(body.get("blocks"), list) else [],
                diagnostics=diagnostics,
                review_items=body.get("review_items") if "review_items" in body else None,
            )
        except JobError as e:
            raise HTTPException(409, str(e)) from e

    @app.get("/api/jobs/{job}/ai_output")
    def job_read_ai_output(job: str):
        """读取当前 revision 的 AI 翻译输出；无则返回空结构。"""
        try:
            return job_service.read_translation(job)
        except JobError as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/api/jobs/{job}/review")
    def job_read_review(
        job: str,
        source_revision: str | None = None,
        translation_revision: str | None = None,
    ):
        """Read review records bound to the current source/translation revision."""
        try:
            return job_service.read_review(
                job,
                source_revision=source_revision,
                translation_revision=translation_revision,
            )
        except JobError as e:
            raise HTTPException(409, str(e)) from e

    @app.put("/api/jobs/{job}/review")
    def job_update_review(job: str, body: dict):
        source_revision = body.get("source_revision")
        if not isinstance(source_revision, str) or not source_revision:
            raise HTTPException(409, "缺少 source_revision，请重新载入任务")
        if "decisions" in body:
            translation_revision = body.get("translation_revision")
            if translation_revision is not None and not isinstance(translation_revision, str):
                raise HTTPException(409, "translation_revision 格式无效，请重新载入任务")
            try:
                return job_service.save_review_decisions(
                    job,
                    source_revision=source_revision,
                    translation_revision=translation_revision,
                    decisions=body.get("decisions"),
                )
            except JobError as e:
                raise HTTPException(409, str(e)) from e
        action = body.get("status") or body.get("action")
        action_map = {
            "accept": "accepted",
            "accepted": "accepted",
            "edit": "edited",
            "edited": "edited",
            "ignore": "ignored",
            "ignored": "ignored",
            "skip": "ignored",
        }
        status = action_map.get(action)
        review_id = body.get("review_id")
        all_pending = bool(
            body.get("all_pending")
            or body.get("all")
            or (isinstance(review_id, str) and review_id in {"all", "*"})
        )
        if status is None:
            raise HTTPException(400, "审核操作必须是 accept、edit 或 ignore")
        try:
            return job_service.update_review(
                job,
                source_revision=source_revision,
                review_id=review_id,
                status=status,
                final_target=body.get("final_target", body.get("target")),
                all_pending=all_pending,
            )
        except JobError as e:
            raise HTTPException(409, str(e)) from e

    @app.post("/api/jobs/{job}/apply")
    def job_apply(job: str, body: dict):
        source_revision = body.get("source_revision")
        translation_revision = body.get("translation_revision")
        if not isinstance(source_revision, str) or not source_revision:
            raise HTTPException(409, "缺少 source_revision，请重新载入任务")
        if not isinstance(translation_revision, str) or not translation_revision:
            raise HTTPException(409, "缺少 translation_revision，请重新载入译文")
        try:
            return job_service.apply(
                job,
                source_revision=source_revision,
                translation_revision=translation_revision,
                sep=body.get("sep"),
                rich_text_policy=body.get("rich_text_policy", "flatten"),
            )
        except JobError as e:
            raise HTTPException(409, str(e)) from e
        except TranslationError as e:
            diagnostics = e.diagnostics_as_dict()
            error_code = (
                diagnostics[0].get("code")
                if diagnostics
                else "xlsx.export_validation_failed"
            )
            message = str(e)
            raise HTTPException(
                status_code=409,
                detail={
                    "message": message,
                    "error_code": error_code,
                    "diagnostics": diagnostics,
                },
            ) from e
        except Exception as e:
            raise HTTPException(400, str(e)) from e

    # ---------- AI 翻译 ----------

    @app.get("/api/mirrors")
    def get_mirrors():
        return {"mirrors": DEFAULT_MIRRORS}

    @app.get("/api/openrouter/models")
    def openrouter_models():
        """从 OpenRouter 拉取模型元数据（id / name / context_length），供设置页填充默认配置。"""
        import requests as _requests

        try:
            r = _requests.get(
                "https://openrouter.ai/api/v1/models",
                timeout=10,
                headers={"User-Agent": "office_translate/1.0"},
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise HTTPException(502, f"拉取 OpenRouter 模型列表失败: {e}") from e
        models = []
        for m in (data.get("data") or []):
            mid = m.get("id")
            if not mid:
                continue
            tp = m.get("top_provider") or {}
            dp = m.get("default_parameters") or {}
            sp = m.get("supported_parameters") or []
            models.append({
                "id": mid,
                "name": m.get("name", ""),
                "context_length": m.get("context_length"),
                "max_completion_tokens": tp.get("max_completion_tokens"),
                "default_temperature": dp.get("temperature"),
                "default_top_p": dp.get("top_p"),
                "supports_reasoning": any(
                    k in sp for k in ("reasoning", "include_reasoning", "reasoning_effort")
                ),
                "reasoning": m.get("reasoning"),  # {mandatory, supported_efforts, default_effort}
                "supported_parameters": sp,
            })
        models.sort(key=lambda m: m["id"])
        return {"models": models, "count": len(models)}

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

    @app.post("/api/providers/test")
    def test_provider(body: dict):
        """测试已保存的 OpenAI 兼容供应商，不把密钥交给浏览器。"""
        import requests as _requests

        settings = _load_settings()
        ai_cfg = settings.get("ai", {})
        provider_key = body.get("provider_id") or body.get("provider_key")
        provider = (ai_cfg.get("providers") or {}).get(provider_key) if provider_key else None
        if not isinstance(provider, dict):
            raise HTTPException(400, "请先选择并保存供应商设置。")
        base_url = (body.get("base_url") or provider.get("base_url") or "").strip().rstrip("/")
        api_key = provider.get("api_key") or ""
        if not base_url:
            raise HTTPException(400, "缺少 base_url")
        url = base_url + "/models"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        start = time.time()
        try:
            r = _requests.get(url, headers=headers, timeout=10)
            latency = int((time.time() - start) * 1000)
            if r.status_code < 400:
                return {"ok": True, "latency_ms": latency, "status": r.status_code}
            return {"ok": False, "latency_ms": latency, "status": r.status_code, "error": f"HTTP {r.status_code}"}
        except Exception as exc:  # noqa: BLE001
            _log_failure("provider_test_failed", "provider.test", exc=exc)
            return {"ok": False, "latency_ms": None, "error": "供应商连接失败，请检查设置或网络。", "error_code": "provider_test_failed"}

    @app.post("/api/operations/{operation_id}/cancel")
    def cancel_operation(operation_id: str):
        with operation_guard:
            record = operation_registry.get(operation_id)
            if record is None:
                raise HTTPException(404, "操作不存在或已过期")
            if record.get("status") != "running":
                return {
                    "operation_id": operation_id,
                    "status": record.get("status"),
                    "already_finished": True,
                }
            record["status"] = "cancelling"
            event = record.get("cancel_event")
            if isinstance(event, threading.Event):
                event.set()
            return {"operation_id": operation_id, "status": "cancelling"}

    @app.get("/api/operations/{operation_id}")
    def operation_status(operation_id: str):
        with operation_guard:
            record = operation_registry.get(operation_id)
            if record is None:
                raise HTTPException(404, "操作不存在或已过期")
            return {
                key: copy.deepcopy(value)
                for key, value in record.items()
                if key != "cancel_event"
            }

    def _translate_with_concurrency(
        texts,
        provider,
        source,
        target,
        concurrency,
        matched=None,
        use_glossary=False,
        cancel_event=None,
    ):
        """Use the same explicit-outcome orchestration for every provider."""
        import inspect

        kwargs: dict[str, Any] = {}
        parameters = inspect.signature(translate_batch).parameters
        if "concurrency" in parameters:
            kwargs["concurrency"] = concurrency
        if "cancel_event" in parameters:
            kwargs["cancel_event"] = cancel_event
        return translate_batch(
            texts,
            provider,
            source,
            target,
            matched if use_glossary else None,
            **kwargs,
        )

    def _summary_for_results(texts: list[str], results: list[dict]) -> dict:
        expected_ids = tuple(range(len(texts)))
        by_id = {result.get("id"): result for result in results}
        if set(by_id) != set(expected_ids) or len(by_id) != len(results):
            raise OutputContractError(
                "invalid_result_set", "服务端翻译结果 ID 集合不完整"
            )
        succeeded_ids = [
            item_id
            for item_id in expected_ids
            if by_id[item_id].get("status") == "succeeded"
        ]
        failed_ids = [
            item_id
            for item_id in expected_ids
            if by_id[item_id].get("status") == "failed"
        ]
        cancelled_ids = [
            item_id
            for item_id in expected_ids
            if by_id[item_id].get("status") == "cancelled"
        ]
        return OperationSummary.from_outcomes(
            expected_ids,
            succeeded_ids=succeeded_ids,
            failed_ids=failed_ids,
            cancelled_ids=cancelled_ids,
        ).to_dict()

    @app.post("/api/translate")
    def translate(body: dict):
        """AI 翻译一批文本。body: {texts, source, target, engine, provider_config, glossary_categories}"""
        settings = _load_settings()
        ai_cfg = settings.get("ai", GUI_CONFIG_DEFAULTS["ai"])
        texts = body.get("texts", [])
        if not isinstance(texts, list) or any(
            not isinstance(text, str) for text in texts
        ):
            raise HTTPException(400, "texts 必须是字符串数组")
        source = body.get("source", ai_cfg.get("source_lang", "en"))
        target = body.get("target", ai_cfg.get("target_lang", "zh-CN"))
        engine = body.get("engine", ai_cfg.get("engine", "google"))
        try:
            concurrency = int(body.get("concurrency", ai_cfg.get("concurrency", 4)))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "concurrency 必须是整数") from exc
        if not 1 <= concurrency <= 64:
            raise HTTPException(400, "concurrency 必须在 1 到 64 之间")
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
                model_config = _effective_model_config(ai_cfg, body)
                output_format = model_config.get("output_format") or "xml"
                response_format = model_config.get("response_format") or "none"
                if response_format not in {
                    "auto",
                    "none",
                    "json_object",
                    "json_schema",
                }:
                    raise HTTPException(
                        400,
                        "response_format 必须是 auto/none/json_object/json_schema",
                    )
                if (
                    output_format != "json"
                    and response_format in {"json_object", "json_schema"}
                ):
                    raise HTTPException(
                        400, "json_object/json_schema 仅支持 JSON 输出协议"
                    )
                base_url, api_key, model = _resolve_openai_config(ai_cfg, body)
                provider = OpenAICompatProvider(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    model_config=model_config,
                )
                results = _translate_with_concurrency(
                    texts, provider, source, target, concurrency, matched=matched, use_glossary=True
                )
            else:
                raise HTTPException(400, f"未知引擎: {engine}")
            return {
                "results": results,
                "summary": _summary_for_results(texts, results),
                "matched_glossary": matched,
            }
        except HTTPException:
            raise
        except ProviderError as exc:
            _log_failure("provider_error", "translate", exc=exc)
            raise HTTPException(
                502,
                {"message": "翻译服务失败，请重试。", "error_code": "provider_error"},
            ) from exc
        except Exception as exc:
            _log_failure("translate_failed", "translate", exc=exc)
            raise HTTPException(
                500,
                {"message": "翻译失败，请重试。", "error_code": "translate_failed"},
            ) from exc

    @app.post("/api/translate/stream")
    async def translate_stream_api(body: dict):
        """Stream original item outcomes while keeping provider segments private."""
        from fastapi.responses import StreamingResponse
        from concurrent.futures import ThreadPoolExecutor
        from queue import Queue
        import inspect
        import json as _json

        settings = _load_settings()
        ai_cfg = settings.get("ai", GUI_CONFIG_DEFAULTS["ai"])
        texts = body.get("texts", [])
        if not isinstance(texts, list) or any(
            not isinstance(text, str) for text in texts
        ):
            raise HTTPException(400, "texts 必须是字符串数组")
        source = body.get("source", ai_cfg.get("source_lang", "en"))
        target = body.get("target", ai_cfg.get("target_lang", "zh-CN"))
        engine = body.get("engine", ai_cfg.get("engine", "google"))
        categories = body.get("glossary_categories")

        glossary = load_glossary(glossary_path)
        matched = match_terms(glossary, categories, texts)
        glossary_prompt = format_glossary_prompt(matched)

        try:
            concurrency = int(body.get("concurrency", ai_cfg.get("concurrency", 4)))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "concurrency 必须是整数") from exc
        if not 1 <= concurrency <= 64:
            raise HTTPException(400, "concurrency 必须在 1 到 64 之间")

        try:
            if engine == "google":
                mirrors = body.get("mirrors") or ai_cfg.get("mirrors") or DEFAULT_MIRRORS
                provider = GoogleProvider(mirrors)
                model_config: dict[str, Any] = {}
                output_format = "xml"
                model_context = None
                max_output_tokens = None
            elif engine == "openai":
                model_config = _effective_model_config(ai_cfg, body)
                base_url, api_key, model = _resolve_openai_config(ai_cfg, body)
                provider = OpenAICompatProvider(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    model_config=model_config,
                )
                provider_config = getattr(provider, "config", None)
                output_format = getattr(
                    provider_config,
                    "output_format",
                    model_config.get("output_format") or "xml",
                )
                response_format = getattr(
                    provider_config,
                    "response_format",
                    model_config.get("response_format") or "none",
                )
                if output_format not in {"text", "json", "xml"}:
                    raise HTTPException(400, "output_format 必须是 text/json/xml")
                if response_format not in {
                    "auto",
                    "none",
                    "json_object",
                    "json_schema",
                }:
                    raise HTTPException(
                        400,
                        "response_format 必须是 auto/none/json_object/json_schema",
                    )
                if output_format != "json" and response_format in {
                    "json_object",
                    "json_schema",
                }:
                    raise HTTPException(400, "json_object/json_schema 仅支持 JSON 输出协议")
                model_context = getattr(
                    provider_config,
                    "model_context",
                    model_config.get("model_context") or body.get("model_context"),
                )
                max_output_tokens = getattr(
                    provider_config,
                    "max_output_tokens",
                    model_config.get("max_completion_tokens")
                    or model_config.get("max_tokens"),
                )
            else:
                raise HTTPException(400, f"未知引擎: {engine}")

            total = len(texts)
            source_request_items = [
                TranslationRequestItem(id=item_id, text=text)
                for item_id, text in enumerate(texts)
            ]
            system_prompt = build_system_prompt(
                source,
                target,
                "",
                output_format,
            )
            chunks = chunk_request_items(
                source_request_items,
                engine,
                model_context=model_context,
                system_prompt=system_prompt,
                glossary=glossary_prompt,
                output_format=output_format,
                max_output_tokens=max_output_tokens,
            )

            all_request_items = [item for chunk in chunks for item in chunk]
            segment_by_id = {item.id: item for item in all_request_items}
            if len(segment_by_id) != len(all_request_items):
                raise OutputContractError("invalid_request", "分块后出现重复请求 ID")
            source_segments: dict[int, list[TranslationRequestItem]] = {
                item_id: [] for item_id in range(total)
            }
            for item in all_request_items:
                source_id = item.source_id if item.source_id is not None else item.id
                if source_id not in source_segments:
                    raise OutputContractError(
                        "segment_reassembly_invalid",
                        f"分块结果引用了未知原始 ID {source_id}",
                    )
                source_segments[source_id].append(item)
            for source_id, items in source_segments.items():
                if not items:
                    raise OutputContractError(
                        "segment_reassembly_invalid",
                        f"分块结果遗漏了原始 ID {source_id}",
                    )
                items.sort(
                    key=lambda item: (
                        item.segment_index
                        if item.segment_index is not None
                        else 0
                    )
                )

            chunk_block_ids = [
                (
                    chunk[0].source_id
                    if chunk and chunk[0].source_id is not None
                    else chunk[0].id
                )
                for chunk in chunks
            ]

            operation_id = _new_operation(total=total)
            operation_record = operation_registry[operation_id]
            cancel_event = operation_record["cancel_event"]

            def event_stream():
                def encode(payload: dict[str, Any]) -> str:
                    return (
                        "data: "
                        + _json.dumps(payload, ensure_ascii=False, allow_nan=False)
                        + "\n\n"
                    )

                yield encode(
                    {
                        "type": "meta",
                        "operation_id": operation_id,
                        "total": total,
                        "chunks": len(chunks),
                        "blocks": chunk_block_ids,
                        "matched_glossary": matched,
                    }
                )
                succeeded_ids: set[int] = set()
                failed_ids: set[int] = set()
                cancelled_ids: set[int] = set()

                def progress_event() -> dict[str, Any]:
                    completed = len(succeeded_ids) + len(failed_ids) + len(cancelled_ids)
                    with operation_guard:
                        operation_record.update(
                            {
                                "completed": completed,
                                "succeeded": len(succeeded_ids),
                                "failed": len(failed_ids),
                                "cancelled": len(cancelled_ids),
                            }
                        )
                    return {
                        "type": "progress",
                        "completed": completed,
                        "total": total,
                        "succeeded": len(succeeded_ids),
                        "failed": len(failed_ids),
                        "cancelled": len(cancelled_ids),
                        "progress": int(completed / total * 100) if total else 100,
                    }

                chunk_states: list[dict[str, Any]] = []
                for chunk_index, chunk in enumerate(chunks):
                    chunk_states.append(
                        {
                            "expected_ids": tuple(item.id for item in chunk),
                            "content_parts": [],
                            "previewed_ids": set(),
                            "successes": {},
                            "failures": {},
                            "cancelled_ids": set(),
                            "duplicate_ids": set(),
                            "invalid_error": None,
                            "cancelled": False,
                            "thinking_parts": [],
                            "block_id": chunk_block_ids[chunk_index],
                        }
                    )

                segment_results: dict[int, dict[str, Any]] = {}
                segment_previews: dict[int, dict[str, Any]] = {}
                previewed_source_ids: set[int] = set()
                published_source_ids: set[int] = set()

                def source_preview_payloads() -> list[dict[str, Any]]:
                    payloads: list[dict[str, Any]] = []
                    for source_id in range(total):
                        if source_id in previewed_source_ids:
                            continue
                        segments = source_segments[source_id]
                        if any(item.id not in segment_previews for item in segments):
                            continue
                        translations = {
                            item.id: segment_previews[item.id]["translation"]
                            for item in segments
                        }
                        if len(segments) == 1 and segments[0].source_id is None:
                            translation = translations[segments[0].id]
                        else:
                            translation = reassemble_segments(
                                segments,
                                translations,
                                {source_id: texts[source_id]},
                            )[source_id]
                        terms: list[dict[str, str]] = []
                        for item in segments:
                            terms.extend(
                                segment_previews[item.id].get("uncertain_terms", [])
                            )
                        previewed_source_ids.add(source_id)
                        payloads.append(
                            {
                                "type": "item_preview",
                                "id": source_id,
                                "block_id": source_id,
                                "translation": translation,
                                "uncertain_terms": terms,
                            }
                        )
                    return payloads

                def source_result_payloads() -> list[dict[str, Any]]:
                    payloads: list[dict[str, Any]] = []
                    for source_id in range(total):
                        if source_id in published_source_ids:
                            continue
                        segments = source_segments[source_id]
                        if any(item.id not in segment_results for item in segments):
                            continue
                        outcomes = [segment_results[item.id] for item in segments]
                        statuses = {outcome["status"] for outcome in outcomes}
                        thinking_parts: list[str] = []
                        thinking_blocks: set[int] = set()
                        diagnostic = None
                        for outcome in outcomes:
                            block_id = outcome.get("block_id")
                            thinking = outcome.get("thinking") or ""
                            if thinking and block_id not in thinking_blocks:
                                thinking_blocks.add(block_id)
                                thinking_parts.append(thinking)
                            if diagnostic is None and outcome.get("diagnostic") is not None:
                                diagnostic = outcome["diagnostic"]
                        thinking = "\n".join(thinking_parts)
                        common = {
                            "id": source_id,
                            "block_id": source_id,
                            "uncertain_terms": [],
                            "thinking": thinking,
                        }
                        if "cancelled" in statuses:
                            payload = {
                                "type": "item_cancelled",
                                **common,
                                "translation": texts[source_id],
                                "error_code": "cancelled",
                                "error": "用户已停止此操作",
                            }
                            cancelled_ids.add(source_id)
                        elif "failed" in statuses:
                            failure = next(
                                outcome
                                for outcome in outcomes
                                if outcome["status"] == "failed"
                            )
                            payload = {
                                "type": "item_failed",
                                **common,
                                "translation": texts[source_id],
                                "error_code": failure.get("error_code")
                                or "provider_error",
                                "error": failure.get("error") or "翻译失败",
                            }
                            failed_ids.add(source_id)
                        else:
                            translations = {
                                item.id: segment_results[item.id]["translation"]
                                for item in segments
                            }
                            if len(segments) == 1 and segments[0].source_id is None:
                                translation = translations[segments[0].id]
                            else:
                                translation = reassemble_segments(
                                    segments,
                                    translations,
                                    {source_id: texts[source_id]},
                                )[source_id]
                            terms: list[dict[str, str]] = []
                            for outcome in outcomes:
                                terms.extend(outcome.get("uncertain_terms", []))
                            payload = {
                                "type": "item_succeeded",
                                **common,
                                "translation": translation,
                                "uncertain_terms": terms,
                            }
                            succeeded_ids.add(source_id)
                        if diagnostic is not None:
                            payload["diagnostic"] = diagnostic
                        published_source_ids.add(source_id)
                        payloads.append(payload)
                    return payloads

                def set_invalid(
                    state: dict[str, Any],
                    code: str,
                    message: str,
                    diagnostic: Any = None,
                ) -> None:
                    if state["invalid_error"] is None:
                        state["invalid_error"] = (code, message, diagnostic)

                def record_terminal(
                    state: dict[str, Any],
                    item_id: int,
                    status: str,
                    outcome: dict[str, Any] | None = None,
                ) -> None:
                    expected_ids = set(state["expected_ids"])
                    if item_id not in expected_ids:
                        set_invalid(
                            state,
                            "id_set_mismatch",
                            f"Provider 返回了未知 ID {item_id}",
                        )
                        return
                    stores = (
                        state["successes"],
                        state["failures"],
                        state["cancelled_ids"],
                    )
                    if any(item_id in store for store in stores):
                        state["successes"].pop(item_id, None)
                        state["failures"].pop(item_id, None)
                        state["cancelled_ids"].discard(item_id)
                        state["duplicate_ids"].add(item_id)
                        set_invalid(
                            state,
                            "duplicate_id",
                            f"Provider 重复返回了 ID {item_id}",
                        )
                        return
                    if status == "succeeded":
                        state["successes"][item_id] = outcome
                    elif status == "failed":
                        state["failures"][item_id] = outcome
                    else:
                        state["cancelled_ids"].add(item_id)

                def handle_provider_event(
                    chunk_index: int,
                    event: Any,
                ) -> list[dict[str, Any]]:
                    state = chunk_states[chunk_index]
                    if cancel_event.is_set():
                        state["cancelled"] = True
                        return []
                    if not isinstance(event, dict):
                        set_invalid(
                            state,
                            "invalid_provider_event",
                            "Provider 返回了非对象事件",
                        )
                        return []
                    event_type = event.get("type")
                    if event_type == "_worker_failed":
                        set_invalid(
                            state,
                            "provider_error",
                            "翻译块异常",
                            event.get("diagnostic"),
                        )
                        return []
                    if event_type in {"thinking", "content"}:
                        delta = event.get("delta")
                        if not isinstance(delta, str):
                            set_invalid(
                                state,
                                "invalid_provider_event",
                                f"Provider 的 {event_type} 事件缺少字符串 delta",
                            )
                            return []
                        if event_type == "thinking":
                            state["thinking_parts"].append(delta)
                            return [
                                {
                                    "type": "thinking",
                                    "id": state["block_id"],
                                    "block_id": state["block_id"],
                                    "delta": delta,
                                }
                            ]
                        state["content_parts"].append(delta)
                        previews = extract_preview_items(
                            "".join(state["content_parts"]),
                            output_format,
                            start_id=state["expected_ids"][0],
                            expected_ids=state["expected_ids"],
                        )
                        for preview in previews:
                            item_id = preview.get("id")
                            if (
                                item_id in state["previewed_ids"]
                                or item_id not in state["expected_ids"]
                            ):
                                continue
                            try:
                                parsed = validate_result_item(
                                    {
                                        "id": item_id,
                                        "translation": preview.get("translation"),
                                        "uncertain_terms": preview.get(
                                            "uncertain_terms", []
                                        ),
                                    }
                                )
                            except OutputContractError:
                                continue
                            state["previewed_ids"].add(item_id)
                            segment_previews[item_id] = parsed.to_dict()
                        return source_preview_payloads()
                    if event_type == "block_succeeded":
                        raw_items = event.get("items")
                        thinking = event.get("thinking") or ""
                        if not isinstance(raw_items, list) or not isinstance(
                            thinking, str
                        ):
                            set_invalid(
                                state,
                                "invalid_provider_event",
                                "Provider 成功事件缺少合法 items/thinking",
                                event.get("diagnostic"),
                            )
                            return []
                        event_ids = [
                            item.get("id")
                            for item in raw_items
                            if isinstance(item, dict)
                        ]
                        if len(event_ids) != len(raw_items):
                            set_invalid(
                                state,
                                "invalid_provider_event",
                                "Provider 成功事件包含非对象条目",
                                event.get("diagnostic"),
                            )
                            return []
                        try:
                            parsed_items = validate_result_items(raw_items, event_ids)
                        except OutputContractError as exc:
                            set_invalid(state, exc.code, str(exc), exc.diagnostic)
                            return []
                        if thinking:
                            state["thinking_parts"] = [thinking]
                        for parsed in parsed_items:
                            record_terminal(
                                state,
                                parsed.id,
                                "succeeded",
                                {
                                    **parsed.to_dict(),
                                    "status": "succeeded",
                                    "thinking": thinking,
                                    "diagnostic": event.get("diagnostic"),
                                    "block_id": state["block_id"],
                                },
                            )
                        return []
                    if event_type == "block_failed":
                        event_ids = event.get("ids")
                        error_code = event.get("error_code") or "provider_error"
                        error_message = event.get("error") or "翻译块失败"
                        thinking = event.get("thinking") or ""
                        if (
                            not isinstance(event_ids, list)
                            or any(
                                not isinstance(item_id, int)
                                or isinstance(item_id, bool)
                                for item_id in event_ids
                            )
                            or not all(
                                isinstance(value, str)
                                for value in (error_code, error_message, thinking)
                            )
                        ):
                            set_invalid(
                                state,
                                "invalid_provider_event",
                                "Provider 失败事件缺少合法 IDs/error/thinking",
                                event.get("diagnostic"),
                            )
                            return []
                        if thinking:
                            state["thinking_parts"] = [thinking]
                        for item_id in event_ids:
                            record_terminal(
                                state,
                                item_id,
                                "failed",
                                {
                                    "id": item_id,
                                    "status": "failed",
                                    "error_code": error_code,
                                    "error": error_message,
                                    "thinking": thinking,
                                    "diagnostic": event.get("diagnostic"),
                                    "block_id": state["block_id"],
                                },
                            )
                        return []
                    if event_type == "block_cancelled":
                        event_ids = event.get("ids")
                        if not isinstance(event_ids, list) or any(
                            not isinstance(item_id, int) or isinstance(item_id, bool)
                            for item_id in event_ids
                        ):
                            set_invalid(
                                state,
                                "invalid_provider_event",
                                "Provider 取消事件缺少有效 IDs",
                                event.get("diagnostic"),
                            )
                            return []
                        state["cancelled"] = True
                        for item_id in event_ids:
                            record_terminal(state, item_id, "cancelled")
                        return []
                    set_invalid(
                        state,
                        "invalid_provider_event",
                        f"Provider 返回了未知事件类型: {event_type!r}",
                    )
                    return []

                def finalize_chunk(chunk_index: int) -> None:
                    state = chunk_states[chunk_index]
                    expected_ids = state["expected_ids"]
                    if cancel_event.is_set() or state["cancelled"]:
                        # Results from this block have not been published yet.
                        # Cancellation therefore wins over queued successes.
                        state["successes"].clear()
                        state["failures"].clear()
                        state["cancelled_ids"] = set(expected_ids)
                    else:
                        covered = (
                            set(state["successes"])
                            | set(state["failures"])
                            | set(state["cancelled_ids"])
                            | set(state["duplicate_ids"])
                        )
                        if covered != set(expected_ids) and state["invalid_error"] is None:
                            set_invalid(
                                state,
                                "id_set_mismatch",
                                "Provider 块结果的 ID 集合与输入不一致",
                            )
                        code, message, diagnostic = state["invalid_error"] or (
                            "stream_incomplete",
                            "翻译流未返回该分段的最终结果",
                            None,
                        )
                        for item_id in state["duplicate_ids"]:
                            state["failures"][item_id] = {
                                "id": item_id,
                                "status": "failed",
                                "error_code": "duplicate_id",
                                "error": f"Provider 重复返回了 ID {item_id}",
                                "thinking": "".join(state["thinking_parts"]),
                                "diagnostic": diagnostic,
                                "block_id": state["block_id"],
                            }
                        covered = (
                            set(state["successes"])
                            | set(state["failures"])
                            | set(state["cancelled_ids"])
                        )
                        for item_id in expected_ids:
                            if item_id not in covered:
                                state["failures"][item_id] = {
                                    "id": item_id,
                                    "status": "failed",
                                    "error_code": code,
                                    "error": message,
                                    "thinking": "".join(state["thinking_parts"]),
                                    "diagnostic": diagnostic,
                                    "block_id": state["block_id"],
                                }

                        # A structurally complete streamed item remains usable
                        # when only another item or the enclosing document failed.
                        for item_id in tuple(state["failures"]):
                            if (
                                item_id in state["duplicate_ids"]
                                or item_id not in segment_previews
                                or not state["content_parts"]
                            ):
                                continue
                            preview = segment_previews[item_id]
                            failure = state["failures"].pop(item_id)
                            state["successes"][item_id] = {
                                **preview,
                                "status": "succeeded",
                                "thinking": failure.get("thinking", ""),
                                "diagnostic": failure.get("diagnostic"),
                                "block_id": state["block_id"],
                            }

                    for item_id, outcome in state["successes"].items():
                        segment_results[item_id] = outcome
                    for item_id, outcome in state["failures"].items():
                        segment_results[item_id] = outcome
                    for item_id in state["cancelled_ids"]:
                        segment_results[item_id] = {
                            "id": item_id,
                            "status": "cancelled",
                            "translation": segment_by_id[item_id].text,
                            "uncertain_terms": [],
                            "error_code": "cancelled",
                            "error": "用户已停止此操作",
                            "thinking": "".join(state["thinking_parts"]),
                            "diagnostic": None,
                            "block_id": state["block_id"],
                        }

                event_queue: Queue[tuple[int, Any, bool]] = Queue()

                def stream_chunk(chunk_index: int) -> None:
                    chunk = chunks[chunk_index]
                    stream_kwargs: dict[str, Any] = {}
                    if engine == "openai":
                        stream_kwargs["glossary_entries"] = matched
                    try:
                        stream_method = provider.translate_stream
                        if "cancel_event" in inspect.signature(stream_method).parameters:
                            stream_kwargs["cancel_event"] = cancel_event
                        for event in stream_method(
                            chunk,
                            source,
                            target,
                            **stream_kwargs,
                        ):
                            event_queue.put((chunk_index, event, False))
                    except Exception as exc:  # noqa: BLE001
                        event_queue.put(
                            (
                                chunk_index,
                                {
                                    "type": "_worker_failed",
                                    "diagnostic": {
                                        "exception_type": type(exc).__name__
                                    },
                                },
                                False,
                            )
                        )
                    finally:
                        event_queue.put((chunk_index, None, True))

                if chunks:
                    worker_count = min(concurrency, len(chunks))
                    pool = ThreadPoolExecutor(max_workers=worker_count)
                    futures = [
                        pool.submit(stream_chunk, chunk_index)
                        for chunk_index in range(len(chunks))
                    ]
                    remaining = len(futures)
                    try:
                        while remaining:
                            chunk_index, event, finished = event_queue.get()
                            if finished:
                                finalize_chunk(chunk_index)
                                remaining -= 1
                                for payload in source_result_payloads():
                                    yield encode(payload)
                                    yield encode(progress_event())
                                continue
                            for payload in handle_provider_event(chunk_index, event):
                                yield encode(payload)
                    finally:
                        if remaining:
                            cancel_event.set()
                        pool.shutdown(wait=True, cancel_futures=True)
                        if remaining:
                            # The client may close the SSE connection before
                            # the cancellation summary can be sent.  Keep the
                            # operation registry truthful even when no final
                            # event reaches the browser.
                            missing = set(range(total)) - succeeded_ids - failed_ids - cancelled_ids
                            cancelled_ids.update(missing)
                            disconnected_summary = OperationSummary.from_outcomes(
                                range(total),
                                succeeded_ids=succeeded_ids,
                                failed_ids=failed_ids,
                                cancelled_ids=cancelled_ids,
                            ).to_dict()
                            _finish_operation(operation_id, disconnected_summary)

                # A segmented source item may become complete only after the
                # final segment's worker finishes.  Publish it using its
                # original ID before applying the defensive fallback below.
                for payload in source_result_payloads():
                    yield encode(payload)
                    yield encode(progress_event())

                unaccounted = set(range(total)) - succeeded_ids - failed_ids - cancelled_ids
                for item_id in sorted(unaccounted):
                    if cancel_event.is_set():
                        cancelled_ids.add(item_id)
                        yield encode(
                            {
                                "type": "item_cancelled",
                                "id": item_id,
                                "block_id": item_id,
                                "translation": texts[item_id],
                                "uncertain_terms": [],
                                "thinking": "",
                                "error_code": "cancelled",
                                "error": "用户已停止此操作",
                            }
                        )
                    else:
                        failed_ids.add(item_id)
                        yield encode(
                            {
                                "type": "item_failed",
                                "id": item_id,
                                "block_id": item_id,
                                "translation": texts[item_id],
                                "uncertain_terms": [],
                                "thinking": "",
                                "error_code": "stream_incomplete",
                                "error": "翻译流未返回该条目的最终结果",
                            }
                        )
                    yield encode(progress_event())

                summary = OperationSummary.from_outcomes(
                    range(total),
                    succeeded_ids=succeeded_ids,
                    failed_ids=failed_ids,
                    cancelled_ids=cancelled_ids,
                )
                summary_payload = summary.to_dict()
                _finish_operation(operation_id, summary_payload)
                yield encode({"type": "summary", **summary_payload})

            return StreamingResponse(
                event_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        except HTTPException:
            raise
        except ProviderError as e:
            status = 400 if e.code in {
                "invalid_config",
                "unsupported_model_parameter",
                "response_format_unsupported",
            } else 502
            raise HTTPException(status, str(e)) from e
        except Exception as e:
            raise HTTPException(500, str(e)) from e

    # ---------- 审核与术语库 ----------

    @app.get("/api/glossary")
    def get_glossary():
        try:
            return glossary_store.load()
        except GlossaryError as exc:
            _log_failure("glossary_load_failed", "glossary.load", exc=exc)
            raise HTTPException(500, "术语库无法读取，请检查本地诊断日志。") from exc

    @app.post("/api/glossary/terms")
    def add_glossary_term(body: dict):
        category = body.get("category", "默认")
        source = body.get("source", "")
        target = body.get("target", "")
        note = body.get("note", "")
        try:
            entry = glossary_store.update(
                lambda data: add_term(data, category, source, target, note)
            )
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
            def mutate(data):
                entries = data.get("categories", {}).get(category, [])
                for entry in entries:
                    if entry["source"] == source:
                        if target:
                            entry["target"] = target
                        if note is not None:
                            entry["note"] = note
                        return entry
                raise HTTPException(404, f"术语不存在: {category}/{source}")

            return glossary_store.update(mutate)
        except HTTPException:
            raise
        except GlossaryError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/api/glossary/terms")
    def delete_glossary_term(category: str, source: str):
        try:
            ok = glossary_store.update(lambda data: remove_term(data, category, source))
        except GlossaryError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"removed": ok}

    @app.delete("/api/glossary/categories")
    def delete_glossary_category(category: str):
        """删除整个术语类别。"""
        def mutate(data):
            categories = data.get("categories", {})
            if category not in categories:
                raise HTTPException(404, f"类别不存在: {category}")
            count = len(categories[category])
            del categories[category]
            return count

        try:
            count = glossary_store.update(mutate)
        except HTTPException:
            raise
        except GlossaryError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"removed": True, "count": count}

    @app.post("/api/glossary/batch-delete")
    def delete_glossary_terms_batch(body: dict):
        """批量删除术语。body: {category, sources: [..]}"""
        category = body.get("category", "")
        sources = body.get("sources", [])
        if not isinstance(sources, list) or any(not isinstance(source, str) for source in sources):
            raise HTTPException(400, "sources 必须是字符串数组")

        def mutate(data):
            entries = data.get("categories", {}).get(category, [])
            remaining = [entry for entry in entries if entry["source"] not in set(sources)]
            removed = len(entries) - len(remaining)
            data["categories"][category] = remaining
            return removed

        try:
            removed = glossary_store.update(mutate)
        except GlossaryError as exc:
            raise HTTPException(400, str(exc)) from exc
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
