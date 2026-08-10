"""命令行入口（任务制）。

用法：

  # 1) 建任务：把原始文档复制进工作区，生成任务配置。
  #    job 缺省时按时间戳自动命名（YYYYMMDD_HHMMSS）
  python -m office_translate init <job> -i <原始文档路径> [--sep SEP]
  python -m office_translate init -i <原始文档路径> [--sep SEP]

  # 2) 提取原文（产出 source.txt + map.json）
  python -m office_translate extract <job>

  # 3) 手工翻译：复制 source.txt 为 translated.txt 并逐行翻译 ...

  # 4) 回填译文（产出 output/<job>_translated.xlsx 与 output/<job>_bilingual.xlsx）
  python -m office_translate apply <job> [--sep SEP]

  # 5) 查看工作区任务及进度
  python -m office_translate list
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import Any, Sequence

from . import config as config_mod
from . import win_convert
from .base import UnsupportedFormatError, get_adapter
from .config import ConfigError, load_config
from .escape import decode_escapes

_PADDING = 20


def _auto_job_name(config: dict[str, Any]) -> str:
    """生成默认任务名：时间戳 YYYYMMDD_HHMMSS，重名时追加 _1/_2。"""
    base = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = base
    i = 1
    while os.path.isdir(config_mod.job_dir(config, name)):
        name = f"{base}_{i}"
        i += 1
    return name


def _cmd_init(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    job = args.job if args.job else _auto_job_name(cfg)

    # .xls 输入：自动转换为 .xlsx（Windows + Excel），否则提示手动转换
    ext = os.path.splitext(args.input)[1].lower()
    if ext == ".xls":
        converted = win_convert.maybe_convert(args.input)
        if converted:
            print(f"已将 .xls 自动转换为 .xlsx: {converted}")
            args.input = converted
        else:
            print(win_convert.manual_convert_instructions())
            return 1

    info = config_mod.init_job(cfg, job, args.input, args.sep)
    print(f"任务已创建: {job}")
    print(f"  工作目录:    {info['job_dir']}")
    print(f"  输入文件:    {info['input']}（已从 {args.input} 复制）")
    print(f"  任务配置:    {info['job_yaml']}")
    print()
    print("下一步：运行 extract 提取原文。")
    return 0


def _cmd_extract(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    info = config_mod.load_job(cfg, args.job)
    adapter = get_adapter(os.path.splitext(info["input"])[1])()

    result = adapter.extract(info["input"], info["source_txt"], info["map_json"])

    print(f"提取完成: {args.job}")
    print(f"  源文件:       {info['input']}")
    print(f"  工作表:       {', '.join(result['sheets'])}")
    print(f"  非空单元格:   {result['cells_total']}")
    print(f"  可翻译单元格: {result['cells_translatable']}")
    print(f"  去重文本数:   {result['unique_texts']}")
    print(f"  原文 TXT:     {info['source_txt']}")
    print(f"  位置映射 JSON:{info['map_json']}")
    print()
    print("下一步：复制 source.txt 为 translated.txt 并翻译，保留每行一条、不要增删行；")
    print("        其中的 \\r \\n 是转义符，译文里若需换行可同样写成 \\n。")
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    info = config_mod.load_job(cfg, args.job)
    if not os.path.isfile(info["translated_txt"]):
        raise ConfigError(
            f"译文文件缺失: {info['translated_txt']}。"
            f"请先复制 source.txt 为 translated.txt 并完成翻译。"
        )

    adapter = get_adapter(os.path.splitext(info["input"])[1])()
    sep = decode_escapes(args.sep) if args.sep is not None else info["sep"]
    out_translated = args.translated or info["output_translated"]
    out_bilingual = args.bilingual if args.bilingual is not None else info["output_bilingual"]
    for out in (out_translated, out_bilingual):
        if out:
            os.makedirs(os.path.dirname(out), exist_ok=True)

    result = adapter.apply(
        original=info["input"],
        json_path=info["map_json"],
        translated_txt=info["translated_txt"],
        output_translated=out_translated,
        output_bilingual=out_bilingual,
        sep=sep,
    )

    print(f"回填完成: {args.job}")
    print(f"  原文件:        {info['input']}")
    print(f"  译文条数:      {result['unique_texts']}")
    print(f"  填充单元格数:  {result['cells_filled']}")
    print(f"  仅译文版:      {result['translated_output']}")
    if result["bilingual_output"]:
        print(f"  原文-译文对照版:{result['bilingual_output']}")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    jobs = config_mod.list_jobs(cfg)
    if not jobs:
        print(f"工作区 {cfg['work_dir']} 下暂无任务。运行 init 创建第一个任务。")
        return 0
    print(f"工作区: {cfg['work_dir']}")
    print(f"{'任务名':<{_PADDING}}进度")
    print("-" * (_PADDING + 20))
    for info in jobs:
        steps = []
        if os.path.isfile(info["source_txt"]):
            steps.append("已提取")
        if os.path.isfile(info["translated_txt"]):
            steps.append("已翻译")
        if os.path.isfile(info["output_translated"]):
            steps.append("已回填")
        print(f"{info['job']:<{_PADDING}}{' → '.join(steps) if steps else '待提取'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="office-translate",
        description="办公文档翻译套件：导出原文 -> 人工翻译 -> 回填译文（保留原样式）。"
        "支持 xlsx，架构可扩展 xls / docx。",
    )
    p.add_argument(
        "-c", "--config", default="config.yaml",
        help="配置文件路径（默认 config.yaml；不存在时用内置默认值）",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pi = sub.add_parser("init", help="创建翻译任务：复制原始文件进工作区")
    pi.add_argument(
        "job", nargs="?", default=None,
        help="任务名（工作区下的目录名；缺省按时间戳自动生成）",
    )
    pi.add_argument("-i", "--input", required=True, help="原始文档路径（会被复制进工作区）")
    pi.add_argument(
        "--sep", default=None,
        help="对照版分隔符，字面 \\n \\r \\t \\\\ 会还原（默认用配置文件）",
    )
    pi.set_defaults(func=_cmd_init)

    pe = sub.add_parser("extract", help="从任务输入文件提取去重原文 txt 与位置映射 json")
    pe.add_argument("job", help="任务名")
    pe.set_defaults(func=_cmd_extract)

    pa = sub.add_parser("apply", help="用译文 txt 回填，产出仅译文与对照两份文件")
    pa.add_argument("job", help="任务名")
    pa.add_argument("--translated", default=None, help="仅译文版输出路径（默认 output/<job>_translated.xlsx）")
    pa.add_argument("--bilingual", default=None, help="对照版输出路径（默认 output/<job>_bilingual.xlsx）")
    pa.add_argument(
        "--sep", default=None,
        help="对照版分隔符，字面 \\n \\r \\t \\\\ 会还原（默认用 job.yaml / config.yaml）",
    )
    pa.set_defaults(func=_cmd_apply)

    pl = sub.add_parser("list", help="列出工作区任务及进度")
    pl.set_defaults(func=_cmd_list)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, UnsupportedFormatError, OSError) as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
