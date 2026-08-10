"""格式适配器集合。

导入各格式模块即完成注册（模块内调用 register_adapter）。
新增格式：新建子包并在此处 import。
"""

from . import xlsx  # noqa: F401

__all__ = ["xlsx"]
