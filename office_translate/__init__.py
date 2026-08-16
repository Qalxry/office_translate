"""office_translate 本地 GUI 应用包。

文档提取、翻译和导出均通过 GUI 工作流完成。格式适配器仍作为 GUI
内部实现加载，但不再从顶层包公开 extract/apply Python API。
"""

from __future__ import annotations

# Import format modules so internal adapter registration remains available to
# the GUI's existing format-service code.  The adapters are intentionally not
# re-exported from this package.
from . import formats  # noqa: F401

__version__ = "0.2.0"

__all__ = ["__version__"]
