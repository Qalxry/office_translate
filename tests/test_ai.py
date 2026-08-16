"""AI provider and strict translation contract tests."""

from types import SimpleNamespace

import pytest

from office_translate.ai.contracts import (
    TRANSLATION_SCHEMA,
    OutputContractError,
    ProviderCompletion,
    TranslationBlockResult,
    TranslationRequestItem,
    TranslationResultItem,
    parse_translation_result,
)
from office_translate.ai.provider import (
    GoogleProvider,
    MirrorPool,
    OpenAICompatProvider,
    Provider,
    ProviderConfig,
    ProviderError,
)
from office_translate.ai.translator import translate_batch


class FakeProvider:
    def translate(self, text, source, target):
        return "译文:" + text


def test_mirror_pool_fallback_on_failure():
    calls = []

    def func(mirror, *args):
        calls.append(mirror)
        raise ProviderError(f"{mirror} failed")

    pool = MirrorPool(["a", "b"], max_failures=2, cooldown_seconds=3600)
    with pytest.raises(ProviderError):
        pool.execute(func)
    assert calls == ["a", "b"]


def test_mirror_pool_success_first():
    calls = []

    def func(mirror, *args):
        calls.append(mirror)
        if mirror == "a":
            raise ProviderError("a down")
        return "ok"

    pool = MirrorPool(["a", "b"], max_failures=2, cooldown_seconds=3600)
    assert pool.execute(func) == "ok"
    assert calls == ["a", "b"]


def test_mirror_pool_cooldown():
    calls = []

    def func(mirror, *args):
        calls.append(mirror)
        raise ProviderError("down")

    pool = MirrorPool(["a"], max_failures=2, cooldown_seconds=3600)
    for _ in range(3):
        with pytest.raises(ProviderError):
            pool.execute(func)
    assert calls == ["a", "a"]


def test_mirror_pool_empty_raises():
    with pytest.raises(ValueError):
        MirrorPool([])


def test_mirror_pool_snapshot():
    pool = MirrorPool(["a"], max_failures=1, cooldown_seconds=3600)

    def func(mirror, *args):
        raise ProviderError("x")

    with pytest.raises(ProviderError):
        pool.execute(func)
    assert pool.snapshot()[0]["available"] is False


@pytest.mark.p0_regression
def test_p0_07_schema_requires_id_bearing_items():
    assert TRANSLATION_SCHEMA["required"] == ["items"]
    assert TRANSLATION_SCHEMA["additionalProperties"] is False
    item_schema = TRANSLATION_SCHEMA["properties"]["items"]["items"]
    assert item_schema["additionalProperties"] is False
    assert set(item_schema["required"]) == {
        "id",
        "translation",
        "uncertain_terms",
    }
    term_schema = item_schema["properties"]["uncertain_terms"]["items"]
    assert term_schema["additionalProperties"] is False


def test_parse_strict_items_preserves_internal_line_breaks_and_input_order():
    content = (
        '{"items":['
        '{"id":1,"translation":"second","uncertain_terms":[]},'
        '{"id":0,"translation":"first\\ncontinued","uncertain_terms":'
        '[{"term":"PPB","reason":"abbr","candidate":"parts per billion"}]}'
        "]}"
    )
    parsed = parse_translation_result(content, [0, 1])
    assert [item.id for item in parsed] == [0, 1]
    assert parsed[0].translation == "first\ncontinued"
    assert parsed[0].uncertain_terms[0]["term"] == "PPB"


@pytest.mark.parametrize(
    ("content", "code"),
    [
        ("not json", "malformed_json"),
        ('```json\n{"items":[]}\n```', "malformed_json"),
        ("<translation_result><item>x</item></translation_result>", "malformed_json"),
        ('{"translation":"legacy","uncertain_terms":[]}', "invalid_schema"),
        ('{"items":[],"extra":true}', "invalid_schema"),
        ('{"items":[{"id":0,"translation":"x","uncertain_terms":[],"extra":1}]}', "invalid_schema"),
    ],
)
def test_old_or_malformed_output_is_rejected(content, code):
    with pytest.raises(OutputContractError) as caught:
        parse_translation_result(content, [] if '"items":[]' in content else [0])
    assert caught.value.code == code


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (
            '{"items":[{"id":0,"translation":"a","uncertain_terms":[]},'
            '{"id":0,"translation":"b","uncertain_terms":[]}]}',
            "duplicate_id",
        ),
        (
            '{"items":[{"id":0,"translation":"a","uncertain_terms":[]}]}',
            "id_set_mismatch",
        ),
        (
            '{"items":[{"id":0,"translation":"a","uncertain_terms":[]},'
            '{"id":2,"translation":"c","uncertain_terms":[]}]}',
            "id_set_mismatch",
        ),
    ],
)
def test_result_id_set_must_be_exact(content, code):
    with pytest.raises(OutputContractError) as caught:
        parse_translation_result(content, [0, 1])
    assert caught.value.code == code


