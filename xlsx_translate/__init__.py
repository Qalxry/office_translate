"""XLSX 翻译套件。

工作流程：
1) extract：解析 xlsx，导出「位置映射 JSON」与「去重后的原文 TXT」。
2) 用户手动翻译 TXT。
3) apply：以译文替换 xlsx 中的原文，输出「原文-译文对照」「仅译文」两份 xlsx，
          样式与原文件完全一致（基于原文件的物理拷贝）。
"""

from .escape import unescape_text, escape_text
from .extractor import extract
from .applier import apply

__all__ = ["escape_text", "unescape_text", "extract", "apply"]
__version__ = "0.1.0"
