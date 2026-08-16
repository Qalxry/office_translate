"""翻译 Provider 抽象与实现。

- `Provider`：抽象基类，定义翻译接口（单条 / 批量）。
- `OpenAICompatProvider`：OpenAI 兼容 API（Claude / OpenAI / DeepSeek / Ollama 等）。
- `GoogleProvider`：Google 翻译，支持多个镜像站；
  通过 `MirrorPool` 实现失败自动切换与冷却。
"""

from __future__ import annotations

import abc
import copy
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional

import requests

from .contracts import (
    OutputContractError,
    ProviderCompletion,
    TRANSLATION_SCHEMA,
    TranslationBlockResult,
    TranslationRequestItem,
    parse_result_by_format,
)


class ProviderError(Exception):
    """翻译请求失败（含所有镜像站失败）。"""

    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_error",
        diagnostic: Any = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostic = diagnostic
        self.retryable = retryable


@dataclass(frozen=True)
class ProviderConfig:
    """Validated effective model configuration shared by every request path."""

    base_url: str
    model: str
    temperature: float | None
    model_context: int | None
    output_format: str
    response_format: str
    request_params: Mapping[str, Any]
    extra_body: Mapping[str, Any]
    max_output_tokens: int | None

    @classmethod
    def from_model_config(
        cls,
        *,
        base_url: str,
        model: str,
        temperature: float | None,
        model_config: Mapping[str, Any] | None,
    ) -> "ProviderConfig":
        if not isinstance(base_url, str) or not base_url.strip():
            raise ProviderError("缺少 API base_url", code="invalid_config", retryable=False)
        if not isinstance(model, str) or not model.strip():
            raise ProviderError("缺少模型名称", code="invalid_config", retryable=False)
        if temperature is not None and (
            not isinstance(temperature, (int, float)) or isinstance(temperature, bool)
            or not math.isfinite(float(temperature))
        ):
            raise ProviderError("temperature 必须是有限数字", code="invalid_config", retryable=False)

        sdk_params = {
            "temperature", "max_tokens", "max_completion_tokens", "top_p", "top_logprobs",
            "reasoning_effort", "frequency_penalty", "presence_penalty", "seed", "stop",
            "n", "user", "logit_bias", "logprobs", "prediction", "metadata", "modalities",
            "moderation", "safety_identifier", "service_tier", "store", "stream_options",
            "verbosity", "audio", "web_search_options",
        }
        # These are known provider-specific OpenAI-compatible body fields.
        # Arbitrary vendor fields must be explicitly nested under ``extra``;
        # silently forwarding every typo as a fake supported parameter is unsafe.
        extra_body_params = {"thinking", "top_k"}
        reserved = {
            "model_context", "response_format", "output_format", "extra", "_effort_options"
        }
        if model_config is not None and not isinstance(model_config, Mapping):
            raise ProviderError("model_config 必须是对象", code="invalid_config", retryable=False)
        mc = copy.deepcopy(dict(model_config or {}))
        unknown = sorted(
            key for key in mc
            if key not in sdk_params and key not in extra_body_params and key not in reserved
            and not key.startswith("_")
        )
        if unknown:
            raise ProviderError(
                f"不支持的模型参数: {', '.join(unknown)}；请放入 extra 明确传递",
                code="unsupported_model_parameter",
                retryable=False,
            )
        model_context = mc.get("model_context")
        if model_context is not None and (
            not isinstance(model_context, int)
            or isinstance(model_context, bool)
            or model_context <= 0
        ):
            raise ProviderError("model_context 必须是正整数", code="invalid_config", retryable=False)
        for name in ("max_tokens", "max_completion_tokens", "top_k", "n", "seed"):
            value = mc.get(name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value <= 0
            ):
                raise ProviderError(f"{name} 必须是正整数", code="invalid_config", retryable=False)
        if mc.get("max_tokens") is not None and mc.get("max_completion_tokens") is not None:
            raise ProviderError(
                "max_tokens 与 max_completion_tokens 不能同时设置",
                code="invalid_config",
                retryable=False,
            )
        for name in ("temperature", "top_p", "frequency_penalty", "presence_penalty"):
            value = mc.get(name)
            if value is not None and (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
            ):
                raise ProviderError(f"{name} 必须是有限数字", code="invalid_config", retryable=False)
        if mc.get("top_p") is not None and not 0 <= float(mc["top_p"]) <= 1:
            raise ProviderError("top_p 必须在 0 到 1 之间", code="invalid_config", retryable=False)
        output_format = mc.get("output_format") or "xml"
        if output_format not in {"text", "json", "xml"}:
            raise ProviderError("output_format 必须是 text/json/xml", code="invalid_config", retryable=False)
        response_format = mc.get("response_format") or "none"
        if response_format not in {"auto", "none", "json_object", "json_schema"}:
            raise ProviderError(
                "response_format 必须是 auto/none/json_object/json_schema",
                code="invalid_config",
                retryable=False,
            )
        if output_format != "json" and response_format in {"json_object", "json_schema"}:
            raise ProviderError(
                "json_object/json_schema 仅支持 JSON 输出协议",
                code="invalid_config",
                retryable=False,
            )

        request_params: dict[str, Any] = {}
        extra_body: dict[str, Any] = {}
        for key, value in mc.items():
            if value is None or key.startswith("_") or key in reserved:
                continue
            if key in sdk_params:
                request_params[key] = value
            else:
                extra_body[key] = value
        extra = mc.get("extra")
        if extra is not None:
            if not isinstance(extra, Mapping) or any(not isinstance(key, str) for key in extra):
                raise ProviderError("extra 必须是字符串键对象", code="invalid_config", retryable=False)
            extra_body.update({key: value for key, value in extra.items() if value is not None})
        if "temperature" not in request_params and temperature is not None:
            request_params["temperature"] = temperature
        return cls(
            base_url=base_url.rstrip("/"),
            model=model,
            temperature=float(temperature) if temperature is not None else None,
            model_context=model_context,
            output_format=output_format,
            response_format=response_format,
            request_params=MappingProxyType(dict(request_params)),
            extra_body=MappingProxyType(dict(extra_body)),
            max_output_tokens=request_params.get("max_completion_tokens")
            or request_params.get("max_tokens"),
        )


