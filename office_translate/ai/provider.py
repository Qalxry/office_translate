"""翻译 Provider 抽象与实现。

- `Provider`：抽象基类，定义翻译接口（单条 / 批量）。
- `OpenAICompatProvider`：OpenAI 兼容 API（Claude / OpenAI / DeepSeek / Ollama 等）。
- `GoogleProvider`：Google 翻译，支持多个镜像站；
  通过 `MirrorPool` 实现失败自动切换与冷却。
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests


class ProviderError(Exception):
    """翻译请求失败（含所有镜像站失败）。"""


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
        """批量翻译，返回与输入等长的译文列表。

        Args:
            concurrency: 并发线程数（>1 时并发翻译，失败的单条降级为原文）。
        """
        if concurrency <= 1:
            return [self.translate(t, source, target) for t in texts]
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: list[Optional[str]] = [None] * len(texts)
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(self.translate, texts[i], source, target): i for i in range(len(texts))}
            for fut in as_completed(futures):
                i = futures[fut]
                try:
                    results[i] = fut.result()
                except ProviderError:
                    results[i] = texts[i]  # 失败降级为原文
        return [r or "" for r in results]

    def translate_stream(
        self,
        texts: list[str],
        source: str,
        target: str,
        glossary_entries: Optional[list[dict[str, Any]]] = None,
    ) -> "typing.Iterator[dict]":
        """流式批量翻译：逐条 yield {"id", "translation", "uncertain_terms", "thinking"}。

        默认实现：串行逐条调用 translate（无 thinking）。
        OpenAI 兼容 Provider 覆盖此方法以支持思考过程流式输出。
        """
        del glossary_entries
        for i, text in enumerate(texts):
            try:
                yield {"id": i, "translation": self.translate(text, source, target), "uncertain_terms": [], "thinking": None}
            except ProviderError:
                yield {"id": i, "translation": text, "uncertain_terms": [{"term": text[:80], "reason": "翻译失败，保留原文", "candidate": ""}], "thinking": None}


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

        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._temperature = temperature
        # 模型级请求参数（来自 GUI 的 model_configs[model]）：
        # temperature / max_tokens / top_p / thinking / reasoning_effort / top_k / extra…
        # 显式设置的才会传给 API；未设置（None）不传，交给 API 默认。
        # 参数分两类：SDK 标准参数直接传 kwargs；
        # 非标准参数（thinking / top_k / 自定义）走 extra_body，避免 SDK 强类型报错。
        _SDK_STD = {
            "temperature", "max_tokens", "max_completion_tokens", "top_p", "top_logprobs",
            "reasoning_effort", "frequency_penalty", "presence_penalty", "seed", "stop",
            "n", "user", "logit_bias", "logprobs", "prediction", "metadata", "modalities",
            "moderation", "safety_identifier", "service_tier", "store", "stream_options",
            "verbosity", "audio", "web_search_options",
        }
        mc = model_config or {}
        self._request_params: dict = {}   # SDK 标准参数 → create(**kwargs)
        self._extra_body: dict = {}       # 非标准参数 → create(extra_body=...)
        for k, v in mc.items():
            # 下划线前缀是内部字段（如 _effort_options，仅 UI 用），不传给 API
            if v is None or k.startswith("_") or k in ("model_context", "response_format", "extra"):
                continue
            if k in _SDK_STD:
                self._request_params[k] = v
            else:
                self._extra_body[k] = v
        extra = mc.get("extra")
        if isinstance(extra, dict):
            self._extra_body.update({k: v for k, v in extra.items() if v is not None})
        # response_format 显式覆盖（"json_object"/"json_schema"/"none"/dict）：
        # 设置后跳过自动探测降级链，直接使用该模式。
        self._format_override = mc.get("response_format")
        # 输出格式模式：
        # - 思考型模型（deepseek-reasoner / o1 / o3 等）JSON 输出不稳定，直接用 XML 标签；
        # - 其余模型从 strict json_schema 开始，400 时逐级降级
        #   （json_schema → json_object → xml），记住结果避免每次重试。
        m = model.lower()
        if "reasoner" in m or "o1" in m or "o3" in m or "thinking" in m:
            self._format_mode = "xml"
        else:
            self._format_mode = "json_schema"

    def translate(self, text: str, source: str, target: str) -> str:
        content = self._chat_with_glossary(text, source, target, glossary="")
        # XML 兜底模式返回的是带标签文本，需提取译文（行列表 → 字符串）
        if self._format_mode == "xml":
            from .translator import _parse_result

            return "\n".join(_parse_result(content)["translations"])
        return content.strip()

    def _system_prompt(self, source: str, target: str, glossary: str) -> str:
        """按当前输出模式选择 system 模板（JSON 或 XML 兜底）。"""
        from .translator import _SYSTEM_TMPL, _SYSTEM_TMPL_XML

        tmpl = _SYSTEM_TMPL_XML if self._format_mode == "xml" else _SYSTEM_TMPL
        return tmpl.format(source=source, target=target, glossary=glossary)

    def _response_format(self) -> Optional[dict]:
        """构造 response_format：json_schema 优先，逐级降级 json_object / xml（不传）。

        若模型配置显式指定 response_format 覆盖（如 {"type": "json_object"} 或 "none"），
        直接使用覆盖值，跳过自动探测。
        """
        from .translator import TRANSLATION_SCHEMA

        ov = self._format_override
        if ov:
            if ov == "none":
                return None
            if ov == "json_object":
                return {"type": "json_object"}
            if ov == "json_schema":
                return {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "translation_result",
                        "schema": TRANSLATION_SCHEMA,
                        "strict": True,
                    },
                }
            if isinstance(ov, dict):
                return ov
        if self._format_mode == "json_object":
            return {"type": "json_object"}
        if self._format_mode == "json_schema":
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "translation_result",
                    "schema": TRANSLATION_SCHEMA,
                    "strict": True,
                },
            }
        return None

    def _create(self, messages: list[dict], *, stream: bool = False):
        """chat.completions.create：response_format 不支持时逐级降级重试。

        降级链：json_schema → json_object → xml（不传 response_format），
        每档 400 时继续降一档，直到成功或耗尽（deepseek-reasoner 连 json_object 都不支持）。
        模型级请求参数（temperature/max_tokens/top_p/thinking 等）随请求透传。
        """
        from openai import BadRequestError

        order = {"json_schema": "json_object", "json_object": "xml"}
        for _ in range(3):  # 最多 3 次：json_schema / json_object / xml
            kwargs: dict = {"model": self._model, "messages": messages, "stream": stream}
            if self._request_params:
                kwargs.update(self._request_params)
            if self._extra_body:
                kwargs["extra_body"] = self._extra_body
            fmt = self._response_format()
            if fmt:
                kwargs["response_format"] = fmt
            try:
                return self._client.chat.completions.create(**kwargs)
            except BadRequestError:
                if self._format_mode not in order:
                    raise
                self._format_mode = order[self._format_mode]
        raise

    def _chat_create(self, text: str, source: str, target: str, glossary: str, *, stream: bool = False):
        """构建 messages 并调用 _create；若本次触发降级到 xml，改用 XML 模板重发。

        返回：_create 的响应对象（流式时为 stream）。
        """
        mode_before = self._format_mode
        system = self._system_prompt(source, target, glossary)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ]
        resp = self._create(messages, stream=stream)
        if self._format_mode != mode_before and self._format_mode == "xml":
            # 降级发生在请求中途：模型这次收到的是 JSON 模板，重发一次换 XML 模板
            system = self._system_prompt(source, target, glossary)
            messages[0]["content"] = system
            resp = self._create(messages, stream=stream)
        return resp

    def _chat_with_glossary(
        self,
        text: str,
        source: str,
        target: str,
        glossary: str = "",
    ) -> str:
        """带术语库的 chat 调用，返回模型原始输出（JSON 或 XML 标签）。"""
        try:
            resp = self._chat_create(text, source, target, glossary)
            return resp.choices[0].message.content or ""
        except Exception as e:
            raise ProviderError(f"OpenAI 兼容 API 调用失败: {e}") from e

    def translate_stream(
        self,
        texts: list[str],
        source: str,
        target: str,
        glossary_entries: Optional[list[dict[str, Any]]] = None,
    ):
        """流式批量翻译：逐条 yield，含 thinking 思考过程（模型支持时）。"""
        from ..glossary import format_glossary_prompt

        glossary = format_glossary_prompt(glossary_entries)
        for i, text in enumerate(texts):
            thinking_parts: list[str] = []
            content_parts: list[str] = []
            try:
                stream = self._chat_create(text, source, target, glossary, stream=True)
                for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if not delta:
                        continue
                    # 思考过程（DeepSeek 的 reasoning_content / Anthropic 等）
                    thinking = getattr(delta, "reasoning_content", None)
                    if thinking:
                        thinking_parts.append(thinking)
                        # 思考过程也流式 yield，前端实时显示
                        yield {"id": i, "type": "thinking", "delta": thinking}
                    if delta.content:
                        content_parts.append(delta.content)
                        yield {"id": i, "type": "content", "delta": delta.content}
                content = "".join(content_parts)
                # 解析为逐行译文 + 不确定术语
                from .translator import _parse_result

                parsed = _parse_result(content)
                yield {
                    "id": i,
                    "type": "done",
                    "translations": parsed["translations"],
                    "uncertain_terms": parsed["uncertain_terms"],
                    "thinking": "".join(thinking_parts),
                }
            except Exception as e:
                yield {
                    "id": i,
                    "type": "done",
                    "translation": text,
                    "uncertain_terms": [{"term": text[:80], "reason": "翻译失败，保留原文", "candidate": ""}],
                    "thinking": "".join(thinking_parts),
                    "error": str(e),
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
        errors: list[str] = []
        # 按优先级 + 冷却状态重排可用镜像
        order = [m for m in self.mirrors if self._is_available(m)]
        if not order:
            raise ProviderError("所有镜像站均在冷却中，稍后再试")
        for mirror in order:
            try:
                result = func(mirror, *args, **kwargs)
                self._mark_success(mirror)
                return result
            except ProviderError as e:
                self._mark_failure(mirror)
                errors.append(f"{mirror}: {e}")
            except Exception as e:  # 非 ProviderError 的异常也视为失败
                self._mark_failure(mirror)
                errors.append(f"{mirror}: {type(e).__name__}: {e}")
        raise ProviderError("所有镜像站均失败: " + " | ".join(errors))

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
        url = f"{mirror}/translate_a/single"
        params = {"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text}
        try:
            r = requests.get(
                url,
                params=params,
                timeout=self._timeout,
                proxies=self._proxies,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code == 429:
                raise ProviderError("HTTP 429 限流")
            r.raise_for_status()
            data = r.json()
            segments = [seg[0] for seg in data[0]]
            return "".join(segments)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"{type(e).__name__}: {e}") from e

    def translate(self, text: str, source: str, target: str) -> str:
        return self._pool.execute(self._translate_one, text, source, target)

    def translate_stream(
        self,
        texts: list[str],
        source: str,
        target: str,
        glossary_entries: Optional[list[dict[str, Any]]] = None,
    ):
        """流式批量翻译（Google 无思考过程，逐条 yield 结果）。"""
        del glossary_entries
        for i, text in enumerate(texts):
            try:
                translation = self.translate(text, source, target)
                yield {"id": i, "type": "done", "translation": translation, "uncertain_terms": [], "thinking": None}
            except ProviderError:
                yield {
                    "id": i,
                    "type": "done",
                    "translation": text,
                    "uncertain_terms": [{"term": text[:80], "reason": "翻译失败，保留原文", "candidate": ""}],
                    "thinking": None,
                }
