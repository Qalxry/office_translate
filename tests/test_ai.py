"""AI 翻译核心测试：MirrorPool 切换/冷却、translate_batch 降级、JSON 解析。"""

import pytest

from office_translate.ai.provider import MirrorPool, ProviderError
from office_translate.ai.translator import _extract_json, _parse_result, translate_batch


class FakeProvider:
    """假 Provider：可配置成功/失败的站点。"""

    def __init__(self, mirror_result: dict[str, str]):
        self.mirror_result = mirror_result

    def translate(self, text, source, target):
        # 无自报能力的 provider 直接返回
        return "译文:" + text


# ---------- MirrorPool ----------

def test_mirror_pool_fallback_on_failure():
    calls = []

    def func(mirror, *a):
        calls.append(mirror)
        raise ProviderError(f"{mirror} failed")

    pool = MirrorPool(["a", "b"], max_failures=2, cooldown_seconds=3600)
    with pytest.raises(ProviderError):
        pool.execute(func)
    assert calls == ["a", "b"]  # 依次尝试两个


def test_mirror_pool_success_first():
    calls = []

    def func(mirror, *a):
        calls.append(mirror)
        if mirror == "a":
            raise ProviderError("a down")
        return "ok"

    pool = MirrorPool(["a", "b"], max_failures=2, cooldown_seconds=3600)
    assert pool.execute(func) == "ok"
    assert calls == ["a", "b"]


def test_mirror_pool_cooldown():
    # 连续失败达阈值后进入冷却，不再尝试
    calls = []

    def func(mirror, *a):
        calls.append(mirror)
        raise ProviderError("down")

    pool = MirrorPool(["a"], max_failures=2, cooldown_seconds=3600)
    for _ in range(3):
        with pytest.raises(ProviderError):
            pool.execute(func)
    # 前 2 次尝试，第 3 次 a 冷却中 → 也失败但不再调用 func
    assert calls == ["a", "a"]


def test_mirror_pool_empty_raises():
    with pytest.raises(ValueError):
        MirrorPool([])


def test_mirror_pool_snapshot():
    pool = MirrorPool(["a"], max_failures=1, cooldown_seconds=3600)

    def func(mirror, *a):
        raise ProviderError("x")

    with pytest.raises(ProviderError):
        pool.execute(func)
    snap = pool.snapshot()
    assert snap[0]["url"] == "a"
    assert snap[0]["available"] is False  # 已冷却


# ---------- JSON 解析 ----------

def test_extract_json_bare():
    assert _extract_json('{"translation": "你好"}') == {"translation": "你好"}


def test_extract_json_codeblock():
    s = '```json\n{"translation": "你好"}\n```'
    assert _extract_json(s) == {"translation": "你好"}


def test_extract_json_invalid():
    assert _extract_json("not json at all") is None


def test_parse_result_valid():
    content = '{"translation": "你好", "uncertain_terms": [{"term": "PPB", "reason": "缩写", "candidate": "十亿分之几"}]}'
    parsed = _parse_result(content)
    assert parsed["translation"] == "你好"
    assert parsed["uncertain_terms"][0]["term"] == "PPB"


def test_schema_shape():
    """json_schema 输出（含不确定术语嵌套数组）应能被解析。"""
    from office_translate.ai.translator import TRANSLATION_SCHEMA, _parse_result
    # schema 本身合法
    assert TRANSLATION_SCHEMA["required"] == ["translation", "uncertain_terms"]
    # 模型按 schema 输出
    content = '{"translation": "供应商质量评估", "uncertain_terms": [{"term": "PPB", "reason": "缩写", "candidate": "十亿分之几"}]}'
    parsed = _parse_result(content)
    assert parsed["translation"] == "供应商质量评估"
    assert parsed["uncertain_terms"][0]["term"] == "PPB"


def test_parse_result_no_json_fallback():
    parsed = _parse_result("直接输出的译文")
    assert parsed["translation"] == "直接输出的译文"
    assert parsed["uncertain_terms"] == []


def test_parse_result_json_without_translation_fallback():
    parsed = _parse_result('{"foo": "bar"}')
    assert parsed["uncertain_terms"] == []


# ---------- translate_batch ----------

def test_translate_batch_fake_provider():
    provider = FakeProvider({})
    results = translate_batch(["Hello", "World"], provider)
    assert len(results) == 2
    assert results[0]["translation"] == "译文:Hello"
    assert results[1]["translation"] == "译文:World"
    assert all(r["uncertain_terms"] == [] for r in results)


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

    results = Slow().translate_batch([f"t{i}" for i in range(6)], "en", "zh-CN", concurrency=3)
    assert len(results) == 6
    assert peak >= 2  # 确实并发过
    assert results[0] == "译:t0"


def test_translate_batch_failure_degrades():
    class Failing:
        def translate(self, text, source, target):
            raise ProviderError("boom")

    results = translate_batch(["Hello"], Failing())
    assert results[0]["translation"] == "Hello"  # 保留原文
    assert results[0]["uncertain_terms"][0]["reason"] == "翻译失败，保留原文"