def _cancel_requested(cancel_event: Any) -> bool:
    if cancel_event is None:
        return False
    checker = getattr(cancel_event, "is_set", None)
    if callable(checker):
        return bool(checker())
    checker = getattr(cancel_event, "is_cancelled", None)
    if callable(checker):
        return bool(checker())
    if callable(cancel_event):
        return bool(cancel_event())
    raise TypeError("cancel_event 必须提供 is_set()/is_cancelled() 或可调用接口")


def _cancelled_outcome(item: TranslationRequestItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "translation": item.text,
        "uncertain_terms": [],
        "status": "cancelled",
        "error": "翻译已取消",
        "error_code": "cancelled",
        "diagnostic": None,
    }


@dataclass
class TranslationResult:
    """一条文本的翻译结果（由模型自报不确定术语）。"""

    translation: str
    uncertain_terms: list[dict] = field(default_factory=list)


class Provider(abc.ABC):
    """翻译 Provider 抽象基类。"""

    name: str = "abstract"

    @abc.abstractmethod
    def translate(self, text: str, source: str, target: str) -> str:
        """翻译单条文本，返回译文。失败抛 ProviderError。"""

    def translate_batch(
        self,
        texts: list[str],
        source: str,
        target: str,
        concurrency: int = 1,
    ) -> list[str]:
        """批量翻译，返回确定性顺序的译文；失败或取消会明确抛错。"""
        outcomes = self.translate_batch_outcomes(
            texts, source, target, concurrency=concurrency
        )
        for outcome in outcomes:
            if outcome["status"] != "succeeded":
                raise ProviderError(
                    outcome["error"],
                    code=outcome["error_code"],
                    diagnostic=outcome.get("diagnostic"),
                    retryable=outcome["status"] != "cancelled",
                )
        return [outcome["translation"] for outcome in outcomes]

    def translate_batch_outcomes(
        self,
        texts: list[str],
        source: str,
        target: str,
        *,
        concurrency: int = 1,
        cancel_event: Any = None,
    ) -> list[dict[str, Any]]:
        """Translate with bounded workers and explicit per-item outcomes.

        Futures are always folded back into input order.  Once cancellation is
        observed, completed-but-not-yet-published successes are intentionally
        converted to ``cancelled`` and pending futures are not published.
        """
        if not isinstance(texts, list) or any(not isinstance(text, str) for text in texts):
            raise ProviderError("texts 必须是字符串数组", code="invalid_request", retryable=False)
        max_workers = max(1, int(concurrency))
        items = [TranslationRequestItem(id=index, text=text) for index, text in enumerate(texts)]
        results: list[dict[str, Any] | None] = [None] * len(items)

        def run(item: TranslationRequestItem) -> dict[str, Any]:
            try:
                if _cancel_requested(cancel_event):
                    return _cancelled_outcome(item)
                translation = self.translate(item.text, source, target)
                if not isinstance(translation, str) or (item.text and not translation.strip()):
                    raise ProviderError("翻译服务返回了空响应", code="empty_response")
                return {
                    "id": item.id,
                    "translation": translation,
                    "uncertain_terms": [],
                    "status": "succeeded",
                    "error": None,
                    "error_code": None,
                    "diagnostic": None,
                }
            except ProviderError as exc:
                return {
                    **(
                        _cancelled_outcome(item)
                        if exc.code == "cancelled"
                        else {
                        "id": item.id,
                        "translation": item.text,
                        "uncertain_terms": [],
                        "status": "failed",
                        "error": str(exc),
                        "error_code": exc.code,
                        "diagnostic": exc.diagnostic,
                        }
                    )
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "id": item.id,
                    "translation": item.text,
                    "uncertain_terms": [],
                    "status": "failed",
                    "error": f"翻译服务异常（{type(exc).__name__}）",
                    "error_code": "provider_error",
                    "diagnostic": {"exception_type": type(exc).__name__},
                }

        if not items:
            return []
        if max_workers == 1:
            cancelled = False
            for index, item in enumerate(items):
                if cancelled or _cancel_requested(cancel_event):
                    cancelled = True
                    results[index] = _cancelled_outcome(item)
                    continue
                result = run(item)
                if _cancel_requested(cancel_event) and result["status"] == "succeeded":
                    cancelled = True
                    result = _cancelled_outcome(item)
                results[index] = result
            return [result for result in results if result is not None]

        pool = ThreadPoolExecutor(max_workers=max_workers)
        futures = {
            pool.submit(run, item): index for index, item in enumerate(items)
        }
        cancelled = False
        try:
            for future in as_completed(futures):
                index = futures[future]
                if cancelled or _cancel_requested(cancel_event):
                    cancelled = True
                    future.cancel()
                    results[index] = _cancelled_outcome(items[index])
                    for pending, pending_index in futures.items():
                        if pending is not future:
                            pending.cancel()
                    break
                result = future.result()
                if _cancel_requested(cancel_event) and result["status"] == "succeeded":
                    cancelled = True
                    result = _cancelled_outcome(items[index])
                results[index] = result
                if cancelled:
                    break
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        for index, result in enumerate(results):
            if result is None:
                results[index] = _cancelled_outcome(items[index]) if cancelled or _cancel_requested(cancel_event) else {
                    "id": items[index].id,
                    "translation": items[index].text,
                    "uncertain_terms": [],
                    "status": "failed",
                    "error": "翻译任务未返回结果",
                    "error_code": "batch_incomplete",
                    "diagnostic": None,
                }
        return [result for result in results if result is not None]

    def translate_stream(
        self,
        items: list[TranslationRequestItem],
        source: str,
        target: str,
        glossary_entries: Optional[list[dict[str, Any]]] = None,
        *,
        cancel_event: Any = None,
    ):
        """Yield validated provider block outcomes for ID-bearing inputs."""
        del glossary_entries
        for item_index, item in enumerate(items):
            if _cancel_requested(cancel_event):
                yield {
                    "type": "block_cancelled",
                    "ids": [remaining.id for remaining in items[item_index:]],
                    "error_code": "cancelled",
                    "error": "翻译已取消",
                    "diagnostic": None,
                    "thinking": "",
                }
                return
            try:
                translation = self.translate(item.text, source, target)
                if not isinstance(translation, str) or (
                    item.text and not translation.strip()
                ):
                    raise ProviderError(
                        "翻译服务返回了空响应", code="empty_response"
                    )
                yield {
                    "type": "block_succeeded",
                    "items": [
                        {
                            "id": item.id,
                            "translation": translation,
                            "uncertain_terms": [],
                        }
                    ],
                    "thinking": "",
                    "diagnostic": None,
                }
            except ProviderError as exc:
                event_type = "block_cancelled" if exc.code == "cancelled" else "block_failed"
                yield {
                    "type": event_type,
                    "ids": [
                        remaining.id for remaining in items[item_index:]
                    ] if event_type == "block_cancelled" else [item.id],
                    "error_code": exc.code,
                    "error": str(exc),
                    "diagnostic": exc.diagnostic,
                    "retryable": exc.retryable,
                    "thinking": "",
                }
                if event_type == "block_cancelled":
                    return
            except Exception as exc:  # noqa: BLE001
                yield {
                    "type": "block_failed",
                    "ids": [item.id],
                    "error_code": "provider_error",
                    "error": f"翻译服务异常（{type(exc).__name__}）",
                    "diagnostic": {"exception_type": type(exc).__name__},
                    "retryable": True,
                    "thinking": "",
                }


