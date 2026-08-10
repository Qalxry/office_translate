"""AI 翻译模块：Provider 抽象 + OpenAI 兼容 + Google（镜像站自动切换）。"""

from .provider import (
    GoogleProvider,
    MirrorPool,
    OpenAICompatProvider,
    Provider,
    ProviderError,
    TranslationResult,
)

__all__ = [
    "Provider",
    "ProviderError",
    "TranslationResult",
    "OpenAICompatProvider",
    "GoogleProvider",
    "MirrorPool",
]
