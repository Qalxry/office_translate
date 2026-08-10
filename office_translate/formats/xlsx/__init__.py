"""xlsx 格式适配器：extract / apply 实现。"""

from __future__ import annotations

from typing import Any

from ...base import FormatAdapter, register_adapter

from .applier import apply as _apply
from .extractor import extract as _extract


class XlsxAdapter(FormatAdapter):
    format = "xlsx"
    extensions = (".xlsx",)

    def extract(
        self,
        src_path: str,
        txt_path: str,
        json_path: str,
    ) -> dict[str, Any]:
        return _extract(src_path, txt_path, json_path)

    def apply(
        self,
        original: str,
        json_path: str,
        translated_txt: str,
        output_translated: str,
        output_bilingual: str | None,
        sep: str,
    ) -> dict[str, Any]:
        return _apply(
            original_xlsx=original,
            json_path=json_path,
            translated_txt=translated_txt,
            output_translated=output_translated,
            output_bilingual=output_bilingual,
            sep=sep,
        )


register_adapter(XlsxAdapter)

__all__ = ["XlsxAdapter"]
