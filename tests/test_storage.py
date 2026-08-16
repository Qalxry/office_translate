"""Atomic storage and per-resource locking tests."""

from __future__ import annotations

import json
import threading

import pytest

from office_translate.storage import (
    LockRegistry,
    atomic_write,
    atomic_write_json,
)


def test_atomic_json_roundtrip_preserves_backslashes_and_line_endings(tmp_path):
    path = tmp_path / "artifact.json"
    payload = {
        "values": [
            r"C:\new\report",
            r"literal\n",
            "LF\nCR\rCRLF\r\ntrail\\",
        ]
    }

    atomic_write_json(path, payload)

    assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_atomic_write_failure_keeps_previous_file_and_removes_temp(tmp_path):
    target = tmp_path / "manifest.json"
    target.write_text("old", encoding="utf-8")

    def fail_after_partial_write(temp):
        temp.write_text("partial", encoding="utf-8")
        raise OSError("simulated write failure")

    with pytest.raises(OSError, match="simulated"):
        atomic_write(target, fail_after_partial_write)

    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob(".manifest.json.*")) == []


def test_atomic_json_rejects_nan_without_replacing_previous_file(tmp_path):
    target = tmp_path / "artifact.json"
    target.write_text('{"status": "old"}', encoding="utf-8")

    with pytest.raises(ValueError, match="JSON"):
        atomic_write_json(target, {"value": float("nan")})

    assert json.loads(target.read_text(encoding="utf-8")) == {"status": "old"}
    assert list(tmp_path.glob(".artifact.json.*")) == []


def test_lock_registry_serializes_the_same_resource(tmp_path):
    registry = LockRegistry()
    resource = tmp_path / "job"
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()

    def first_worker():
        with registry.hold(resource):
            first_entered.set()
            assert release_first.wait(timeout=1)

    def second_worker():
        assert first_entered.wait(timeout=1)
        with registry.hold(resource):
            second_entered.set()

    first = threading.Thread(target=first_worker)
    second = threading.Thread(target=second_worker)
    first.start()
    second.start()
    assert first_entered.wait(timeout=1)
    assert not second_entered.wait(timeout=0.05)
    release_first.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert not first.is_alive()
    assert not second.is_alive()
    assert second_entered.is_set()
