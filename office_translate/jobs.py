"""Revision-aware lifecycle service for local GUI jobs."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Iterable

from . import config as config_mod
from .artifacts import (
    ArtifactError,
    JobManifest,
    SourceArtifact,
    TranslationArtifact,
    build_review_items,
    canonical_sha256,
    sha256_file,
)
from .escape import decode_escapes
from .formats.xlsx.applier import apply_artifacts
from .formats.xlsx.extractor import extract_artifact, require_valid_workbook
from .storage import (
    LockRegistry,
    atomic_write_json,
    cleanup_file,
    load_json,
    make_temp_path,
)


class JobError(RuntimeError):
    """A job operation is invalid for the current revision or stage."""


STAGE_LABELS = {
    "created": "待提取",
    "extracted": "已提取",
    "translation_partial": "部分翻译",
    "translated": "已翻译",
    "exported": "已导出",
}


class JobService:
    def __init__(
        self,
        config: dict[str, Any],
        locks: LockRegistry | None = None,
    ) -> None:
        self.config = config
        self.locks = locks or LockRegistry()

    def _info(self, job: str) -> dict[str, Any]:
        try:
            return config_mod.load_job(self.config, job)
        except config_mod.ConfigError as exc:
            raise JobError(str(exc)) from exc

    @staticmethod
    def _manifest_path(info: dict[str, Any]) -> Path:
        return Path(info["job_dir"]) / "manifest.json"

    @staticmethod
    def _safe_job_file(info: dict[str, Any], filename: str) -> Path:
        if not filename or Path(filename).name != filename:
            raise JobError(f"任务 manifest 包含非法文件名: {filename!r}")
        root = Path(info["job_dir"]).resolve()
        path = (root / filename).resolve()
        if path.parent != root:
            raise JobError(f"任务产物越出工作目录: {filename!r}")
        return path

    def _load_manifest(
        self,
        info: dict[str, Any],
        *,
        required: bool = True,
    ) -> JobManifest | None:
        path = self._manifest_path(info)
        if not path.is_file():
            if required:
                raise JobError("这是旧版任务，需要重新提取后才能继续")
            return None
        try:
            manifest = JobManifest.from_dict(load_json(path))
        except (ArtifactError, OSError) as exc:
            raise JobError(f"任务 manifest 损坏: {exc}") from exc
        if manifest.job_id != info["job"]:
            raise JobError("任务 manifest 的 job_id 与目录不一致")
        if manifest.input_filename != Path(info["input"]).name:
            raise JobError("任务 manifest 的输入文件与 job.yaml 不一致")
        return manifest

    def _write_manifest(
        self,
        info: dict[str, Any],
        manifest: JobManifest,
    ) -> None:
        atomic_write_json(self._manifest_path(info), manifest.to_dict())

    def _new_manifest(self, info: dict[str, Any]) -> JobManifest:
        return JobManifest(
            job_id=info["job"],
            input_filename=Path(info["input"]).name,
            input_sha256=sha256_file(info["input"]),
        )

    def _load_source(
        self,
        info: dict[str, Any],
        manifest: JobManifest,
    ) -> SourceArtifact:
        if not manifest.source_artifact or not manifest.source_revision:
            raise JobError("任务尚未提取")
        path = self._safe_job_file(info, manifest.source_artifact)
        if not path.is_file():
            raise JobError("当前原文产物缺失，请重新提取")
        try:
            source = SourceArtifact.from_dict(load_json(path))
        except (ArtifactError, OSError) as exc:
            raise JobError(f"当前原文产物损坏: {exc}") from exc
        if source.source_revision != manifest.source_revision:
            raise JobError("manifest 与原文产物的 source_revision 不一致")
        return source

    def _load_translation(
        self,
        info: dict[str, Any],
        manifest: JobManifest,
        source: SourceArtifact,
    ) -> TranslationArtifact:
        if not manifest.translation_artifact or not manifest.translation_revision:
            raise JobError("任务尚未保存译文")
        path = self._safe_job_file(info, manifest.translation_artifact)
        if not path.is_file():
            raise JobError("当前译文产物缺失，请重新翻译")
        try:
            translation = TranslationArtifact.from_dict(load_json(path), source)
        except (ArtifactError, OSError) as exc:
            raise JobError(f"当前译文产物损坏: {exc}") from exc
        if translation.translation_revision != manifest.translation_revision:
            raise JobError("manifest 与译文产物的 translation_revision 不一致")
        return translation

    def create(
        self,
        job: str | None,
        input_path: str,
        sep: str | None = None,
    ) -> dict[str, Any]:
        lock_key = Path(self.config["work_dir"]) / (job or "__auto_create__")
        with self.locks.hold(lock_key):
            try:
                require_valid_workbook(input_path)
                info = config_mod.init_job(self.config, job, input_path, sep)
            except (config_mod.ConfigError, ArtifactError) as exc:
                raise JobError(str(exc)) from exc
            try:
                self._write_manifest(info, self._new_manifest(info))
                return self.status(info["job"])
            except Exception:
                shutil.rmtree(info["job_dir"], ignore_errors=True)
                raise

    def list(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        for info in config_mod.list_jobs(self.config):
            try:
                jobs.append(self._status_from_info(info))
            except JobError as exc:
                jobs.append(
                    {
                        "job": info["job"],
                        "input": info["input"],
                        "stage": "任务损坏",
                        "stage_code": "error",
                        "stages": [],
                        "needs_reextract": True,
                        "error": str(exc),
                        "source_revision": None,
                        "translation_revision": None,
                        "output_translated": None,
                        "output_bilingual": None,
                    }
                )
        return jobs

    def status(self, job: str) -> dict[str, Any]:
        return self._status_from_info(self._info(job))

    def _status_from_info(self, info: dict[str, Any]) -> dict[str, Any]:
        manifest = self._load_manifest(info, required=False)
        if manifest is None:
            return {
                "job": info["job"],
                "input": info["input"],
                "stage": "需要重新提取",
                "stage_code": "legacy",
                "stages": [],
                "needs_reextract": True,
                "source_revision": None,
                "translation_revision": None,
                "output_translated": None,
                "output_bilingual": None,
            }
        stages: list[str] = []
        if manifest.stage in {
            "extracted",
            "translation_partial",
            "translated",
            "exported",
        }:
            stages.append("已提取")
        if manifest.stage in {"translated", "exported"}:
            stages.append("已翻译")
        if manifest.stage == "translation_partial":
            stages.append("部分翻译")
        if manifest.stage == "exported":
            stages.append("已导出")

        translated_output = self._current_output(info, manifest, "translated")
        bilingual_output = self._current_output(info, manifest, "bilingual")
        return {
            "job": info["job"],
            "input": info["input"],
            "stage": STAGE_LABELS[manifest.stage],
            "stage_code": manifest.stage,
            "stages": stages,
            "needs_reextract": False,
            "source_revision": manifest.source_revision,
            "translation_revision": manifest.translation_revision,
            "output_translated": str(translated_output) if translated_output else None,
            "output_bilingual": str(bilingual_output) if bilingual_output else None,
        }

    def _current_output(
        self,
        info: dict[str, Any],
        manifest: JobManifest,
        kind: str,
    ) -> Path | None:
        if manifest.stage != "exported":
            return None
        filename = manifest.outputs.get(kind)
        if not filename:
            return None
        output_dir = Path(info["output_dir"]).resolve()
        path = (output_dir / filename).resolve()
        if path.parent != output_dir or not path.is_file():
            return None
        return path

    def extract(self, job: str) -> dict[str, Any]:
        info = self._info(job)
        with self.locks.hold(info["job_dir"]):
            try:
                old_manifest = self._load_manifest(info, required=False)
            except JobError:
                old_manifest = None
            manifest = old_manifest or self._new_manifest(info)
            source = extract_artifact(info["input"])
            filename = f"source.{source.source_revision}.json"
            artifact_path = self._safe_job_file(info, filename)
            atomic_write_json(artifact_path, source.to_dict())
            next_manifest = manifest.with_source(source, filename)
            try:
                self._write_manifest(info, next_manifest)
            except Exception:
                if old_manifest is None or old_manifest.source_artifact != filename:
                    cleanup_file(artifact_path)
                raise
            self._cleanup_superseded(info, old_manifest, next_manifest)
            return {
                **source.stats,
                "job": job,
                "source_revision": source.source_revision,
                "items": [item.to_dict() for item in source.items],
            }

    def source(self, job: str) -> dict[str, Any]:
        info = self._info(job)
        with self.locks.hold(info["job_dir"]):
            manifest = self._load_manifest(info)
            source = self._load_source(info, manifest)
            return {
                "source_revision": source.source_revision,
                "items": [item.to_dict() for item in source.items],
                "texts": [item.text for item in source.items],
            }

    def save_translation(
        self,
        job: str,
        *,
        source_revision: str,
        results: Iterable[dict[str, Any]],
        summary: dict[str, Any] | None = None,
        blocks: list[dict[str, Any]] | None = None,
        diagnostics: list[dict[str, Any]] | None = None,
        review_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        info = self._info(job)
        with self.locks.hold(info["job_dir"]):
            manifest = self._load_manifest(info)
            if source_revision != manifest.source_revision:
                raise JobError("source_revision 已变化，请重新载入任务后再保存")
            source = self._load_source(info, manifest)
            raw_results = list(results)
            previous_reviews: list[dict[str, Any]] = []
            if manifest.translation_artifact:
                try:
                    previous = self._load_translation(info, manifest, source)
                    previous_reviews = previous.review_items
                except JobError:
                    # A partial/failed artifact may be replaced by a new result;
                    # its valid review records are not allowed to block recovery.
                    previous_reviews = []
            effective_reviews = (
                review_items
                if review_items is not None
                else build_review_items(
                    source.source_revision,
                    raw_results,
                    previous_reviews,
                )
            )
            try:
                translation = TranslationArtifact.create(
                    source=source,
                    results=raw_results,
                    summary=summary,
                    blocks=blocks,
                    diagnostics=diagnostics,
                    review_items=effective_reviews,
                )
            except ArtifactError as exc:
                raise JobError(str(exc)) from exc
            filename = f"translation.{translation.translation_revision}.json"
            artifact_path = self._safe_job_file(info, filename)
            atomic_write_json(artifact_path, translation.to_dict())
            complete = translation.is_complete_for(source)
            next_manifest = manifest.with_translation(
                translation,
                filename,
                complete=complete,
            )
            try:
                self._write_manifest(info, next_manifest)
            except Exception:
                if manifest.translation_artifact != filename:
                    cleanup_file(artifact_path)
                raise
            self._cleanup_superseded(info, manifest, next_manifest)
            return {
                "ok": True,
                "source_revision": source.source_revision,
                "translation_revision": translation.translation_revision,
                "complete": complete,
                "stage": next_manifest.stage,
            }

    def read_translation(self, job: str) -> dict[str, Any]:
        info = self._info(job)
        with self.locks.hold(info["job_dir"]):
            manifest = self._load_manifest(info)
            source = self._load_source(info, manifest)
            if not manifest.translation_artifact:
                return {
                    "source_revision": source.source_revision,
                    "translation_revision": None,
                    "results": [],
                    "items": [],
                    "blocks": [],
                    "summary": None,
                    "diagnostics": [],
                    "review_items": [],
                    "pending_review_count": 0,
                    "complete": False,
                    "text": "",
                }
            translation = self._load_translation(info, manifest, source)
            results = translation.as_results()
            return {
                "source_revision": source.source_revision,
                "translation_revision": translation.translation_revision,
                "results": results,
                "items": [item.to_dict() for item in translation.items],
                "blocks": translation.blocks,
                "summary": translation.summary,
                "diagnostics": translation.diagnostics,
                "review_items": translation.review_items,
                "pending_review_count": len(translation.pending_review_items()),
                "complete": translation.is_complete_for(source),
                "text": "\n".join(item.translation for item in translation.items),
            }

    @staticmethod
    def _review_public_items(
        translation: TranslationArtifact,
    ) -> list[dict[str, Any]]:
        """Aggregate per-cell review records into the GUI's row-scoped cards."""
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for record in translation.review_items:
            key = (
                record.get("term", ""),
                record.get("reason", ""),
                record.get("candidate", ""),
            )
            groups.setdefault(key, []).append(record)
        public: list[dict[str, Any]] = []
        for (term, reason, candidate), records in groups.items():
            records = sorted(records, key=lambda value: value["item_id"])
            statuses = {record["status"] for record in records}
            status = records[0]["status"] if len(statuses) == 1 else "pending"
            target = next(
                (
                    record["final_target"]
                    for record in records
                    if isinstance(record.get("final_target"), str)
                    and record["final_target"]
                ),
                candidate,
            )
            public.append(
                {
                    "review_id": records[0]["review_id"],
                    "kind": "blank_translation" if not term else "term",
                    "term": term,
                    "reason": reason,
                    "candidate": candidate,
                    "target": target or "",
                    "category": records[0].get("category") or None,
                    "decision": status,
                    "apply_to_text": any(
                        record.get("apply_to_text", False) for record in records
                    ),
                    "selected_row_ids": [
                        record["item_id"]
                        for record in records
                        if record.get("apply_to_text", False)
                    ],
                    "empty_translation_confirmed": all(
                        record.get("empty_translation_confirmed", False)
                        for record in records
                    ),
                    "row_ids": [record["item_id"] for record in records],
                }
            )
        return sorted(
            public,
            key=lambda value: (value["row_ids"][0] if value["row_ids"] else -1, value["review_id"]),
        )

    def read_review(
        self,
        job: str,
        *,
        source_revision: str | None = None,
        translation_revision: str | None = None,
    ) -> dict[str, Any]:
        info = self._info(job)
        with self.locks.hold(info["job_dir"]):
            manifest = self._load_manifest(info)
            source = self._load_source(info, manifest)
            if source_revision is not None and source_revision != source.source_revision:
                raise JobError("source_revision 已变化，请重新载入任务")
            if not manifest.translation_artifact:
                return {
                    "source_revision": source.source_revision,
                    "translation_revision": None,
                    "review_revision": canonical_sha256(
                        {"source_revision": source.source_revision, "items": []}
                    ),
                    "items": [],
                }
            translation = self._load_translation(info, manifest, source)
            if translation_revision is not None and translation_revision != translation.translation_revision:
                raise JobError("translation_revision 已变化，请重新载入译文")
            items = self._review_public_items(translation)
            return {
                "source_revision": source.source_revision,
                "translation_revision": translation.translation_revision,
                "review_revision": canonical_sha256(
                    {
                        "source_revision": source.source_revision,
                        "translation_revision": translation.translation_revision,
                        "items": items,
                    }
                ),
                "items": items,
            }

    def save_review_decisions(
        self,
        job: str,
        *,
        source_revision: str,
        translation_revision: str | None,
        decisions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Validate and atomically save the complete GUI review decision set."""
        if not isinstance(decisions, list):
            raise JobError("decisions 必须是数组")
        info = self._info(job)
        with self.locks.hold(info["job_dir"]):
            manifest = self._load_manifest(info)
            source = self._load_source(info, manifest)
            if source_revision != source.source_revision:
                raise JobError("source_revision 已变化，请重新载入任务")
            translation = self._load_translation(info, manifest, source)
            if translation_revision is not None and translation_revision != translation.translation_revision:
                raise JobError("translation_revision 已变化，请重新载入译文")
            records = [dict(record) for record in translation.review_items]
            public_items = self._review_public_items(translation)
            groups: dict[str, list[dict[str, Any]]] = {}
            for public_item in public_items:
                key = (
                    public_item.get("term", ""),
                    public_item.get("reason", ""),
                    public_item.get("candidate", ""),
                )
                groups[public_item["review_id"]] = [
                    record
                    for record in records
                    if (
                        record.get("term", ""),
                        record.get("reason", ""),
                        record.get("candidate", ""),
                    ) == key
                ]
            if len(decisions) != len(public_items):
                raise JobError("审核 decisions 必须完整覆盖当前审核项")
            seen: set[str] = set()
            for decision in decisions:
                if not isinstance(decision, dict):
                    raise JobError("审核 decision 必须是对象")
                review_id = decision.get("review_id")
                status = decision.get("decision")
                if not isinstance(review_id, str) or review_id in seen or review_id not in groups:
                    raise JobError("审核 review_id 无效、重复或不属于当前译文")
                if status not in {"pending", "accepted", "edited", "ignored"}:
                    raise JobError("审核 decision 非法")
                row_ids = decision.get("row_ids")
                if not isinstance(row_ids, list) or any(
                    not isinstance(item_id, int) or isinstance(item_id, bool)
                    for item_id in row_ids
                ):
                    raise JobError("审核 row_ids 必须是整数数组")
                records_for_id = groups[review_id]
                expected_rows = sorted(record["item_id"] for record in records_for_id)
                if sorted(row_ids) != expected_rows:
                    raise JobError("审核 row_ids 与 review_id 的作用范围不一致")
                target = decision.get("target", "")
                if not isinstance(target, str):
                    raise JobError("审核 target 必须是字符串")
                category = decision.get("category")
                if category is not None and not isinstance(category, str):
                    raise JobError("审核 category 必须是字符串或 null")
                empty_confirmed = decision.get("empty_translation_confirmed", False)
                if not isinstance(empty_confirmed, bool):
                    raise JobError("空译文确认标记非法")
                apply_to_text = decision.get("apply_to_text", False)
                if not isinstance(apply_to_text, bool):
                    raise JobError("apply_to_text 标记非法")
                selected_row_ids = decision.get("selected_row_ids")
                if not isinstance(selected_row_ids, list) or any(
                    not isinstance(item_id, int) or isinstance(item_id, bool)
                    for item_id in selected_row_ids
                ):
                    raise JobError("审核 selected_row_ids 必须是整数数组")
                if len(set(selected_row_ids)) != len(selected_row_ids):
                    raise JobError("审核 selected_row_ids 不能重复")
                selected_rows = set(selected_row_ids)
                if not selected_rows.issubset(expected_rows):
                    raise JobError("审核 selected_row_ids 超出 review_id 的作用范围")
                if not apply_to_text and selected_rows:
                    raise JobError("未启用应用到译文时不能选择作用行")
                is_blank = records_for_id[0].get("term", "") == ""
                if is_blank and status == "accepted" and not empty_confirmed:
                    raise JobError("空译文必须显式确认后才能接受")
                if not is_blank and status in {"accepted", "edited"} and not target.strip():
                    raise JobError("已接受或编辑的术语必须提供最终译法")
                if is_blank and selected_rows:
                    raise JobError("空译文审核不能应用术语替换")
                for record in records_for_id:
                    record["status"] = status
                    record["final_target"] = None if is_blank else (target if status in {"accepted", "edited"} else None)
                    record["category"] = category or ""
                    record["empty_translation_confirmed"] = empty_confirmed
                    record["apply_to_text"] = (
                        apply_to_text and record["item_id"] in selected_rows
                    )
                seen.add(review_id)

            results = translation.as_results()
            result_by_id = {result["id"]: result for result in results}
            # Apply only explicitly confirmed term decisions and only to the
            # rows bound to that review card.  The browser may have previewed
            # the same change already, so replacement is intentionally
            # idempotent; the server remains the export-authorizing source of
            # truth.
            for public_item in public_items:
                key = (
                    public_item.get("term", ""),
                    public_item.get("reason", ""),
                    public_item.get("candidate", ""),
                )
                matching = [
                    record
                    for record in records
                    if (
                        record.get("term", ""),
                        record.get("reason", ""),
                        record.get("candidate", ""),
                    )
                    == key
                ]
                if not matching or not any(record.get("apply_to_text", False) for record in matching):
                    continue
                if matching[0].get("status") not in {"accepted", "edited"}:
                    continue
                target = matching[0].get("final_target") or public_item.get("candidate", "")
                term = public_item.get("term", "")
                candidate = public_item.get("candidate", "")
                if not isinstance(target, str) or not target or not isinstance(term, str):
                    continue
                for record in matching:
                    if not record.get("apply_to_text", False):
                        continue
                    result = result_by_id.get(record["item_id"])
                    if result is None or not isinstance(result.get("translation"), str):
                        continue
                    translated = result["translation"]
                    if candidate and candidate != target:
                        translated = translated.replace(candidate, target)
                    if term and term != target:
                        translated = translated.replace(term, target)
                    result["translation"] = translated
            blank_by_item = {
                record["item_id"]: record.get("empty_translation_confirmed", False)
                for record in records
                if record.get("term", "") == ""
            }
            for result in results:
                if result["id"] in blank_by_item:
                    result["empty_translation_confirmed"] = blank_by_item[result["id"]]
            saved = self.save_translation(
                job,
                source_revision=source_revision,
                results=results,
                summary=translation.summary,
                blocks=translation.blocks,
                diagnostics=translation.diagnostics,
                review_items=records,
            )
            refreshed = self.read_review(
                job,
                source_revision=source_revision,
                translation_revision=saved["translation_revision"],
            )
            return refreshed

    def update_review(
        self,
        job: str,
        *,
        source_revision: str,
        review_id: str | None = None,
        status: str,
        final_target: str | None = None,
        all_pending: bool = False,
    ) -> dict[str, Any]:
        """Atomically persist one review decision or a batch ignore decision."""
        if status not in {"accepted", "edited", "ignored"}:
            raise JobError("审核状态必须是 accepted、edited 或 ignored")
        if status == "edited" and not isinstance(final_target, str):
            raise JobError("编辑审核项必须提供 final_target")
        info = self._info(job)
        with self.locks.hold(info["job_dir"]):
            manifest = self._load_manifest(info)
            if source_revision != manifest.source_revision:
                raise JobError("source_revision 已变化，请重新载入任务")
            source = self._load_source(info, manifest)
            translation = self._load_translation(info, manifest, source)
            records = [dict(item) for item in translation.review_items]
            if all_pending:
                if status != "ignored":
                    raise JobError("批量审核目前只允许全部忽略")
                changed = 0
                for record in records:
                    if record.get("status") == "pending":
                        record["status"] = "ignored"
                        record["final_target"] = None
                        changed += 1
            else:
                if not isinstance(review_id, str) or not review_id:
                    raise JobError("缺少 review_id")
                matching = [record for record in records if record.get("review_id") == review_id]
                if len(matching) != 1:
                    raise JobError("审核项不存在或不属于当前任务")
                record = matching[0]
                record["status"] = status
                if status == "accepted":
                    record["final_target"] = final_target or record["candidate"]
                elif status == "edited":
                    record["final_target"] = final_target
                else:
                    record["final_target"] = None
                changed = 1
            result = self.save_translation(
                job,
                source_revision=source_revision,
                results=translation.as_results(),
                summary=translation.summary,
                blocks=translation.blocks,
                diagnostics=translation.diagnostics,
                review_items=records,
            )
            result["changed"] = changed
            return result

    def apply(
        self,
        job: str,
        *,
        source_revision: str,
        translation_revision: str,
        sep: str | None = None,
        rich_text_policy: str = "flatten",
    ) -> dict[str, Any]:
        info = self._info(job)
        with self.locks.hold(info["job_dir"]):
            manifest = self._load_manifest(info)
            if source_revision != manifest.source_revision:
                raise JobError("source_revision 已变化，请重新载入任务")
            if translation_revision != manifest.translation_revision:
                raise JobError("translation_revision 已变化，请重新载入译文")
            source = self._load_source(info, manifest)
            translation = self._load_translation(info, manifest, source)
            if translation.pending_review_items():
                raise JobError("存在未完成审核项，不能导出")
            if any(
                item.translation == "" and not item.empty_translation_confirmed
                for item in translation.items
            ):
                raise JobError("存在未确认的空译文，不能导出")
            if not translation.is_complete_for(source):
                raise JobError("译文不完整，不能导出")

            output_dir = Path(info["output_dir"])
            output_dir.mkdir(parents=True, exist_ok=True)
            suffix = Path(info["input"]).suffix
            effective_sep = decode_escapes(sep) if sep is not None else info["sep"]
            publication_id = uuid.uuid4().hex
            output_revision = canonical_sha256(
                {
                    "translation_revision": translation.translation_revision,
                    "sep": effective_sep,
                    "publication_id": publication_id,
                }
            )
            revision_tag = output_revision[:12]
            translated_name = f"{job}.{revision_tag}.translated{suffix}"
            bilingual_name = f"{job}.{revision_tag}.bilingual{suffix}"
            translated_final = output_dir / translated_name
            bilingual_final = output_dir / bilingual_name
            translated_temp = make_temp_path(translated_final, suffix=suffix)
            bilingual_temp = make_temp_path(bilingual_final, suffix=suffix)
            try:
                result = apply_artifacts(
                    original_xlsx=info["input"],
                    source=source,
                    translation=translation,
                    output_translated=translated_temp,
                    output_bilingual=bilingual_temp,
                    sep=effective_sep,
                    rich_text_policy=rich_text_policy,
                )
                os.replace(translated_temp, translated_final)
                os.replace(bilingual_temp, bilingual_final)
                next_manifest = manifest.with_outputs(
                    translated=translated_name,
                    bilingual=bilingual_name,
                    output_revision=output_revision,
                )
                self._write_manifest(info, next_manifest)
            except Exception:
                cleanup_file(translated_temp)
                cleanup_file(bilingual_temp)
                cleanup_file(translated_final)
                cleanup_file(bilingual_final)
                raise
            self._cleanup_superseded(info, manifest, next_manifest)
            return {
                **result,
                "translated_output": str(translated_final),
                "bilingual_output": str(bilingual_final),
                "source_revision": source.source_revision,
                "translation_revision": translation.translation_revision,
                "output_revision": output_revision,
            }

    def download(self, job: str, kind: str) -> Path:
        if kind not in {"translated", "bilingual"}:
            raise JobError(f"未知下载类型: {kind!r}")
        info = self._info(job)
        with self.locks.hold(info["job_dir"]):
            manifest = self._load_manifest(info)
            path = self._current_output(info, manifest, kind)
            if path is None:
                raise JobError("当前修订没有可下载的输出文件")
            return path

    def delete(self, job: str) -> bool:
        info = self._info(job)
        with self.locks.hold(info["job_dir"]):
            shutil.rmtree(info["job_dir"])
        return not Path(info["job_dir"]).exists()

    def _cleanup_superseded(
        self,
        info: dict[str, Any],
        old: JobManifest | None,
        new: JobManifest,
    ) -> None:
        old_job_files = (
            {old.source_artifact, old.translation_artifact}
            if old is not None
            else set()
        )
        new_job_files = {new.source_artifact, new.translation_artifact}
        for filename in old_job_files - new_job_files:
            if filename:
                cleanup_file(self._safe_job_file(info, filename))
        active_job_files = {filename for filename in new_job_files if filename}
        job_dir = Path(info["job_dir"])
        for pattern in ("source.*.json", "translation.*.json"):
            for path in job_dir.glob(pattern):
                if path.name not in active_job_files:
                    cleanup_file(path)

        output_dir = Path(info["output_dir"]).resolve()
        old_outputs = set(old.outputs.values()) if old is not None else set()
        for filename in old_outputs - set(new.outputs.values()):
            path = (output_dir / filename).resolve()
            if path.parent == output_dir:
                cleanup_file(path)
        if output_dir.is_dir():
            active_outputs = set(new.outputs.values())
            suffix = Path(info["input"]).suffix
            generated_suffixes = (
                f".translated{suffix}",
                f".bilingual{suffix}",
            )
            prefix = f"{info['job']}."
            for path in output_dir.iterdir():
                if (
                    path.is_file()
                    and path.name.startswith(prefix)
                    and path.name.endswith(generated_suffixes)
                    and path.name not in active_outputs
                ):
                    cleanup_file(path)

        if new.stage == "extracted":
            for legacy in (
                info["source_txt"],
                info["map_json"],
                info["translated_txt"],
                Path(info["job_dir"]) / "ai_output.json",
                info["output_translated"],
                info["output_bilingual"],
            ):
                cleanup_file(legacy)
