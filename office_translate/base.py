"""格式适配器基类与注册表（格式无关的核心层）。

每种文档格式（xlsx / xls / docx ...）实现一个 FormatAdapter 子类，
并在模块内用 `register_adapter` 装饰器注册。核心层与 CLI 只认识
FormatAdapter 接口，不认识任何具体格式。

扩展新格式：

    # office_translate/formats/docx/__init__.py
    from office_translate.base import FormatAdapter, register_adapter

    class DocxAdapter(FormatAdapter):
        format = "docx"
        extensions = (".docx",)

        def extract(self, src_path, txt_path, json_path): ...
        def apply(self, original, json_path, translated_txt,
                  output_translated, output_bilingual, sep): ...

    register_adapter(DocxAdapter)

    # office_translate/formats/__init__.py 中导入该模块即可自动完成注册。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class FormatAdapter(ABC):
    """一种文档格式的翻译适配器：提取原文、回填译文。

    约定与 xlsx 适配器一致：
    - extract：src 中「可翻译的文本」去重后逐行写入 txt（CR/LF 转义），
      同时把位置映射写入 json（list[{"id", "text", "cells"}]）。
    - apply：以 original 为模板（物理拷贝），把译文写回对应位置，
      输出「仅译文」与「原文-译文对照」两份文件，保留全部样式。
    """

    format: str
    extensions: tuple[str, ...]

    @abstractmethod
    def extract(
        self,
        src_path: str,
        txt_path: str,
        json_path: str,
    ) -> dict[str, Any]:
        """提取原文 txt 与位置映射 json，返回统计信息 dict。"""

    @abstractmethod
    def apply(
        self,
        original: str,
        json_path: str,
        translated_txt: str,
        output_translated: str,
        output_bilingual: str | None,
        sep: str,
    ) -> dict[str, Any]:
        """回填译文，返回统计信息 dict。"""


class UnsupportedFormatError(ValueError):
    """未注册的文档格式。"""


_REGISTRY: dict[str, type[FormatAdapter]] = {}


def register_adapter(cls: type[FormatAdapter]) -> type[FormatAdapter]:
    """类装饰器：按 extensions 注册适配器。

    后注册的同扩展名会覆盖先注册的，便于测试注入或替换实现。
    """
    for ext in cls.extensions:
        _REGISTRY[ext.lower()] = cls
    return cls


def get_adapter(ext: str) -> type[FormatAdapter]:
    """按扩展名（如 ".xlsx"）取适配器类，未支持时抛 UnsupportedFormatError。"""
    ext = ext.lower()
    try:
        return _REGISTRY[ext]
    except KeyError:
        supported = ", ".join(sorted({e for es in _REGISTRY for e in es}))
        raise UnsupportedFormatError(
            f"暂不支持 {ext!r} 格式，当前支持: {supported}"
        ) from None
