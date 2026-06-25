"""命令行入口。

用法：

  # 1) 提取
  python -m xlsx_translate extract -i test/original_file.xlsx \
      -t work/source.txt -j work/map.json

  # 2) 复制 source.txt -> translated.txt 手工翻译 ...

  # 3) 回填
  python -m xlsx_translate apply -i test/original_file.xlsx \
      -j work/map.json -t work/translated.txt \
      --translated work/out_translated.xlsx --bilingual work/out_bilingual.xlsx
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .applier import apply
from .extractor import extract


def _cmd_extract(args: argparse.Namespace) -> int:
    info = extract(args.input, args.txt, args.json)
    print("提取完成：")
    print(f"  源文件:       {args.input}")
    print(f"  工作表:       {', '.join(info['sheets'])}")
    print(f"  非空单元格:   {info['cells_total']}")
    print(f"  可翻译单元格: {info['cells_translatable']}")
    print(f"  去重文本数:   {info['unique_texts']}")
    print(f"  原文 TXT:     {info['txt_path']}")
    print(f"  位置映射 JSON:{info['json_path']}")
    print()
    print("下一步：复制 TXT 为译文文件并翻译，保留每行一条、不要增删行；")
    print("        其中的 \\r \\n 是转义符，译文里若需换行可同样写成 \\n。")
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    info = apply(
        original_xlsx=args.input,
        json_path=args.json,
        translated_txt=args.txt,
        output_translated=args.translated,
        output_bilingual=args.bilingual,
        sep=args.sep,
    )
    print("回填完成：")
    print(f"  原文件:        {args.input}")
    print(f"  译文条数:      {info['unique_texts']}")
    print(f"  填充单元格数:  {info['cells_filled']}")
    print(f"  仅译文版:      {info['translated_output']}")
    if info["bilingual_output"]:
        print(f"  原文-译文对照版:{info['bilingual_output']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xlsx-translate",
        description="XLSX 翻译套件：导出原文 -> 人工翻译 -> 回填译文（保留原样式）。",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pe = sub.add_parser("extract", help="从 xlsx 提取去重原文 txt 与位置映射 json")
    pe.add_argument("-i", "--input", required=True, help="输入 xlsx 路径")
    pe.add_argument("-t", "--txt", required=True, help="输出的原文 txt 路径")
    pe.add_argument("-j", "--json", required=True, help="输出的位置映射 json 路径")
    pe.set_defaults(func=_cmd_extract)

    pa = sub.add_parser("apply", help="用译文 txt 回填 xlsx")
    pa.add_argument("-i", "--input", required=True, help="原始 xlsx 路径（作为样式模板）")
    pa.add_argument("-j", "--json", required=True, help="extract 产出的位置映射 json")
    pa.add_argument("-t", "--txt", required=True, help="已翻译的 txt 路径")
    pa.add_argument("--translated", required=True, help="仅译文版输出 xlsx 路径")
    pa.add_argument("--bilingual", default=None, help="原文-译文对照版输出 xlsx 路径（可选）")
    pa.add_argument(
        "--sep",
        default="\\n",
        help="对照版原文与译文的分隔符（默认换行，使用字面 \\n / \\r / \\t 会还原）",
    )
    pa.set_defaults(func=_cmd_apply)

    return p


def _decode_escapes(s: str) -> str:
    return s.encode("utf-8").decode("unicode_escape") if "\\" in s else s


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # apply 的 sep 支持字面 \n / \r / \t
    if getattr(args, "command", None) == "apply":
        args.sep = _decode_escapes(args.sep)

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