class OpenAICompatProvider(Provider):
    """OpenAI 兼容 API Provider。

    Args:
        base_url: API 端点（如 https://api.openai.com/v1 或 https://api.deepseek.com/v1）。
        api_key: API 密钥。
        model: 模型名。
        temperature: 采样温度。
    """

    name = "openai-compat"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.6,
        model_config: Optional[dict] = None,
    ):
        from openai import OpenAI

        self._config = ProviderConfig.from_model_config(
            base_url=base_url,
            model=model,
            temperature=temperature,
            model_config=model_config,
        )
        self.config = self._config
        self._client = OpenAI(base_url=self._config.base_url, api_key=api_key)
        self._model = self._config.model
        self._temperature = self._config.temperature
        self.model_context = self._config.model_context
        self.output_format = self._config.output_format
        self.response_format = self._config.response_format
        # Keep these attributes for integrations that inspect the provider,
        # but derive both sync and stream requests from the same snapshot.
        self._request_params = dict(self._config.request_params)
        self._extra_body = dict(self._config.extra_body)

    def translate(self, text: str, source: str, target: str) -> str:
        block = self.translate_items(
            [TranslationRequestItem(id=0, text=text)],
            source,
            target,
        )
        return block.items[0].translation

    def _response_format(self) -> Optional[dict]:
        """Transport hint; only meaningful for the JSON protocol."""
        if self.output_format != "json" or self.response_format == "none":
            return None
        if self.response_format == "json_schema":
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "translation_result",
                    "schema": TRANSLATION_SCHEMA,
                    "strict": True,
                },
            }
        # auto 与 json_object 都先尝试 json_object，失败时降级为不传。
        return {"type": "json_object"}

    def _create(self, messages: list[dict], *, stream: bool = False):
        """Call Chat Completions using the immutable effective config.

        ``auto`` may retry once without a transport response hint.  Explicit
        ``json_object``/``json_schema`` selections never silently downgrade.
        """
        from openai import BadRequestError

        kwargs: dict = {"model": self._config.model, "messages": messages, "stream": stream}
        if self._config.request_params:
            kwargs.update(copy.deepcopy(dict(self._config.request_params)))
        if self._config.extra_body:
            kwargs["extra_body"] = copy.deepcopy(dict(self._config.extra_body))
        fmt = self._response_format()
        if fmt:
            kwargs["response_format"] = fmt
        try:
            return self._client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            if fmt and self._config.response_format == "auto":
                kwargs.pop("response_format", None)
                try:
                    return self._client.chat.completions.create(**kwargs)
                except BadRequestError as retry_exc:
                    raise ProviderError(
                        "响应格式协商失败",
                        code="response_format_unsupported",
                        diagnostic={
                            "exception_type": type(retry_exc).__name__,
                            "status_code": getattr(retry_exc, "status_code", None),
                        },
                        retryable=False,
                    ) from retry_exc
            if fmt:
                raise ProviderError(
                    "响应格式不被供应商支持",
                    code="response_format_unsupported",
                    diagnostic={
                        "exception_type": type(exc).__name__,
                        "status_code": getattr(exc, "status_code", None),
                    },
                    retryable=False,
                ) from exc
            raise self._provider_error(exc) from exc
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._provider_error(exc) from exc

    def _chat_create(
        self,
        items: list[TranslationRequestItem],
        source: str,
        target: str,
        glossary: str,
        *,
        stream: bool = False,
    ):
        from .translator import build_request_payload, build_system_prompt

        system = build_system_prompt(source, target, glossary, self.output_format)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": build_request_payload(items, self.output_format)},
        ]
        return self._create(messages, stream=stream)

    @staticmethod
    def _provider_error(exc: Exception) -> ProviderError:
        status_code = getattr(exc, "status_code", None)
        diagnostic = {"exception_type": type(exc).__name__}
        if isinstance(status_code, int):
            diagnostic["status_code"] = status_code
        if status_code in {402, 429}:
            code = "usage_limit"
            message = "模型服务额度不足或请求受限"
            retryable = True
        elif status_code in {408, 425, 409} or (
            isinstance(status_code, int) and status_code >= 500
        ):
            code = "provider_unavailable"
            message = "模型服务暂时不可用，请稍后重试"
            retryable = True
        elif status_code in {401, 403}:
            code = "authentication_failed"
            message = "模型服务认证失败，请检查 API Key"
            retryable = False
        elif status_code in {400, 404, 422}:
            code = "provider_request_rejected"
            message = "模型服务拒绝了请求，请检查模型参数"
            retryable = False
        else:
            code = "provider_error"
            message = "OpenAI 兼容 API 调用失败，请稍后重试"
            retryable = True
        return ProviderError(
            message,
            code=code,
            diagnostic=diagnostic,
            retryable=retryable,
        )

    def _chat_with_glossary(
        self,
        items: list[TranslationRequestItem],
        source: str,
        target: str,
        glossary: str = "",
    ) -> ProviderCompletion:
        try:
            response = self._chat_create(items, source, target, glossary)
            if not getattr(response, "choices", None):
                raise ProviderError(
                    "模型响应没有 choices",
                    code="empty_response",
                    diagnostic={"raw_response": response},
                )
            choice = response.choices[0]
            message = choice.message
            return ProviderCompletion(
                content=getattr(message, "content", None) or "",
                finish_reason=getattr(choice, "finish_reason", None),
                refusal=getattr(message, "refusal", None),
                raw_response=response,
            )
        except ProviderError:
            raise
        except Exception as exc:
            raise self._provider_error(exc) from exc

    def translate_items(
        self,
        items: list[TranslationRequestItem],
        source: str,
        target: str,
        *,
        glossary: str = "",
        cancel_event: Any = None,
    ) -> TranslationBlockResult:
        if _cancel_requested(cancel_event):
            raise ProviderError("翻译已取消", code="cancelled", retryable=False)
        completion = self._chat_with_glossary(items, source, target, glossary)
        if _cancel_requested(cancel_event):
            raise ProviderError("翻译已取消", code="cancelled", retryable=False)
        completion.require_complete()
        try:
            parsed = parse_result_by_format(
                completion.content,
                [item.id for item in items],
                self.output_format,
            )
        except OutputContractError as exc:
            raise OutputContractError(
                exc.code,
                str(exc),
                diagnostic={
                    "provider": completion.diagnostic(),
                    "contract": exc.diagnostic,
                },
            ) from exc
        return TranslationBlockResult(
            status="succeeded",
            expected_ids=tuple(item.id for item in items),
            items=parsed,
            diagnostic=completion.diagnostic(),
        )

    def translate_stream(
        self,
        items: list[TranslationRequestItem],
        source: str,
        target: str,
        glossary_entries: Optional[list[dict[str, Any]]] = None,
        *,
        cancel_event: Any = None,
    ):
        """Stream raw deltas, then emit one validated block outcome."""
        from ..glossary import format_glossary_prompt

        glossary = format_glossary_prompt(glossary_entries)
        expected_ids = tuple(item.id for item in items)
        thinking_parts: list[str] = []
        content_parts: list[str] = []
        finish_reason: str | None = None
        refusal_parts: list[Any] = []
        try:
            stream = self._chat_create(
                items,
                source,
                target,
                glossary,
                stream=True,
            )
            for chunk in stream:
                if _cancel_requested(cancel_event):
                    close = getattr(stream, "close", None)
                    if callable(close):
                        close()
                    yield {
                        "type": "block_cancelled",
                        "ids": list(expected_ids),
                        "error_code": "cancelled",
                        "error": "翻译已取消",
                        "diagnostic": None,
                        "thinking": "".join(thinking_parts),
                    }
                    return
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                choice = choices[0]
                if getattr(choice, "finish_reason", None) is not None:
                    finish_reason = choice.finish_reason
                delta = getattr(choice, "delta", None)
                if not delta:
                    continue
                thinking = getattr(delta, "reasoning_content", None)
                if thinking:
                    thinking_parts.append(thinking)
                    yield {"type": "thinking", "delta": thinking}
                refusal = getattr(delta, "refusal", None)
                if refusal not in (None, "", False, []):
                    refusal_parts.append(refusal)
                content = getattr(delta, "content", None)
                if content:
                    content_parts.append(content)
                    yield {"type": "content", "delta": content}
            content = "".join(content_parts)
            if _cancel_requested(cancel_event):
                yield {
                    "type": "block_cancelled",
                    "ids": list(expected_ids),
                    "error_code": "cancelled",
                    "error": "翻译已取消",
                    "diagnostic": None,
                    "thinking": "".join(thinking_parts),
                }
                return
            refusal: Any = refusal_parts or None
            raw_response = {
                "content": content,
                "finish_reason": finish_reason,
                "refusal": refusal,
            }
            completion = ProviderCompletion(
                content=content,
                finish_reason=finish_reason,
                refusal=refusal,
                raw_response=raw_response,
            )
            completion.require_complete()
            try:
                parsed = parse_result_by_format(
                    content,
                    list(expected_ids),
                    self.output_format,
                )
            except OutputContractError as exc:
                raise OutputContractError(
                    exc.code,
                    str(exc),
                    diagnostic={
                        "provider": completion.diagnostic(),
                        "contract": exc.diagnostic,
                    },
                ) from exc
            yield {
                "type": "block_succeeded",
                "items": [item.to_dict() for item in parsed],
                "thinking": "".join(thinking_parts),
                "diagnostic": completion.diagnostic(),
            }
        except OutputContractError as exc:
            yield {
                "type": "block_failed",
                "ids": list(expected_ids),
                "error_code": exc.code,
                "error": str(exc),
                "diagnostic": exc.diagnostic,
                "retryable": exc.retryable,
                "thinking": "".join(thinking_parts),
            }
        except ProviderError as exc:
            event_type = "block_cancelled" if exc.code == "cancelled" else "block_failed"
            yield {
                "type": event_type,
                "ids": list(expected_ids),
                "error_code": exc.code,
                "error": str(exc),
                "diagnostic": exc.diagnostic,
                "retryable": exc.retryable,
                "thinking": "".join(thinking_parts),
            }
        except Exception as exc:
            error = self._provider_error(exc)
            yield {
                "type": "block_failed",
                "ids": list(expected_ids),
                "error_code": error.code,
                "error": str(error),
                "diagnostic": error.diagnostic,
                "retryable": error.retryable,
                "thinking": "".join(thinking_parts),
            }