@pytest.mark.parametrize(
    ("completion", "code"),
    [
        (ProviderCompletion("{}", "length"), "truncated"),
        (ProviderCompletion("{}", "stop", refusal="denied"), "refusal"),
        (ProviderCompletion("", "stop"), "empty_response"),
        (ProviderCompletion("{}", None), "incomplete_completion"),
        (ProviderCompletion("{}", "content_filter"), "incomplete_completion"),
    ],
)
def test_provider_completion_rejects_non_success(completion, code):
    with pytest.raises(OutputContractError) as caught:
        completion.require_complete()
    assert caught.value.code == code


def test_provider_completion_accepts_stop_with_content():
    ProviderCompletion('{"items":[]}', "stop").require_complete()


def test_openai_translate_items_validates_completion_before_json(monkeypatch):
    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    provider.output_format = "json"
    monkeypatch.setattr(
        provider,
        "_chat_with_glossary",
        lambda *args, **kwargs: ProviderCompletion(
            '{"items":[{"id":0,"translation":"partial","uncertain_terms":[]}]}',
            "length",
            raw_response={"id": "response-id"},
        ),
    )
    with pytest.raises(OutputContractError, match="截断") as caught:
        provider.translate_items(
            [TranslationRequestItem(0, "source")],
            "en",
            "zh-CN",
        )
    assert caught.value.code == "truncated"
    assert caught.value.diagnostic["raw_response"]["id"] == "response-id"


def test_openai_translate_items_parses_xml_by_default(monkeypatch):
    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    provider.output_format = "xml"
    monkeypatch.setattr(
        provider,
        "_chat_with_glossary",
        lambda *args, **kwargs: ProviderCompletion(
            "<items>"
            '<item id="0"><translation>你好</translation><uncertain_terms/></item>'
            "</items>",
            "stop",
        ),
    )
    block = provider.translate_items(
        [TranslationRequestItem(0, "hello")],
        "en",
        "zh-CN",
    )
    assert block.items[0].translation == "你好"


@pytest.mark.parametrize(
    ("output_format", "response_format", "expected"),
    [
        ("json", "auto", {"type": "json_object"}),
        ("json", "json_object", {"type": "json_object"}),
        ("json", "none", None),
        ("json", "json_schema", "json_schema"),
    ],
)
def test_openai_response_format_option(output_format, response_format, expected):
    provider = OpenAICompatProvider(
        base_url="http://127.0.0.1:9/v1",
        api_key="k",
        model="m",
        model_config={
            "output_format": output_format,
            "response_format": response_format,
        },
    )
    fmt = provider._response_format()
    if expected is None:
        assert fmt is None
    elif expected == "json_schema":
        assert fmt["type"] == "json_schema"
        assert fmt["json_schema"]["name"] == "translation_result"
        assert fmt["json_schema"]["strict"] is True
        assert fmt["json_schema"]["schema"]["additionalProperties"] is False
    else:
        assert fmt == expected


def test_openai_json_defaults_to_stream_compatible_response_format_none():
    provider = OpenAICompatProvider(
        base_url="http://127.0.0.1:9/v1",
        api_key="k",
        model="m",
        model_config={"output_format": "json"},
    )
    assert provider.config.response_format == "none"
    assert provider._response_format() is None


@pytest.mark.parametrize(
    ("output_format", "response_format"),
    [
        ("xml", "json_object"),
        ("text", "json_schema"),
        ("json", "yaml"),
    ],
)
def test_openai_response_format_invalid_combinations(output_format, response_format):
    with pytest.raises(ProviderError):
        OpenAICompatProvider(
            base_url="http://127.0.0.1:9/v1",
            api_key="k",
            model="m",
            model_config={
                "output_format": output_format,
                "response_format": response_format,
            },
        )


def test_openai_stream_rejects_refusal(monkeypatch):
    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    provider.output_format = "json"
    chunks = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    delta=SimpleNamespace(
                        reasoning_content=None,
                        refusal="denied",
                        content=None,
                    ),
                )
            ]
        )
    ]
    monkeypatch.setattr(provider, "_chat_create", lambda *args, **kwargs: chunks)
    events = list(
        provider.translate_stream(
            [TranslationRequestItem(0, "source")],
            "en",
            "zh-CN",
        )
    )
    assert events[-1]["type"] == "block_failed"
    assert events[-1]["error_code"] == "refusal"


def test_openai_provider_classifies_usage_limit_without_exposing_message():
    class RateLimited(Exception):
        status_code = 429

    error = OpenAICompatProvider._provider_error(
        RateLimited("Bearer secret at /private/path")
    )
    assert error.code == "usage_limit"
    assert "secret" not in str(error)
    assert error.diagnostic == {
        "exception_type": "RateLimited",
        "status_code": 429,
    }


def test_translate_batch_fake_provider():
    results = translate_batch(["Hello", "World"], FakeProvider())
    assert [item["translation"] for item in results] == [
        "译文:Hello",
        "译文:World",
    ]
    assert all(item["status"] == "succeeded" for item in results)


def test_translate_batch_failure_is_explicit_draft():
    class Failing:
        def translate(self, text, source, target):
            raise ProviderError("boom", code="network")

    results = translate_batch(["Hello"], Failing())
    assert results == [
        {
            "id": 0,
            "translation": "Hello",
            "uncertain_terms": [],
            "status": "failed",
            "error": "boom",
            "error_code": "network",
            "diagnostic": None,
        }
    ]


