"""Strict ID-bearing translation orchestration."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from .contracts import (
    OutputContractError,
    TranslationRequestItem,
    escape_text_line,
    parse_result_by_format,
)
from .provider import OpenAICompatProvider, Provider, ProviderError, _cancel_requested


_SYSTEM_TMPL_JSON = (
    "You are a professional translation engine. Translate every input item "
    "from {source} to {target}.\n"
    "{glossary}\n"
    "The user input is one JSON object shaped exactly as:\n"
    '{{"source_items":[{{"id":0,"source_text":"text to translate"}}]}}\n'
    "Return exactly one JSON object shaped exactly as:\n"
    '{{"items":[{{"id":0,"translation":"translated text",'
    '"uncertain_terms":[{{"term":"...","reason":"...","candidate":"..."}}]}}]}}\n'
    "Rules:\n"
    "- The only root key is items. Every output item has exactly id, translation, "
    "and uncertain_terms.\n"
    "- Always use the output key translation. Never output text, source, or source_text.\n"
    "- Return exactly one output item for every input ID, with the same ID.\n"
    "- Never add, remove, duplicate, merge, split, or renumber items.\n"
    "- translation is the translated text for that ID and may contain real line breaks.\n"
    "- uncertain_terms belongs to that item. Use [] when fully confident.\n"
    "- Preserve the structure and formatting inside each item.\n"
    "- Do not use Markdown fences, XML, commentary, or text outside the JSON object."
)


_SYSTEM_TMPL_XML = (
    "You are a professional translation engine. Translate every input item "
    "from {source} to {target}.\n"
    "{glossary}\n"
    "Rules:\n"
    "- Return exactly one XML document matching this structure:\n"
    "  <items><item id=\"0\"><translation>...</translation>"
    "<uncertain_terms><term term=\"...\" reason=\"...\" candidate=\"...\"/>"
    "</uncertain_terms></item></items>\n"
    "- Return exactly one <item> for every input ID, with the same id attribute.\n"
    "- Never add, remove, duplicate, merge, split, or renumber items.\n"
    "- translation is the translated text for that ID and may contain real line breaks.\n"
    "- uncertain_terms belongs to that item. Use <uncertain_terms/> when fully confident.\n"
    "- Escape XML special characters inside text and attribute values.\n"
    "- Do not use Markdown fences, JSON, commentary, or text outside the XML document."
)


_SYSTEM_TMPL_TEXT = (
    "You are a professional translation engine. Translate every input item "
    "from {source} to {target}.\n"
    "{glossary}\n"
    "Rules:\n"
    "- Return plain text only, with exactly one output line per input item, in input order.\n"
    "- Never include IDs, numbers, JSON, XML, Markdown, bullet points, prefixes, or commentary.\n"
    "- Inside a line, escape every non-space whitespace and every backslash with literal "
    "sequences: \\n for newline, \\t for tab, \\r for carriage return, \\\\ for backslash.\n"
    "- The number of lines must exactly match the number of input items; "
    "do not add, remove, or merge empty lines.\n"
    "- Do not end the output with an extra newline beyond the line separator."
)


def build_system_prompt(
    source: str,
    target: str,
    glossary: str,
    output_format: str = "xml",
) -> str:
    templates = {
        "json": _SYSTEM_TMPL_JSON,
        "xml": _SYSTEM_TMPL_XML,
        "text": _SYSTEM_TMPL_TEXT,
    }
    template = templates.get(output_format)
    if template is None:
        raise OutputContractError("invalid_request", f"未知输出格式: {output_format!r}")
    return template.format(source=source, target=target, glossary=glossary)


def build_request_payload(
    items: list[TranslationRequestItem],
    output_format: str = "xml",
) -> str:
    """Serialize source items using the selected strict protocol."""
    if output_format == "json":
        return json.dumps(
            {
                "source_items": [
                    {"id": item.id, "source_text": item.text}
                    for item in items
                ]
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    if output_format == "xml":
        from xml.sax.saxutils import escape as _xml_escape

        parts = ["<items>"]
        for item in items:
            parts.append(
                f'<item id="{item.id}"><text>{_xml_escape(item.text)}</text></item>'
            )
        parts.append("</items>")
        return "".join(parts)
    if output_format == "text":
        return "\n".join(escape_text_line(item.text) for item in items)
    raise OutputContractError("invalid_request", f"未知输出格式: {output_format!r}")


def _parse_result(
    content: str,
    expected_ids: list[int],
    output_format: str = "xml",
) -> dict[str, Any]:
    """Parse and repackage model output for the selected strict protocol."""
    items = parse_result_by_format(content, expected_ids, output_format)
    return {"items": [item.to_dict() for item in items]}


def _failed_result(
    item: TranslationRequestItem,
    *,
    code: str,
    message: str,
    diagnostic: Any = None,
) -> dict[str, Any]:
    return {
        "id": item.id,
        "translation": item.text,
        "uncertain_terms": [],
        "status": "failed",
        "error": message,
        "error_code": code,
        "diagnostic": diagnostic,
    }


def _cancelled_result(item: TranslationRequestItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "translation": item.text,
        "uncertain_terms": [],
        "status": "cancelled",
        "error": "翻译已取消",
        "error_code": "cancelled",
        "diagnostic": None,
    }


def _translate_generic_batch(
    requests: list[TranslationRequestItem],
    provider: Provider,
    source: str,
    target: str,
    *,
    concurrency: int,
    cancel_event: Any,
) -> list[dict[str, Any]]:
    """Use the provider's explicit outcome API, with a safe duck-typed fallback."""
    outcome_method = getattr(provider, "translate_batch_outcomes", None)
    if callable(outcome_method):
        return outcome_method(
            [item.text for item in requests],
            source,
            target,
            concurrency=concurrency,
            cancel_event=cancel_event,
        )

    # A small compatibility path for test/dummy providers that implement only
    # the original one-item method.  It still never treats source text as a
    # success and folds results into deterministic input order.
    results: list[dict[str, Any] | None] = [None] * len(requests)

    def run(item: TranslationRequestItem) -> dict[str, Any]:
        try:
            if _cancel_requested(cancel_event):
                return _cancelled_result(item)
            translation = provider.translate(item.text, source, target)
            if not isinstance(translation, str) or (item.text and not translation.strip()):
                raise ProviderError("翻译服务返回了空响应", code="empty_response")
            return {
                "id": item.id,
                "translation": translation,
                "uncertain_terms": [],
                "status": "succeeded",
                "error": None,
            }
        except ProviderError as exc:
            if exc.code == "cancelled":
                return _cancelled_result(item)
            return _failed_result(item, code=exc.code, message=str(exc), diagnostic=exc.diagnostic)
        except Exception as exc:  # noqa: BLE001
            return _failed_result(
                item,
                code="provider_error",
                message=f"翻译服务异常（{type(exc).__name__}）",
                diagnostic={"exception_type": type(exc).__name__},
            )

    max_workers = max(1, int(concurrency))
    if max_workers == 1:
        cancelled = False
        for index, item in enumerate(requests):
            if cancelled or _cancel_requested(cancel_event):
                cancelled = True
                results[index] = _cancelled_result(item)
                continue
            result = run(item)
            if _cancel_requested(cancel_event) and result["status"] == "succeeded":
                cancelled = True
                result = _cancelled_result(item)
            results[index] = result
    else:
        pool = ThreadPoolExecutor(max_workers=max_workers)
        futures = {pool.submit(run, item): index for index, item in enumerate(requests)}
        cancelled = False
        try:
            for future in as_completed(futures):
                index = futures[future]
                if cancelled or _cancel_requested(cancel_event):
                    cancelled = True
                    future.cancel()
                    results[index] = _cancelled_result(requests[index])
                    for pending in futures:
                        if pending is not future:
                            pending.cancel()
                    break
                result = future.result()
                if _cancel_requested(cancel_event) and result["status"] == "succeeded":
                    cancelled = True
                    result = _cancelled_result(requests[index])
                results[index] = result
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        for index, result in enumerate(results):
            if result is None:
                results[index] = _cancelled_result(requests[index]) if cancelled or _cancel_requested(cancel_event) else _failed_result(
                    requests[index],
                    code="batch_incomplete",
                    message="翻译任务未返回结果",
                )
    return [result for result in results if result is not None]


