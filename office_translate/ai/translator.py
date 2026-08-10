"""批量翻译编排：支持不确定术语自报 + 术语库注入 + 失败降级。

- `translate_batch`：对一批文本翻译，返回每条 {id, translation, uncertain_terms}。
- 使用 OpenAI 兼容 Provider 时，prompt 要求模型返回结构化 JSON
  （译文 + 不确定术语列表）；模型不返回 JSON 时降级为纯文本译文。
- Google Provider 无自报能力，直接返回纯译文。
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from .provider import OpenAICompatProvider, Provider, ProviderError

# JSON 块匹配：```json ... ``` 或裸 JSON 对象
_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)

# 不确定术语的 JSON Schema（用于 response_format 约束模型输出）
TRANSLATION_SCHEMA = {
    "type": "object",
    "properties": {
        "translation": {"type": "string", "description": "翻译后的文本"},
        "uncertain_terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string", "description": "不确定的术语原文"},
                    "reason": {"type": "string", "description": "不确定原因"},
                    "candidate": {"type": "string", "description": "候选译法"},
                },
                "required": ["term", "reason", "candidate"],
            },
        },
    },
    "required": ["translation", "uncertain_terms"],
}

_SYSTEM_TMPL = (
    "You are a professional translation engine. Translate the following text "
    "from {source} to {target}.\n"
    "{glossary}"
    "\n"
    "Rules:\n"
    "- Output MUST be a valid JSON object matching the provided schema.\n"
    "- translation: the translated text.\n"
    "- uncertain_terms: list terms you are NOT confident about "
    "(proper nouns, abbreviations, ambiguous words). Empty list if fully confident.\n"
    "- Keep the original structure, line breaks, and formatting."
)


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """从模型输出中提取 JSON 对象；失败返回 None。"""
    m = _JSON_BLOCK.search(text)
    if m:
        candidate = m.group(1)
    else:
        obj = _JSON_OBJ.search(text)
        candidate = obj.group(0) if obj else None
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _parse_result(content: str) -> dict[str, Any]:
    """解析模型输出为 {translation, uncertain_terms}；无法解析时降级为纯文本。"""
    obj = _extract_json(content)
    if not obj:
        return {"translation": content.strip(), "uncertain_terms": []}
    translation = obj.get("translation")
    if not isinstance(translation, str):
        # JSON 但缺 translation 字段 → 降级为整段原文
        return {"translation": content.strip(), "uncertain_terms": []}
    terms = obj.get("uncertain_terms", [])
    if not isinstance(terms, list):
        terms = []
    cleaned = []
    for t in terms:
        if isinstance(t, dict) and t.get("term"):
            cleaned.append(
                {
                    "term": str(t.get("term", "")).strip(),
                    "reason": str(t.get("reason", "")).strip(),
                    "candidate": str(t.get("candidate", "")).strip(),
                }
            )
    return {"translation": translation, "uncertain_terms": cleaned}


def translate_batch(
    texts: list[str],
    provider: Provider,
    source: str = "en",
    target: str = "zh-CN",
    glossary_entries: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """批量翻译文本。

    Args:
        texts: 待译文本列表。
        provider: 翻译 Provider。
        source/target: 源/目标语言代码。
        glossary_entries: 已匹配的术语库条目（仅 OpenAI 兼容注入）。

    Returns:
        [{id, translation, uncertain_terms}]，与 texts 等长。
    """
    from ..glossary import format_glossary_prompt

    results: list[dict[str, Any]] = []
    for i, text in enumerate(texts):
        try:
            if isinstance(provider, OpenAICompatProvider):
                content = provider._chat_with_glossary(text, source, target, format_glossary_prompt(glossary_entries))
                parsed = _parse_result(content)
                results.append({"id": i, "translation": parsed["translation"], "uncertain_terms": parsed["uncertain_terms"]})
            else:
                translation = provider.translate(text, source, target)
                results.append({"id": i, "translation": translation, "uncertain_terms": []})
        except ProviderError:
            # 失败降级：保留原文，标注不确定（供用户留意）
            results.append(
                {
                    "id": i,
                    "translation": text,
                    "uncertain_terms": [{"term": text[:80], "reason": "翻译失败，保留原文", "candidate": ""}],
                }
            )
    return results
