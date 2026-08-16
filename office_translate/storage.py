"""Single-process locks and atomic file publication helpers."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator


class StorageError(OSError):
    """A local artifact could not be committed safely."""


class LockRegistry:
    """Create one re-entrant lock per local resource key."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.RLock] = {}

    def get(self, key: str | os.PathLike[str]) -> threading.RLock:
        normalized = os.path.abspath(os.fspath(key))
        with self._guard:
            return self._locks.setdefault(normalized, threading.RLock())

    @contextmanager
    def hold(self, key: str | os.PathLike[str]) -> Iterator[None]:
        lock = self.get(key)
        with lock:
            yield


def make_temp_path(target: str | os.PathLike[str], suffix: str = ".tmp") -> Path:
    """Reserve an empty temporary file beside target and return its path."""
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=suffix,
        dir=path.parent,
    )
    os.close(fd)
    return Path(temp_name)


def cleanup_file(path: str | os.PathLike[str] | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def atomic_write(
    target: str | os.PathLike[str],
    writer: Callable[[Path], None],
) -> None:
    """Write through a sibling temporary file, then replace target."""
    path = Path(target)
    temp = make_temp_path(path)
    try:
        writer(temp)
        with temp.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except Exception:
        cleanup_file(temp)
        raise


def atomic_write_json(target: str | os.PathLike[str], value: Any) -> None:
    def write(temp: Path) -> None:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                value,
                handle,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
            )
            handle.write("\n")

    atomic_write(target, write)


def atomic_write_text(
    target: str | os.PathLike[str],
    text: str,
    *,
    newline: str = "",
) -> None:
    def write(temp: Path) -> None:
        with temp.open("w", encoding="utf-8", newline=newline) as handle:
            handle.write(text)

    atomic_write(target, write)


def load_json(path: str | os.PathLike[str]) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"无法读取 JSON 文件 {path}: {exc}") from exc