def test_translate_batch_concurrency():
    import threading
    import time

    from office_translate.ai.provider import Provider

    active = 0
    peak = 0
    lock = threading.Lock()

    class Slow(Provider):
        name = "slow"

        def translate(self, text, source, target):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return f"译:{text}"

    results = Slow().translate_batch(
        [f"t{i}" for i in range(6)],
        "en",
        "zh-CN",
        concurrency=3,
    )
    assert results[0] == "译:t0"
    assert peak >= 2


def test_provider_batch_all_failures_are_explicit_and_ordered():
    class Failing(Provider):
        name = "failing"

        def translate(self, text, source, target):
            raise ProviderError("temporary", code="network_error")

    outcomes = Failing().translate_batch_outcomes(
        ["zero", "one", "two"], "en", "zh-CN", concurrency=2
    )
    assert [item["id"] for item in outcomes] == [0, 1, 2]
    assert [item["status"] for item in outcomes] == ["failed"] * 3
    assert [item["translation"] for item in outcomes] == ["zero", "one", "two"]
    assert all(item["error_code"] == "network_error" for item in outcomes)


def test_provider_batch_cancellation_stops_subsequent_success_publication():
    import threading

    cancelled = threading.Event()
    calls = []

    class Cancelling(Provider):
        name = "cancelling"

        def translate(self, text, source, target):
            calls.append(text)
            if text == "one":
                cancelled.set()
            return "译:" + text

    outcomes = Cancelling().translate_batch_outcomes(
        ["zero", "one", "two"],
        "en",
        "zh-CN",
        concurrency=1,
        cancel_event=cancelled,
    )
    assert [item["status"] for item in outcomes] == [
        "succeeded",
        "cancelled",
        "cancelled",
    ]
    assert calls == ["zero", "one"]


def test_provider_batch_concurrency_is_capped_and_results_keep_input_order():
    import threading
    import time

    active = 0
    peak = 0
    lock = threading.Lock()

    class Uneven(Provider):
        name = "uneven"

        def translate(self, text, source, target):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep((5 - int(text)) * 0.005)
            with lock:
                active -= 1
            return "译:" + text

    outcomes = Uneven().translate_batch_outcomes(
        [str(index) for index in range(6)],
        "en",
        "zh-CN",
        concurrency=2,
    )
    assert peak == 2
    assert [item["translation"] for item in outcomes] == [
        f"译:{index}" for index in range(6)
    ]


def test_provider_config_is_one_validated_effective_snapshot():
    config = ProviderConfig.from_model_config(
        base_url="https://example.invalid/v1/",
        model="model-a",
        temperature=0.6,
        model_config={
            "model_context": 8192,
            "temperature": 0.2,
            "max_tokens": 1024,
            "thinking": {"type": "enabled"},
            "output_format": "json",
            "response_format": "json_schema",
        },
    )
    assert config.base_url == "https://example.invalid/v1"
    assert config.request_params["temperature"] == 0.2
    assert config.request_params["max_tokens"] == 1024
    assert config.extra_body == {"thinking": {"type": "enabled"}}
    assert config.model_context == 8192


def test_provider_config_rejects_unknown_model_parameter():
    with pytest.raises(ProviderError) as caught:
        ProviderConfig.from_model_config(
            base_url="https://example.invalid/v1",
            model="model-a",
            temperature=0.6,
            model_config={"temperatur": 0.2},
        )
    assert caught.value.code == "unsupported_model_parameter"
    assert caught.value.retryable is False


def test_google_request_and_response_are_validated(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return [[["你", "hello"], ["好", "world"]]]

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("office_translate.ai.provider.requests.post", fake_post)
    provider = GoogleProvider(["https://mirror.invalid/"])
    assert provider.translate("hello world", "en", "zh-CN") == "你好"
    assert captured["url"] == "https://mirror.invalid/translate_a/single"
    assert captured["data"] == {
        "client": "gtx",
        "sl": "en",
        "tl": "zh-CN",
        "dt": "t",
        "q": "hello world",
    }


def test_openai_batch_reassembles_long_item_to_original_id(monkeypatch):
    provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
    provider.output_format = "xml"
    provider.model_context = 1000
    provider.config = SimpleNamespace(max_output_tokens=100)
    calls = []

    def fake_translate_items(items, source, target, *, glossary="", cancel_event=None):
        calls.append(tuple(item.id for item in items))
        return TranslationBlockResult(
            status="succeeded",
            expected_ids=tuple(item.id for item in items),
            items=tuple(
                TranslationResultItem(
                    id=item.id,
                    translation=f"<{item.id}>{item.text}",
                )
                for item in items
            ),
        )

    monkeypatch.setattr(provider, "translate_items", fake_translate_items)
    results = translate_batch(
        ["x" * 1600],
        provider,
        concurrency=2,
    )
    assert len(calls) >= 2
    assert results[0]["id"] == 0
    assert results[0]["status"] == "succeeded"
    assert results[0]["translation"].count("<") == sum(len(call) for call in calls)
