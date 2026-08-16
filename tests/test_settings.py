"""Thread-safe and atomic GUI settings persistence tests."""

from __future__ import annotations

import json
import threading

import pytest

from office_translate.settings import (
    SettingsError,
    SettingsStore,
    SettingsValidationError,
)


DEFAULTS = {
    "ai": {
        "engine": "google",
        "providers": {
            "google": {
                "models": ["default"],
                "model_configs": {
                    "default": {"temperature": 0.6},
                    "custom": {"temperature": 0.6, "max_tokens": 8192},
                },
            }
        },
    },
    "ui": {"theme": "system"},
}


def test_missing_settings_are_merged_and_detached(tmp_path):
    store = SettingsStore(tmp_path / "settings.json", DEFAULTS)

    first = store.load()
    first["ai"]["providers"]["google"]["models"].append("local")

    assert store.load() == DEFAULTS


def test_saved_settings_are_merged_and_removed_models_are_honored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "ai": {
                    "engine": "openai",
                    "providers": {
                        "google": {
                            "removed_models": ["default"],
                            "model_configs": {"custom": {"temperature": 0.2}},
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    loaded = SettingsStore(path, DEFAULTS).load()
    assert loaded["ai"]["engine"] == "openai"
    assert loaded["ai"]["providers"]["google"]["models"] == ["default"]
    assert "default" not in loaded["ai"]["providers"]["google"]["model_configs"]
    assert loaded["ai"]["providers"]["google"]["model_configs"]["custom"] == {
        "temperature": 0.2
    }


def test_malformed_or_non_object_settings_raise_explicitly(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(SettingsError, match="合法 JSON"):
        SettingsStore(path, DEFAULTS).load()

    path.write_text("[]", encoding="utf-8")
    with pytest.raises(SettingsValidationError, match="顶层"):
        SettingsStore(path, DEFAULTS).load()


def test_update_accepts_patch_and_callable(tmp_path):
    store = SettingsStore(tmp_path / "settings.json", DEFAULTS)

    updated = store.update({"ui": {"theme": "dark"}})
    assert updated["ui"]["theme"] == "dark"
    assert updated["ai"]["engine"] == "google"

    updated = store.update(lambda data: data["ui"].update({"scale": 1.25}))
    assert updated["ui"] == {"theme": "dark", "scale": 1.25}
    assert store.load()["ui"] == {"theme": "dark", "scale": 1.25}


def test_concurrent_updates_do_not_lose_changes(tmp_path):
    store = SettingsStore(tmp_path / "settings.json", {"count": 0})
    workers = 8
    increments = 30
    errors = []

    def worker():
        try:
            for _ in range(increments):
                store.update(lambda data: data.update(count=data["count"] + 1))
        except BaseException as exc:  # report failures after all threads join
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    assert store.load()["count"] == workers * increments


def test_atomic_save_failure_keeps_previous_file_and_cleans_temp(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    store = SettingsStore(path, {"value": "old"})
    store.save({"value": "old"})

    import office_translate.storage as storage

    real_replace = storage.os.replace

    def fail_replace(source, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(storage.os, "replace", fail_replace)
    with pytest.raises(SettingsError, match="保存设置失败"):
        store.save({"value": "new"})
    monkeypatch.setattr(storage.os, "replace", real_replace)

    assert store.load() == {"value": "old"}
    assert list(tmp_path.glob(".settings.json.*")) == []


def test_invalid_update_is_rejected_without_writing(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path, {"value": "old"})
    store.save({"value": "old"})

    with pytest.raises(SettingsValidationError, match="NaN"):
        store.update({"value": float("nan")})

    assert store.load() == {"value": "old"}
