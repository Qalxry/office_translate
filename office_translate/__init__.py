"""office_translate：格式无关的办公文档翻译套件。

工作流程（任务制）：
1) init：把原始文档复制进工作区 work/<job>/，生成任务配置。
2) extract：解析文档，导出「位置映射 JSON」与「去重后的原文 TXT」。
3) 用户手动翻译 TXT。
4) apply：以译文替换文档中的原文，输出「原文-译文对照」「仅译文」两份文件，
          样式与原文件完全一致（基于原文件的物理拷贝）。

顶层 extract() / apply() 按文件扩展名自动分发到对应格式适配器，
当前支持 xlsx；新增格式见 base.py 的 FormatAdapter 与 README「扩展新格式」。
"""

from __future__ import annotations

import os
from typing import Any

from . import formats  # noqa: F401  — 导入各格式模块即完成注册
from .base import FormatAdapter, UnsupportedFormatError, get_adapter, register_adapter

__version__ = "0.2.0"

__all__ = [
    "extract",
    "apply",
    "get_adapter",
    "register_adapter",
    "FormatAdapter",
    "UnsupportedFormatError",
    "__version__",
]


def extract(
    src_path: str | os.PathLike,
    txt_path: str | os.PathLike,
    json_path: str | os.PathLike,
) -> dict[str, Any]:
    """从文档提取可翻译原文（txt）与位置映射（json），按扩展名自动分发。"""
    src = os.fspath(src_path)
    cls = get_adapter(os.path.splitext(src)[1])
    return cls().extract(src, os.fspath(txt_path), os.fspath(json_path))


def apply(
    original: str | os.PathLike,
    json_path: str | os.PathLike,
    translated_txt: str | os.PathLike,
    output_translated: str | os.PathLike,
    output_bilingual: str | os.PathLike | None = None,
    sep: str = "\n",
) -> dict[str, Any]:
    """按位置映射把译文回填进文档，按扩展名自动分发。

    Args:
        original: 原始文档（作为样式模板，不会被修改）。
        json_path: extract 产出的位置映射 JSON。
        translated_txt: 用户翻译后的 txt（行序对应 JSON 的 id）。
        output_translated: 仅译文版输出路径。
        output_bilingual: 原文-译文对照版输出路径；为 None 则不生成。
        sep: 对照版原文与译文之间的分隔符，默认换行。
    """
    src = os.fspath(original)
    cls = get_adapter(os.path.splitext(src)[1])
    return cls().apply(
        original=src,
        json_path=os.fspath(json_path),
        translated_txt=os.fspath(translated_txt),
        output_translated=os.fspath(output_translated),
        output_bilingual=os.fspath(output_bilingual) if output_bilingual else None,
        sep=sep,
    )
