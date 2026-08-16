"""Thread-safe, atomic persistence for GUI settings.

The GUI is a single-process application, but FastAPI may execute synchronous
routes in different worker threads.  ``SettingsStore`` therefore owns the
whole read/modify/write transaction and uses a process-local re-entrant lock
per settings file.  Files are committed through a sibling temporary file and
``os.replace`` so readers never observe a partially written JSON document.
"""

from __future__ import annotations

import copy
import json
import math
import os
from collections.abc import Callable, Mapping
from typing import Any

from .storage import LockRegistry, atomic_write_json


class SettingsError(Exception):
    """A settings file could not be read, validated, or committed."""


class SettingsValidationError(SettingsError, ValueError):
    """Settings data is not a JSON object with valid JSON values."""


_SETTINGS_LOCKS = LockRegistry()


def _validate_json_value(value: Any, path: str) -> None:
    """Validate JSON values without silently coercing Python objects."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SettingsValidationError(f"设置字段 {path} 不能包含 NaN 或无穷值。")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise SettingsValidationError(f"设置字段 {path} 的对象键必须是字符串。")
            _validate_json_value(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_json_value(child, f"{path}[{index}]")
        return
    raise SettingsValidationError(
        f"设置字段 {path} 包含不支持的值类型: {type(value).__name__}。"
    )


def _validate_object(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SettingsValidationError(f"{label}顶层必须是 JSON 对象。")
    _validate_json_value(value, label)
    return copy.deepcopy(dict(value))


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Merge objects recursively; arrays and scalar values replace defaults."""
    result = copy.deepcopy(dict(base))
    for key, value in overlay.items():
        if key == "model_configs" and isinstance(result.get(key), Mapping) and isinstance(value, Mapping):
            # The current GUI treats each saved model config as a complete
            # replacement, while provider-level fields still inherit defaults.
            model_configs = copy.deepcopy(dict(result[key]))
            model_configs.update(copy.deepcopy(dict(value)))
            result[key] = model_configs
            continue
        if (
            isinstance(result.get(key), Mapping)
            and isinstance(value, Mapping)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _remove_deleted_models(settings: dict[str, Any]) -> None:
    """Honor the GUI's existing explicit model-removal marker.

    ``removed_models`` is metadata used by the current GUI settings format.
    It is intentionally handled here so loading through ``SettingsStore``
    retains the visible behavior while the server migrates to the store.
    """
    ai = settings.get("ai")
    if not isinstance(ai, dict):
        return
    providers = ai.get("providers")
    if not isinstance(providers, dict):
        return
    for provider in providers.values():
        if not isinstance(provider, dict):
            continue
        removed = provider.get("removed_models")
        model_configs = provider.get("model_configs")
        if not isinstance(removed, list) or not isinstance(model_configs, dict):
            continue
        for model in removed:
            if isinstance(model, str):
                model_configs.pop(model, None)


class SettingsStore:
    """Persist one GUI settings JSON file safely within this process.

    Args:
        path: Settings JSON path.  The parent directory is created on commit.
        defaults: JSON object merged into saved settings on every ``load``.

    ``update`` accepts either a mapping patch or a callable.  A callable is
    passed a private, already-merged dictionary and may mutate it in place or
    return a replacement dictionary.  The callback and the atomic commit run
    under the same per-path lock, preventing lost updates between GUI routes.
    """

    def __init__(self, path: str | os.PathLike[str], defaults: Mapping[str, Any] | None = None):
        try:
            self.path = os.path.abspath(os.fspath(path))
        except TypeError as exc:
            raise SettingsValidationError("设置路径必须是字符串或路径对象。") from exc
        self.defaults = _validate_object(
            {} if defaults is None else defaults,
            label="defaults",
        )

    def _read_saved_unlocked(self) -> dict[str, Any]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(
                    handle,
                    parse_constant=lambda value: (_ for _ in ()).throw(
                        ValueError(f"不允许 JSON 常量 {value}")
                    ),
                )
        except json.JSONDecodeError as exc:
            raise SettingsError(f"设置文件 {self.path} 不是合法 JSON。") from exc
        except (OSError, ValueError) as exc:
            raise SettingsError(f"读取设置文件失败: {self.path}: {exc}") from exc
        return _validate_object(data, label=f"设置文件 {self.path}")

    def _merged_unlocked(self) -> dict[str, Any]:
        saved = self._read_saved_unlocked()
        merged = _deep_merge(self.defaults, saved)
        _remove_deleted_models(merged)
        return _validate_object(merged, label="合并设置")

    def load(self) -> dict[str, Any]:
        """Load, validate, and return a detached defaults-plus-saved snapshot."""
        with _SETTINGS_LOCKS.hold(self.path):
            return self._merged_unlocked()

    def save(self, settings: Mapping[str, Any]) -> None:
        """Atomically replace the saved object after validating it."""
        payload = _validate_object(settings, label="设置")
        with _SETTINGS_LOCKS.hold(self.path):
            try:
                atomic_write_json(self.path, payload)
            except (OSError, TypeError, ValueError) as exc:
                raise SettingsError(f"保存设置失败: {self.path}: {exc}") from exc

    def update(
        self,
        mutator_or_patch: Mapping[str, Any]
        | Callable[[dict[str, Any]], Mapping[str, Any] | None],
    ) -> dict[str, Any]:
        """Apply a patch or callback and atomically commit the result.

        Mapping patches are recursively merged.  Callback exceptions are
        propagated unchanged and leave the previous file untouched.
        """
        with _SETTINGS_LOCKS.hold(self.path):
            current = self._merged_unlocked()
            if isinstance(mutator_or_patch, Mapping):
                candidate = _deep_merge(current, mutator_or_patch)
            elif callable(mutator_or_patch):
                result = mutator_or_patch(current)
                candidate = current if result is None else result
                candidate = _validate_object(candidate, label="更新后的设置")
            else:
                raise SettingsValidationError("update 需要 JSON 对象补丁或可调用修改函数。")

            candidate = _validate_object(candidate, label="更新后的设置")
            try:
                atomic_write_json(self.path, candidate)
            except (OSError, TypeError, ValueError) as exc:
                raise SettingsError(f"保存设置失败: {self.path}: {exc}") from exc
            return copy.deepcopy(candidate)


def load_settings(
    path: str | os.PathLike[str], defaults: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Convenience wrapper for callers that do not need a long-lived store."""
    return SettingsStore(path, defaults).load()


def save_settings(
    path: str | os.PathLike[str], settings: Mapping[str, Any]
) -> None:
    """Convenience wrapper for an atomic full-object save."""
    SettingsStore(path).save(settings)
