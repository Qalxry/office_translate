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

# XML 标签匹配（response_format 全不支持时的兜底输出格式）
# 每行一个 <item>，行边界由标签决定（内容里的换行不影响对齐）；
# <uncertain> 块独立于正文，与行对齐隔离。
_XML_RESULT = re.compile(r"<translation_result>(.*?)</translation_result>", re.DOTALL)
_XML_ITEM = re.compile(r"<item>(.*?)</item>", re.DOTALL)
_XML_TERM = re.compile(r"<uncertain>\s*(.*?)\s*</uncertain>", re.DOTALL)
_XML_FIELD = re.compile(r"<(term|reason|candidate)>(.*?)</\1>", re.DOTALL)

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

# XML 兜底模板：response_format 全不支持的端点（deepseek-reasoner / Ollama 等）。
# 每行一个 <item>：行边界由标签决定，模型少打/多打换行都不影响对齐；
# <uncertain> 独立于正文，与行对齐隔离（一条术语的增删不影响映射）。
_SYSTEM_TMPL_XML = (
    "You are a professional translation engine. Translate the following text "
    "from {source} to {target}.\n"
    "{glossary}"
    "\n"
    "Rules:\n"
    "- Output MUST use XML tags with EXACTLY this structure:\n"
    "  <translation_result>\n"
    "    <item>translation of the first input line</item>\n"
    "    <item>translation of the second input line</item>\n"
    "    <uncertain>\n"
    "      <term>a term you are not confident about</term>\n"
    "      <reason>why you are unsure</reason>\n"
    "      <candidate>suggested translation</candidate>\n"
    "    </uncertain>\n"
    "  </translation_result>\n"
    "- Each input line MUST be translated to EXACTLY ONE <item>, in the same order. "
    "Never merge or split lines. One <item> per input line, no more, no less.\n"
    "- If fully confident, output no <uncertain> block at all.\n"
    "- If the translated text contains < or & characters, write &lt; and &amp;."
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


def _xml_unescape(s: str) -> str:
    """反转义 XML 实体（&lt; &amp; 等）。"""
    import html as _html

    return _html.unescape(s)


def _clean_terms(raw: list) -> list[dict[str, str]]:
    """清洗不确定术语列表（JSON 或 XML 解析后统一结构）。"""
    cleaned = []
    for t in raw:
        if isinstance(t, dict) and t.get("term"):
            cleaned.append(
                {
                    "term": str(t.get("term", "")).strip(),
                    "reason": str(t.get("reason", "")).strip(),
                    "candidate": str(t.get("candidate", "")).strip(),
                }
            )
    return cleaned


def _parse_result(content: str) -> dict[str, Any]:
    """解析模型输出为 {translations: list[str], uncertain_terms: list[dict]}。

    translations 是逐行列表（行边界结构化，杜绝换行错位）：
    - JSON（json_schema / json_object）：translation 字符串按 \\n 拆分（JSON 内 \\n 是转义，安全）
    - XML（无 response_format 兜底）：每个 <item> 一行，行边界由标签决定
    - 纯文本：按换行切分
    """
    obj = _extract_json(content)
    if obj:
        translation = obj.get("translation")
        if isinstance(translation, str):
            terms = obj.get("uncertain_terms", [])
            if not isinstance(terms, list):
                terms = []
            return {
                "translations": translation.split("\n"),
                "uncertain_terms": _clean_terms(terms),
            }
    # XML 标签兜底：每行一个 <item>，<uncertain> 块独立
    m = _XML_RESULT.search(content)
    if m:
        body = m.group(1)
        translations = [_xml_unescape(t.strip()) for t in _XML_ITEM.findall(body)]
        cleaned = []
        for seg in _XML_TERM.findall(body):
            fields: dict[str, str] = {}
            for fm in _XML_FIELD.finditer(seg):
                fields[fm.group(1)] = _xml_unescape(fm.group(2).strip())
            if fields.get("term"):
                cleaned.append(
                    {
                        "term": fields.get("term", ""),
                        "reason": fields.get("reason", ""),
                        "candidate": fields.get("candidate", ""),
                    }
                )
        return {"translations": translations, "uncertain_terms": cleaned}
    return {"translations": content.split("\n"), "uncertain_terms": []}


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
                results.append(
                    {
                        "id": i,
                        "translation": "\n".join(parsed["translations"]),
                        "uncertain_terms": parsed["uncertain_terms"],
                    }
                )
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
