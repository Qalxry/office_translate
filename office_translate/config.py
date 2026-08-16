"""配置加载与任务脚手架（格式无关的核心层）。

约定：
- 根级 config.yaml 存全局默认（work_dir / output_dir / sep），缺省项用内置默认值。
- 每个翻译任务一个文件夹 work/<job>/，init 时复制原始文件进来并生成 job.yaml。
- 相对路径以配置文件所在目录为基准，便于从任意位置运行。
- 所有 sep 值在配置里写「字面转义」（如 '\\n'），加载时统一还原为真实字符。
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .escape import decode_escapes

DEFAULT_CONFIG: dict[str, Any] = {
    "work_dir": "work",
    "output_dir": "output",
    "sep": "\n",
}


class ConfigError(Exception):
    """配置或任务状态不合法。"""


_JOB_NAME_MAX_LENGTH = 80
_SAFE_JOB_NAME_CHARS = frozenset(" _-.")


def _validate_relative_path(
    value: Any,
    label: str,
    *,
    allow_nested: bool,
) -> str:
    """Validate a path stored inside a job directory.

    These are application-internal names, not a general filesystem security
    boundary.  They must be relative, contain no traversal or platform path
    separator, and resolve under the owning job directory.  Absolute config
    directories remain allowed where the public config contract calls for it.
    """
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{label} 必须是非空相对路径")
    if "\x00" in value or os.path.isabs(value) or value.startswith(("/", "\\")):
        raise ConfigError(f"{label} 必须是相对路径: {value!r}")
    if ":" in value:
        raise ConfigError(f"{label} 不能包含驱动器或 URI 分隔符: {value!r}")
    separators = re.split(r"[\\/]", value)
    if not allow_nested and len(separators) != 1:
        raise ConfigError(f"{label} 不能包含路径分隔符: {value!r}")
    if any(part in ("", ".", "..") for part in separators):
        raise ConfigError(f"{label} 含有非法路径片段: {value!r}")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ConfigError(f"{label} 不能包含控制字符: {value!r}")
    return value


def _validate_job_name(job: Any) -> str:
    if not isinstance(job, str) or not job:
        raise ConfigError(f"非法任务名: {job!r}")
    if len(job) > _JOB_NAME_MAX_LENGTH:
        raise ConfigError(f"非法任务名: {job!r}（最多 {_JOB_NAME_MAX_LENGTH} 个字符）")
    if job != job.strip() or job.endswith((".", " ")):
        raise ConfigError(f"非法任务名: {job!r}（不能以空格或句点结尾）")
    if job in (".", ".."):
        raise ConfigError(f"非法任务名: {job!r}")
    if any(
        character not in _SAFE_JOB_NAME_CHARS and not character.isalnum()
        for character in job
    ):
        raise ConfigError(
            f"非法任务名: {job!r}（只允许字母、数字、中文、空格、下划线、短横线和句点）"
        )
    return job


def _validated_output_dir(config: dict[str, Any]) -> str:
    value = config.get("output_dir")
    return _validate_relative_path(value, "output_dir", allow_nested=True)


def load_config(config_path: str = "config.yaml") -> dict[str, Any]:
    """读取配置文件，缺省项用内置默认值；文件不存在时用纯默认值。"""
    data: dict[str, Any] = {}
    if config_path and os.path.isfile(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        if not isinstance(loaded, dict):
            raise ConfigError(f"配置文件 {config_path} 顶层必须是 key: value 映射。")
        data = loaded
    merged = {**DEFAULT_CONFIG, **data}

    base = (
        os.path.dirname(os.path.abspath(config_path))
        if config_path and os.path.isfile(config_path)
        else os.getcwd()
    )
    if not isinstance(merged.get("work_dir"), str) or not merged["work_dir"]:
        raise ConfigError("work_dir 必须是非空路径")
    work_dir = merged["work_dir"]
    if not os.path.isabs(work_dir):
        work_dir = os.path.join(base, work_dir)

    output_dir = _validated_output_dir(merged)

    return {
        "config_path": config_path,
        "work_dir": work_dir,
        "output_dir": output_dir,
        "sep": decode_escapes(str(merged["sep"])),
    }


def job_dir(config: dict[str, Any], job: str) -> str:
    return os.path.join(config["work_dir"], _validate_job_name(job))


def auto_job_name(config: dict[str, Any]) -> str:
    """生成默认任务名：时间戳 YYYYMMDD_HHMMSS，重名时追加 _1/_2。"""
    base = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = base
    i = 1
    while os.path.isdir(job_dir(config, name)):
        name = f"{base}_{i}"
        i += 1
    return name


def init_job(
    config: dict[str, Any],
    job: str | None,
    input_path: str,
    sep: str | None = None,
) -> dict[str, Any]:
    """创建任务：建目录、复制原始文件、写 job.yaml。

