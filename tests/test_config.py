"""Task-name and internal-path validation regressions."""

from __future__ import annotations

import pytest
import yaml

from office_translate.config import (
    ConfigError,
    init_job,
    load_config,
    load_job,
)


def test_task_names_accept_user_friendly_names_and_reject_url_breakers(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("work_dir: work\noutput_dir: output\n", encoding="utf-8")
    config = load_config(str(config_path))
    input_path = tmp_path / "source.xlsx"
    input_path.write_bytes(b"placeholder")

    created = init_job(config, "季度 翻译-01", str(input_path))
    assert created["job"] == "季度 翻译-01"

    for bad_name in (
        "a/b",
        "a\\b",
        "a#b",
        "a?b",
        "a%b",
        "..",
        " trailing",
        "trailing ",
        "x" * 81,
    ):
        with pytest.raises(ConfigError):
            init_job(config, bad_name, str(input_path))


def test_job_yaml_cannot_escape_job_directory(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("work_dir: work\noutput_dir: output\n", encoding="utf-8")
    config = load_config(str(config_path))
    input_path = tmp_path / "source.xlsx"
    input_path.write_bytes(b"placeholder")
    created = init_job(config, "safe", str(input_path))
    job_yaml = created["job_yaml"]

    payload = yaml.safe_load(open(job_yaml, encoding="utf-8"))
    payload["input"] = "../source.xlsx"
    with open(job_yaml, "w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle)
    with pytest.raises(ConfigError, match="input"):
        load_job(config, "safe")


def test_config_rejects_escaping_output_dir(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "work_dir: work\noutput_dir: ../outside\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="output_dir"):
        load_config(str(config_path))