class MirrorPool:
    """镜像站池：按序尝试，失败自动切换；连续失败进入冷却。

    Args:
        mirrors: 镜像站 base URL 列表（按优先级排序）。
        max_failures: 连续失败多少次后进入冷却。
        cooldown_seconds: 冷却时长。
    """

    def __init__(
        self,
        mirrors: list[str],
        max_failures: int = 3,
        cooldown_seconds: int = 60,
    ):
        if not mirrors:
            raise ValueError("镜像站列表不能为空")
        self.mirrors = list(mirrors)
        self.max_failures = max_failures
        self.cooldown_seconds = cooldown_seconds
        self._fails: dict[str, int] = {}
        self._cooldown_until: dict[str, float] = {}

    def _is_available(self, mirror: str) -> bool:
        return time.time() >= self._cooldown_until.get(mirror, 0.0)

    def _mark_failure(self, mirror: str) -> None:
        self._fails[mirror] = self._fails.get(mirror, 0) + 1
        if self._fails[mirror] >= self.max_failures:
            self._cooldown_until[mirror] = time.time() + self.cooldown_seconds
            self._fails[mirror] = 0

    def _mark_success(self, mirror: str) -> None:
        self._fails[mirror] = 0

    def execute(self, func, *args, **kwargs):
        """尝试各镜像站执行 func，全部失败抛 ProviderError。"""
        errors: list[dict[str, Any]] = []
        # 按优先级 + 冷却状态重排可用镜像
        order = [m for m in self.mirrors if self._is_available(m)]
        if not order:
            raise ProviderError(
                "所有镜像站均在冷却中，稍后再试",
                code="mirrors_cooling",
                diagnostic={"mirror_count": len(self.mirrors)},
            )
        for mirror in order:
            try:
                result = func(mirror, *args, **kwargs)
                self._mark_success(mirror)
                return result
            except ProviderError as e:
                self._mark_failure(mirror)
                errors.append({"mirror": mirror, "code": e.code, "retryable": e.retryable})
            except Exception as e:  # 非 ProviderError 的异常也视为失败
                self._mark_failure(mirror)
                errors.append(
                    {"mirror": mirror, "code": "provider_error", "exception_type": type(e).__name__}
                )
        raise ProviderError(
            "所有镜像站均失败，请稍后重试",
            code="all_mirrors_failed",
            diagnostic={"attempts": errors},
            retryable=any(attempt.get("retryable", True) for attempt in errors),
        )

    def snapshot(self) -> list[dict]:
        """返回各镜像站状态（GUI 展示用）。"""
        return [
            {
                "url": m,
                "available": self._is_available(m),
                "failures": self._fails.get(m, 0),
            }
            for m in self.mirrors
        ]