- job 为 None 或空时按时间戳自动命名。
- 复制进任务目录时，文件名里的不可断行空格（U+00A0）会替换为普通空格。"""
    job = job or auto_job_name(config)
    _validate_job_name(job)
    if not os.path.isfile(input_path):
        raise ConfigError(f"输入文件不存在: {input_path}")

    jdir = job_dir(config, job)
    if os.path.exists(jdir):
        raise ConfigError(f"任务已存在: {job}（{jdir}）。如需重建请先删除该目录。")
    os.makedirs(jdir)

    try:
        # 不可断行空格（U+00A0）在文件名中极易踩命令行坑，统一替换为普通空格
        filename = os.path.basename(input_path).replace(" ", " ")
        _validate_relative_path(filename, "任务输入文件名", allow_nested=False)
        dest = os.path.join(jdir, filename)
        shutil.copy2(input_path, dest)

        payload: dict[str, Any] = {
            "input": filename,
            "source_path": os.path.abspath(input_path),
        }
        if sep is not None:
            payload["sep"] = sep
        with open(os.path.join(jdir, "job.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)

        return {"job": job, "job_dir": jdir, "input": dest,
                "job_yaml": os.path.join(jdir, "job.yaml")}
    except Exception:
        shutil.rmtree(jdir, ignore_errors=True)  # 半成品清理
        raise


def load_job(config: dict[str, Any], job: str) -> dict[str, Any]:
    """读取任务配置并校验，返回任务信息与各产物路径。"""
    _validate_job_name(job)
    jdir = job_dir(config, job)
    if not os.path.isdir(jdir):
        raise ConfigError(f"任务不存在: {job}（工作区 {config['work_dir']} 下没有该目录）")

    job_yaml = os.path.join(jdir, "job.yaml")
    if not os.path.isfile(job_yaml):
        raise ConfigError(f"任务缺少配置: {job_yaml}，请先运行 init。")
    with open(job_yaml, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"任务配置 {job_yaml} 顶层必须是 key: value 映射。")
    if "input" not in data:
        raise ConfigError(f"任务配置 {job_yaml} 缺少 input 字段。")

    input_name = _validate_relative_path(
        data["input"],
        "任务 input",
        allow_nested=False,
    )
    job_root = Path(jdir).resolve()
    src_path = (job_root / input_name).resolve()
    if src_path.parent != job_root:
        raise ConfigError(f"任务 input 越出任务目录: {input_name!r}")
    src = os.fspath(src_path)
    if not os.path.isfile(src):
        raise ConfigError(f"任务的输入文件缺失: {src}（与 job.yaml 的 input 字段对应）")

    sep = decode_escapes(str(data["sep"])) if "sep" in data else config["sep"]
    output_dir_name = _validated_output_dir(config)
    out_dir = (job_root / output_dir_name).resolve()
    if job_root not in out_dir.parents and out_dir != job_root:
        raise ConfigError(f"output_dir 越出任务目录: {output_dir_name!r}")
    ext = os.path.splitext(src)[1]

    return {
        "job": job,
        "job_dir": jdir,
        "job_yaml": job_yaml,
        "input": src,
        "source_path": data.get("source_path"),
        "sep": sep,
        "source_txt": os.path.join(jdir, "source.txt"),
        "map_json": os.path.join(jdir, "map.json"),
        "translated_txt": os.path.join(jdir, "translated.txt"),
        "manifest_json": os.path.join(jdir, "manifest.json"),
        "output_dir": out_dir,
        "output_translated": os.path.join(out_dir, f"{job}_translated{ext}"),
        "output_bilingual": os.path.join(out_dir, f"{job}_bilingual{ext}"),
    }


def list_jobs(config: dict[str, Any]) -> list[dict[str, Any]]:
    """扫描工作区，返回所有合法任务的 info（load_job 的结果）。"""
    jobs: list[dict[str, Any]] = []
    if not os.path.isdir(config["work_dir"]):
        return jobs
    for name in sorted(os.listdir(config["work_dir"])):
        if not os.path.isdir(os.path.join(config["work_dir"], name)):
            continue
        try:
            jobs.append(load_job(config, name))
        except ConfigError:
            continue  # 跳过不完整或损坏的任务
    return jobs
