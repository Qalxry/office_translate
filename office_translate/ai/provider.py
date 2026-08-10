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
from typing import Optional

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

    def translate_batch(self, texts: list[str], source: str, target: str) -> list[str]:
        """批量翻译，返回与输入等长的译文列表。"""
        return [self.translate(t, source, target) for t in texts]


class OpenAICompatProvider(Provider):
    """OpenAI 兼容 API Provider。

    Args:
        base_url: API 端点（如 https://api.openai.com/v1 或 https://api.deepseek.com/v1）。
        api_key: API 密钥。
        model: 模型名。
        temperature: 采样温度。
    """

    name = "openai-compat"

    def __init__(self, base_url: str, api_key: str, model: str, temperature: float = 0.6):
        from openai import OpenAI

        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._temperature = temperature

    def translate(self, text: str, source: str, target: str) -> str:
        content = self._chat_with_glossary(text, source, target, glossary="")
        return content.strip()

    def _chat_with_glossary(
        self,
        text: str,
        source: str,
        target: str,
        glossary: str = "",
    ) -> str:
        """带术语库的 chat 调用，返回模型原始输出（含 JSON）。"""
        from ..translator import _SYSTEM_TMPL

        system = _SYSTEM_TMPL.format(source=source, target=target, glossary=glossary)
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                temperature=self._temperature,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            raise ProviderError(f"OpenAI 兼容 API 调用失败: {e}") from e


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