def translate_batch(
    texts: list[str],
    provider: Provider,
    source: str = "en",
    target: str = "zh-CN",
    glossary_entries: Optional[list[dict[str, Any]]] = None,
    *,
    concurrency: int = 1,
    cancel_event: Any = None,
) -> list[dict[str, Any]]:
    """Translate a batch while preserving a complete per-ID outcome set."""
    from ..glossary import format_glossary_prompt

    requests = [
        TranslationRequestItem(id=item_id, text=text)
        for item_id, text in enumerate(texts)
    ]
    if isinstance(provider, OpenAICompatProvider):
        return _translate_openai_batch_chunked(
            requests,
            provider,
            source,
            target,
            glossary_entries,
            concurrency=concurrency,
            cancel_event=cancel_event,
        )
    return _translate_generic_batch(
        requests,
        provider,
        source,
        target,
        concurrency=concurrency,
        cancel_event=cancel_event,
    )


def _translate_openai_batch_chunked(
    requests: list[TranslationRequestItem],
    provider: OpenAICompatProvider,
    source: str,
    target: str,
    glossary_entries: Optional[list[dict[str, Any]]],
    *,
    concurrency: int,
    cancel_event: Any,
) -> list[dict[str, Any]]:
    """Translate OpenAI-compatible requests without losing long-item metadata.

    The provider receives generated segment IDs only inside this function.  The
    returned outcome set is always rebuilt against the original request IDs,
    so retries and the GUI never expose a segment as if it were a source row.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .chunking import chunk_request_items, reassemble_segments
    from ..glossary import format_glossary_prompt

    glossary = format_glossary_prompt(glossary_entries)
    config = getattr(provider, "config", None)
    output_format = getattr(provider, "output_format", "xml")
    model_context = getattr(provider, "model_context", None)
    max_output_tokens = getattr(config, "max_output_tokens", None)
    system_prompt = build_system_prompt(source, target, "", output_format)
    chunks = chunk_request_items(
        requests,
        "openai",
        model_context=model_context,
        system_prompt=system_prompt,
        glossary=glossary,
        output_format=output_format,
        max_output_tokens=max_output_tokens,
    )
    source_segments: dict[int, list[TranslationRequestItem]] = {
        item.id: [] for item in requests
    }
    segment_items: dict[int, TranslationRequestItem] = {}
    for chunk in chunks:
        for item in chunk:
            source_id = item.source_id if item.source_id is not None else item.id
            source_segments[source_id].append(item)
            segment_items[item.id] = item
    for values in source_segments.values():
        values.sort(key=lambda item: item.segment_index if item.segment_index is not None else 0)

    def run_chunk(chunk: list[TranslationRequestItem]) -> tuple[list[dict[str, Any]], tuple[int, ...]]:
        expected = tuple(item.id for item in chunk)
        if _cancel_requested(cancel_event):
            return ([_cancelled_result(item) for item in chunk], expected)
        try:
            block = provider.translate_items(
                chunk,
                source,
                target,
                glossary=glossary,
                cancel_event=cancel_event,
            )
            if _cancel_requested(cancel_event):
                return ([_cancelled_result(item) for item in chunk], expected)
            return (
                [
                    {
                        **item.to_dict(),
                        "status": "succeeded",
                        "error": None,
                        "error_code": None,
                        "diagnostic": block.diagnostic,
                    }
                    for item in block.items
                ],
                expected,
            )
        except OutputContractError as exc:
            return (
                [
                    _failed_result(
                        item,
                        code=exc.code,
                        message=str(exc),
                        diagnostic=exc.diagnostic,
                    )
                    for item in chunk
                ],
                expected,
            )
        except ProviderError as exc:
            if exc.code == "cancelled":
                return ([_cancelled_result(item) for item in chunk], expected)
            return (
                [
                    _failed_result(
                        item,
                        code=exc.code,
                        message=str(exc),
                        diagnostic=exc.diagnostic,
                    )
                    for item in chunk
                ],
                expected,
            )
        except Exception as exc:  # noqa: BLE001
            return (
                [
                    _failed_result(
                        item,
                        code="provider_error",
                        message=f"翻译服务异常（{type(exc).__name__}）",
                        diagnostic={"exception_type": type(exc).__name__},
                    )
                    for item in chunk
                ],
                expected,
            )

    segment_outcomes: dict[int, dict[str, Any]] = {}
    worker_count = max(1, min(int(concurrency), len(chunks)))
    if worker_count == 1:
        chunk_results = [run_chunk(chunk) for chunk in chunks]
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = [pool.submit(run_chunk, chunk) for chunk in chunks]
            chunk_results = [future.result() for future in as_completed(futures)]
    for outcomes, expected in chunk_results:
        by_id = {outcome.get("id"): outcome for outcome in outcomes}
        for item_id in expected:
            segment_outcomes[item_id] = by_id.get(
                item_id,
                {
                    "id": item_id,
                    "translation": segment_items[item_id].text,
                    "status": "failed",
                    "error": "翻译任务未返回结果",
                    "error_code": "batch_incomplete",
                    "diagnostic": None,
                    "uncertain_terms": [],
                },
            )

    results: list[dict[str, Any]] = []
    for source_item in requests:
        segments = source_segments[source_item.id]
        outcomes = [segment_outcomes[item.id] for item in segments]
        if any(outcome["status"] == "cancelled" for outcome in outcomes):
            results.append(_cancelled_result(source_item))
            continue
        if any(outcome["status"] != "succeeded" for outcome in outcomes):
            failure = next(outcome for outcome in outcomes if outcome["status"] != "succeeded")
            results.append(
                _failed_result(
                    source_item,
                    code=failure.get("error_code") or "provider_error",
                    message=failure.get("error") or "翻译失败",
                    diagnostic=failure.get("diagnostic"),
                )
            )
            continue
        translations = {item.id: segment_outcomes[item.id]["translation"] for item in segments}
        if len(segments) == 1 and segments[0].source_id is None:
            translation = translations[segments[0].id]
        else:
            translation = reassemble_segments(
                segments,
                translations,
                {source_item.id: source_item.text},
            )[source_item.id]
        terms: list[dict[str, str]] = []
        for outcome in outcomes:
            terms.extend(outcome.get("uncertain_terms", []))
        results.append(
            {
                "id": source_item.id,
                "translation": translation,
                "uncertain_terms": terms,
                "status": "succeeded",
                "error": None,
                "error_code": None,
                "diagnostic": next(
                    (outcome.get("diagnostic") for outcome in outcomes if outcome.get("diagnostic") is not None),
                    None,
                ),
            }
        )
    return results
