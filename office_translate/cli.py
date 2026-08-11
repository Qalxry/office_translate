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
import json
import os
import sys
from typing import Any, Sequence

from . import config as config_mod
from . import win_convert
from .base import UnsupportedFormatError, get_adapter
from .config import ConfigError, load_config
from .escape import decode_escapes

_PADDING = 20


def _cmd_init(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    job = args.job if args.job else config_mod.auto_job_name(cfg)

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


def _load_ai_settings(config_path: str) -> dict:
    """读取 GUI 设置（gui_settings.json）里的 AI 配置；文件不存在时用默认值。"""
    base = os.path.dirname(os.path.abspath(config_path)) if os.path.isfile(config_path) else os.getcwd()
    path = os.path.join(base, "data", "gui_settings.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("ai"), dict):
                return data["ai"]
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _cmd_auto(args: argparse.Namespace) -> int:
    """一键翻译：extract → AI 翻译 → apply，全部自动完成。"""
    from .ai.provider import GoogleProvider, OpenAICompatProvider, ProviderError
    from .gui.server import DEFAULT_MIRRORS

    cfg = load_config(args.config)
    info = config_mod.load_job(cfg, args.job)

    # 1) extract（若尚未提取）
    if not os.path.isfile(info["source_txt"]):
        adapter = get_adapter(os.path.splitext(info["input"])[1])()
        adapter.extract(info["input"], info["source_txt"], info["map_json"])
        print(f"[1/3] 提取完成: {info['source_txt']}")
    else:
        print(f"[1/3] 已存在提取结果，跳过")

    # 2) AI 翻译
    with open(info["source_txt"], "r", encoding="utf-8", newline="") as f:
        texts = [line.rstrip("\n") for line in f if line.strip()]
    if not texts:
        print("错误: 没有可翻译文本")
        return 1

    ai_cfg = _load_ai_settings(args.config)
    engine = args.engine or ai_cfg.get("engine", "google")
    source = args.source or ai_cfg.get("source_lang", "en")
    target = args.target or ai_cfg.get("target_lang", "zh-CN")

    print(f"[2/3] 开始 AI 翻译（{engine}，{len(texts)} 条，{source}→{target}）...")
    try:
        if engine == "google":
            mirrors = args.mirrors or ai_cfg.get("mirrors") or []
            provider = GoogleProvider(mirrors or DEFAULT_MIRRORS)
            concurrency = ai_cfg.get("concurrency", 4)
            translations = provider.translate_batch(texts, source, target, concurrency=concurrency)
            translations_out = translations
        elif engine == "openai":
            provider_cfg = ai_cfg.get("providers", {}).get(ai_cfg.get("active_provider", "openai"), {})
            provider = OpenAICompatProvider(
                base_url=args.base_url or provider_cfg.get("base_url", "https://api.openai.com/v1"),
                api_key=args.api_key or provider_cfg.get("api_key", ""),
                model=args.model or provider_cfg.get("default_model", "gpt-4o-mini"),
            )
            from .ai.translator import translate_batch as _tb

            results = _tb(texts, provider, source, target)
            translations_out = [r["translation"] for r in results]
        else:
            print(f"错误: 未知引擎 {engine!r}（可选 google / openai）")
            return 1
    except ProviderError as e:
        print(f"错误: 翻译失败: {e}")
        return 1

    # 写回 translated.txt（一行一条，保持行序）
    with open(info["translated_txt"], "w", encoding="utf-8", newline="") as f:
        for t in translations_out:
            f.write(t.rstrip("\n"))
            f.write("\n")
    print(f"[2/3] 翻译完成，已写入 {info['translated_txt']}")

    # 3) apply
    os.makedirs(info["output_dir"], exist_ok=True)
    adapter = get_adapter(os.path.splitext(info["input"])[1])()
    result = adapter.apply(
        original=info["input"],
        json_path=info["map_json"],
        translated_txt=info["translated_txt"],
        output_translated=info["output_translated"],
        output_bilingual=info["output_bilingual"],
        sep=info["sep"],
    )
    print(f"[3/3] 回填完成: {result['translated_output']}")
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

    pauto = sub.add_parser("auto", help="一键翻译：提取 + AI 翻译 + 回填一条命令跑完")
    pauto.add_argument("job", help="任务名")
    pauto.add_argument("--engine", default=None, help="翻译引擎: google / openai（默认读设置）")
    pauto.add_argument("--source", default=None, help="源语言（默认 en）")
    pauto.add_argument("--target", default=None, help="目标语言（默认 zh-CN）")
    pauto.add_argument("--base-url", dest="base_url", default=None, help="OpenAI 兼容端点（覆盖设置）")
    pauto.add_argument("--api-key", dest="api_key", default=None, help="API 密钥（覆盖设置）")
    pauto.add_argument("--model", default=None, help="模型名（覆盖设置）")
    pauto.add_argument("--mirrors", default=None, help="Google 镜像站（逗号分隔，覆盖设置）")
    pauto.set_defaults(func=_cmd_auto)

    pg = sub.add_parser("gui", help="启动图形界面（本地 Web 服务 + 浏览器/WebView）")
    pg.add_argument("--port", type=int, default=None, help="端口（默认自动选）")
    pg.add_argument("--no-webview", action="store_true", help="强制用浏览器而非 pywebview")
    pg.set_defaults(func=_cmd_gui)

    return p


def _cmd_gui(args: argparse.Namespace) -> int:
    from .gui.launcher import launch

    launch(config_path=args.config, port=args.port, use_webview=not args.no_webview)
    return 0


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
