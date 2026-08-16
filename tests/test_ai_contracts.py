"""Cross-layer invariants for translation summaries and diagnostics."""

import pytest

from office_translate.ai.contracts import (
    OperationSummary,
    OutputContractError,
    ProviderCompletion,
    TranslationBlockResult,
    TranslationRequestItem,
    TranslationResultItem,
)


def test_operation_summary_partitions_every_input_id():
    summary = OperationSummary.from_outcomes(
        range(4),
        succeeded_ids=[0, 2],
        failed_ids=[1],
        cancelled_ids=[3],
    )
    assert summary.to_dict() == {
        "status": "partial",
        "total": 4,
        "succeeded": 2,
        "failed": 1,
        "cancelled": 1,
        "succeeded_ids": [0, 2],
        "failed_ids": [1],
        "cancelled_ids": [3],
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"succeeded_ids": [0], "failed_ids": [], "cancelled_ids": []},
        {"succeeded_ids": [0], "failed_ids": [0], "cancelled_ids": [1]},
        {"succeeded_ids": [0], "failed_ids": [2], "cancelled_ids": []},
    ],
)
def test_operation_summary_rejects_missing_duplicate_or_unknown_ids(kwargs):
    with pytest.raises(OutputContractError, match="恰好覆盖"):
        OperationSummary.from_outcomes(range(2), **kwargs)


def test_operation_summary_rejects_count_or_status_tampering():
    payload = OperationSummary.from_outcomes(
        range(2),
        succeeded_ids=[0, 1],
    ).to_dict()
    payload["failed"] = 1
    with pytest.raises(OutputContractError, match="计数"):
        OperationSummary.from_dict(payload, range(2))

    payload = OperationSummary.from_outcomes(
        range(2),
        succeeded_ids=[0, 1],
    ).to_dict()
    payload["status"] = "partial"
    with pytest.raises(OutputContractError, match="不一致"):
        OperationSummary.from_dict(payload, range(2))


def test_provider_diagnostic_redacts_secret_bearing_fields():
    completion = ProviderCompletion(
        content="{}",
        finish_reason="length",
        raw_response={
            "id": "response-1",
            "api_key": "secret",
            "headers": {"Authorization": "Bearer secret"},
            "choices": [{"finish_reason": "length"}],
        },
    )
    diagnostic = completion.diagnostic()
    assert diagnostic["raw_response"]["id"] == "response-1"
    assert diagnostic["raw_response"]["api_key"] == "[REDACTED]"
    assert diagnostic["raw_response"]["headers"] == "[REDACTED]"


def test_segmented_request_contract_carries_complete_offsets():
    item = TranslationRequestItem(
        id=9,
        text="segment",
        source_id=2,
        offset_start=10,
        offset_end=17,
        segment_index=1,
        segment_count=3,
    )
    assert item.to_dict() == {
        "id": 9,
        "text": "segment",
        "source_id": 2,
        "offset_start": 10,
        "offset_end": 17,
        "segment_index": 1,
        "segment_count": 3,
    }


def test_segmented_request_rejects_partial_metadata():
    with pytest.raises(OutputContractError) as caught:
        TranslationRequestItem(id=9, text="segment", source_id=2)
    assert caught.value.code == "invalid_request"


def test_cancelled_block_cannot_carry_success_items():
    block = TranslationBlockResult(
        status="cancelled",
        expected_ids=(0,),
        error_code="cancelled",
        error="cancelled",
    )
    assert block.status == "cancelled"
    with pytest.raises(OutputContractError) as caught:
        TranslationBlockResult(
            status="cancelled",
            expected_ids=(0,),
            items=(TranslationResultItem(id=0, translation="译文"),),
            error_code="cancelled",
            error="cancelled",
        )
    assert caught.value.code == "invalid_block"
