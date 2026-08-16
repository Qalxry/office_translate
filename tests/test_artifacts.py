"""Validation tests for revision-bound job artifacts."""

from __future__ import annotations

import copy

import pytest

from office_translate.artifacts import (
    ArtifactError,
    CellRef,
    JobManifest,
    SourceArtifact,
    SourceItem,
    TranslationArtifact,
)


def _source(*texts: str) -> SourceArtifact:
    return SourceArtifact.create(
        input_sha256="a" * 64,
        items=[
            SourceItem(
                id=item_id,
                text=text,
                cells=(CellRef("Sheet1", f"A{item_id + 1}"),),
            )
            for item_id, text in enumerate(texts)
        ],
    )


def test_source_revision_is_stable_and_content_bound():
    first = _source("Hello", "World")
    same = SourceArtifact.from_dict(first.to_dict())
    changed = _source("Hello", "Changed")

    assert same == first
    assert same.source_revision == first.source_revision
    assert changed.source_revision != first.source_revision


def test_source_artifact_rejects_revision_tampering():
    source = _source("Hello")
    payload = copy.deepcopy(source.to_dict())
    payload["items"][0]["text"] = "Changed"

    with pytest.raises(ArtifactError, match="source_revision"):
        SourceArtifact.from_dict(payload)


def test_translation_revision_preserves_structured_text_and_validates_ids():
    source = _source("one", "two")
    values = [r"C:\new\report", "LF\nCR\rCRLF\r\ntrail\\"]
    translation = TranslationArtifact.create(
        source,
        [
            {"id": item_id, "translation": value}
            for item_id, value in enumerate(values)
        ],
    )

    restored = TranslationArtifact.from_dict(translation.to_dict(), source)
    assert [item.translation for item in restored.items] == values
    assert restored.is_complete_for(source)

    with pytest.raises(ArtifactError, match="重复"):
        TranslationArtifact.create(
            source,
            [
                {"id": 0, "translation": "first"},
                {"id": 0, "translation": "duplicate"},
            ],
        )

    tampered = copy.deepcopy(translation.to_dict())
    tampered["items"][0]["source"] = "not the current source"
    with pytest.raises(ArtifactError, match="source"):
        TranslationArtifact.from_dict(tampered, source)


def test_translation_summary_is_revision_bound_and_gates_completion():
    source = _source("one", "two")
    summary = {
        "status": "partial",
        "total": 2,
        "succeeded": 1,
        "failed": 1,
        "cancelled": 0,
        "succeeded_ids": [0],
        "failed_ids": [1],
        "cancelled_ids": [],
    }
    translation = TranslationArtifact.create(
        source,
        [
            {"id": 0, "translation": "一", "status": "succeeded"},
            {
                "id": 1,
                "translation": "two",
                "status": "failed",
                "error": "truncated",
            },
        ],
        summary=summary,
        diagnostics=[{"finish_reason": "length"}],
    )
    assert translation.summary == summary
    assert translation.diagnostics == [{"finish_reason": "length"}]
    assert not translation.is_complete_for(source)

    tampered = copy.deepcopy(translation.to_dict())
    tampered["summary"]["status"] = "succeeded"
    with pytest.raises(ArtifactError, match="summary"):
        TranslationArtifact.from_dict(tampered, source)


def test_job_manifest_requires_artifacts_for_each_declared_stage():
    created = JobManifest(
        job_id="job",
        input_filename="input.xlsx",
        input_sha256="b" * 64,
    )
    assert JobManifest.from_dict(created.to_dict()) == created

    broken = created.to_dict()
    broken["stage"] = "exported"
    with pytest.raises(ArtifactError, match="原文修订"):
        JobManifest.from_dict(broken)

    broken = created.to_dict()
    broken["input_sha256"] = "not-a-digest"
    with pytest.raises(ArtifactError, match="SHA-256"):
        JobManifest.from_dict(broken)


def test_v1_artifacts_are_rejected_without_compatibility_path():
    source = _source("Hello")
    old_source = source.to_dict()
    old_source["schema_version"] = 1
    with pytest.raises(ArtifactError, match="不支持"):
        SourceArtifact.from_dict(old_source)

    translation = TranslationArtifact.create(
        source,
        [{"id": 0, "translation": "你好"}],
    )
    old_translation = translation.to_dict()
    old_translation["schema_version"] = 1
    with pytest.raises(ArtifactError, match="不支持"):
        TranslationArtifact.from_dict(old_translation, source)