class GoogleProvider(Provider):
    """Google 翻译 Provider，直接请求镜像站的 /translate_a/single 端点。

    与 Tampermonkey 插件的做法一致（client=gtx&dt=t），
    镜像站代理的就是这个端点。支持失败自动切换与冷却。

    Args:
        mirrors: 镜像站 base URL 列表（按优先级排序）。
        pool: 可选的 MirrorPool 实例（默认自动创建）。
        proxies: 代理设置（requests 透传）。
        timeout: 单次请求超时（秒）。
    """

    name = "google"

    def __init__(
        self,
        mirrors: list[str],
        pool: Optional[MirrorPool] = None,
        proxies: Optional[dict] = None,
        timeout: float = 15.0,
    ):
        self._pool = pool or MirrorPool(mirrors)
        self._proxies = proxies
        self._timeout = timeout

    def _translate_one(self, mirror: str, text: str, source: str, target: str) -> str:
        url = f"{mirror.rstrip('/')}/translate_a/single"
        params = {"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text}
        try:
            r = requests.post(
                url,
                data=params,
                timeout=self._timeout,
                proxies=self._proxies,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code == 429:
                raise ProviderError(
                    "Google 服务请求受限",
                    code="usage_limit",
                    retryable=True,
                    diagnostic={"status_code": 429},
                )
            if r.status_code in {408, 425, 409} or r.status_code >= 500:
                raise ProviderError(
                    "Google 服务暂时不可用",
                    code="provider_unavailable",
                    retryable=True,
                    diagnostic={"status_code": r.status_code},
                )
            if r.status_code in {401, 403}:
                raise ProviderError(
                    "Google 镜像认证失败",
                    code="authentication_failed",
                    retryable=False,
                    diagnostic={"status_code": r.status_code},
                )
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list) or not data or not isinstance(data[0], list):
                raise ProviderError(
                    "Google 返回格式无效",
                    code="invalid_response",
                    retryable=False,
                )
            segments: list[str] = []
            for segment in data[0]:
                if not isinstance(segment, list) or not segment or not isinstance(segment[0], str):
                    raise ProviderError(
                        "Google 返回格式无效",
                        code="invalid_response",
                        retryable=False,
                    )
                segments.append(segment[0])
            result = "".join(segments)
            if text and not result.strip():
                raise ProviderError("Google 返回了空响应", code="empty_response")
            return result
        except ProviderError:
            raise
        except requests.Timeout as exc:
            raise ProviderError(
                "Google 请求超时",
                code="timeout",
                diagnostic={"exception_type": type(exc).__name__},
            ) from exc
        except requests.RequestException as exc:
            raise ProviderError(
                "Google 请求失败",
                code="network_error",
                diagnostic={"exception_type": type(exc).__name__},
            ) from exc
        except (ValueError, TypeError, IndexError) as exc:
            raise ProviderError(
                "Google 返回格式无效",
                code="invalid_response",
                retryable=False,
                diagnostic={"exception_type": type(exc).__name__},
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                "Google 翻译失败",
                code="provider_error",
                diagnostic={"exception_type": type(exc).__name__},
            ) from exc

    def translate(self, text: str, source: str, target: str) -> str:
        return self._pool.execute(self._translate_one, text, source, target)
