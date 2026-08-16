# P0 — 关键缺陷：可能造成错误文档或核心流程失效

> 最后审计日期: 2026-08-15
> 最后编号：P0-08

---

## ~~🔴 P0-05. 任务、映射和译文没有版本绑定，旧产物或其他任务译文可静默写入当前文档~~ ✅ 已修复

> 严重程度: 🔴 关键
> 影响范围: GUI 任务状态机、重新提取、任务切换、回填正确性
> 评级理由: 可生成文件名和结构均正常、但内容属于旧版本或另一任务的错误输出

### 问题描述

任务阶段只根据若干文件是否存在推导。`source.txt`、`map.json`、`translated.txt`、`ai_output.json` 和输出文件没有输入摘要或修订号，重新提取不会使旧译文和旧输出失效；apply 也不验证映射中的原文是否仍等于当前单元格内容。

前端切换任务时没有先清空全局翻译状态，空的恢复响应不会覆盖上一任务数据，异步响应也没有请求代次保护。审查已分别复现：交换原文单元格后使用旧 map，apply 成功但译文落到错误原文；已导出任务重新提取后仍显示“已导出”，旧输出继续返回 `200`；两个文本数相同的任务切换时，上一任务译文可通过当前任务的行数校验并被导出。

### 位置

- [office_translate/formats/xlsx/extractor.py](office_translate/formats/xlsx/extractor.py#L95-L107)：产物不记录输入摘要或修订。
- [office_translate/formats/xlsx/applier.py](office_translate/formats/xlsx/applier.py#L69-L90)：按坐标直接覆盖，不核对当前原文。
- [office_translate/gui/server.py](office_translate/gui/server.py#L204-L222)：阶段仅由文件存在性推导。
- [office_translate/gui/server.py](office_translate/gui/server.py#L301-L414)：重新提取不失效下游产物，保存和 apply 不校验修订。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L241-L247)：步骤门控只检查全局布尔值和文本。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L723-L759)：切换任务未完整重置状态，也没有防止异步响应乱序。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L1195-L1209)：把当前全局译文直接写入当前任务。

### 影响

用户可能交付内容属于旧文档、旧提取结果或另一任务的翻译文件。只要条目数相同，现有行数校验不会发现，错误通常只能靠人工逐格核对。

### 推荐修复方案

在任务 manifest 中保存显式状态和 `source_revision`，修订由输入文件、原文列表和映射生成稳定摘要。每个下游产物都记录其基于的修订，重新提取成功后原子失效或归档旧译文、AI 输出和导出文件。apply 必须校验 revision、ID 完整性以及当前单元格原文。前端以 job-scoped 状态替代全局布尔值，切换时原子清空并使用 request token 防止旧响应提交。增加重排原文、同条数任务切换、快速切换、重新提取和旧输出下载测试。

### 最终修复情况

已建立以 `manifest.json` 为唯一任务状态源的修订模型。`SourceArtifact` 绑定输入 SHA-256、稳定 `source_revision`、条目 ID 和单元格位置；`TranslationArtifact` 绑定原文修订、译文修订和逐条状态；manifest 只引用完成写入的版本化产物。重新提取会原子切换 manifest，并清理旧结构化译文、旧 TXT/map、AI 输出和旧下载文件。

`JobService` 统一串行化 create、extract、save、apply 和 delete。保存和导出必须提交当前 `source_revision`，导出还必须提交当前 `translation_revision`。回填前同时校验输入文件摘要、ID 完整性、译文状态和每个坐标的当前原文。两份 XLSX 使用唯一发布修订生成，只有两份都成功替换后才更新 manifest；任一发布或 manifest 写入失败都会清理本次文件并保留上一组可下载输出。

前端在任务切换时先清空任务状态并中止活动请求，提取、恢复、手工保存、AI 翻译、失败重试、术语审核和导出均绑定 job request token 与 source revision。旧异步响应可以完成原任务请求，但不能再修改新任务界面或把结果提交给新任务。

主要实施位置：

- [office_translate/artifacts.py](office_translate/artifacts.py#L137-L551)：结构化产物、修订摘要与 manifest 阶段不变量。
- [office_translate/jobs.py](office_translate/jobs.py#L146-L529)：任务锁、版本化产物、失效、双输出发布和下载门控。
- [office_translate/formats/xlsx/applier.py](office_translate/formats/xlsx/applier.py#L43-L151)：输入摘要、revision、ID 和 current-source 校验。
- [office_translate/gui/server.py](office_translate/gui/server.py#L204-L363)：revision-aware GUI 路由。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L278-L1409)：job-scoped 状态与异步代次保护。
- [tests/test_gui.py](tests/test_gui.py#L157-L326)、[tests/test_roundtrip.py](tests/test_roundtrip.py#L72-L91)：重提取、跨任务修订、原子失败和旧映射回归。

验收结果：当前环境与干净 Python 3.11 虚拟环境均为 `87 passed, 2 xfailed`；剩余 xfail 仅属于阶段 2 的 P0-07。

---

## ~~🔴 P0-06. GUI AI 翻译绕过单行转义协议，反斜杠、CRLF 和字面 `\n` 被错误解释~~ ✅ 已修复

> 严重程度: 🔴 关键
> 影响范围: GUI AI 翻译、translated.txt、对照版分隔符、控制字符
> 评级理由: 可静默改变译文内容、破坏记录边界，并直接生成不符合约定的导出文件

### 原始表述

> 「导出的文件没有逆向转义回\n之类的字符」

### 问题描述

核心约定要求 TXT 中一行一条记录，并用 `escape_text()` / `unescape_text()` 表示真实换行和反斜杠。手工底层路径使用了该编解码器，但 GUI 把 AI 结果用物理换行拼接，再由保存接口直接写入 translated.txt。

审查复现：模型结果包含 `C:\new\report` 时，apply 会把其中的 `\n`、`\r` 当成控制字符；一条真实多行译文会被读成多条记录；CRLF 文件会把行尾 `\r` 带入单元格；GUI apply 固定提交字面 `"\\n"`，服务端不解码，最终对照单元格实际为 `'Hello\\n你好'` 而不是真实换行。

### 位置

- [office_translate/escape.py](office_translate/escape.py#L17-L60)：已有正确的单行记录编解码器，但调用边界不统一。
- [office_translate/gui/server.py](office_translate/gui/server.py#L326-L340)：保存接口把任意多行字符串直接覆盖到 translated.txt。
- [office_translate/gui/server.py](office_translate/gui/server.py#L397-L411)：请求体 sep 未经过 `decode_escapes()`。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L1037-L1046)：前端以换行拼接 AI 结果并提交原始文本。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L1195-L1205)：导出时固定发送字面 `\\n`。
- [office_translate/formats/xlsx/applier.py](office_translate/formats/xlsx/applier.py#L30-L47)：按物理换行分记录，再把反斜杠序列解释为控制字符。

### 影响

路径、正则、代码片段等包含 `\n`/`\r` 的正常译文会被静默改变；真实多行译文可能使回填失败或与其他记录错位；GUI 的默认对照版直接显示反斜杠和字母 n。

### 推荐修复方案

让 GUI 和后端始终以结构化结果数组保存译文，TXT 只作为导出或兼容层，由后端统一执行 `escape_text()` / `unescape_text()`。前端不再自行用物理换行拼接记录。分隔符请求应省略并使用已解码任务配置，或由服务端统一调用 `decode_escapes()`。增加反斜杠、字面 `\n`、真实 LF/CR/CRLF、空字符串、尾随反斜杠和 GUI bilingual 的端到端测试。

### 最终修复情况

GUI 内部保存和回填已改为结构化 `items[]`，译文不再经过 TXT 物理行边界或 `unescape_text()`。真实 LF、CR、CRLF、字面 `\n`、普通反斜杠和尾随反斜杠均作为 JSON 字符串原样存储，并直接写入对应 XLSX 单元格。对照版分隔符统一在服务端解码，导出区改为只读预览，避免用户编辑拼接文本却没有同步回结构化条目。

手工模式仍允许办公用户按行批量粘贴单行记录，但逐条编辑器直接修改结构化条目并允许内部换行；原文自身含换行时，界面禁用有歧义的批量复制/粘贴路径并要求逐条填写。旧 TXT adapter 暂时只为阶段 3 删除前的非 GUI 调用保留，不再位于 GUI 主流程。

干净环境复验还发现 `openpyxl` 缺少可选 XML 后端时会把独立 CR 正规化为 LF，因此 [requirements.txt](requirements.txt#L1-L2) 已显式加入 `lxml`，使分发环境与开发环境保持相同的 OOXML 控制字符行为。

主要实施位置：

- [office_translate/artifacts.py](office_translate/artifacts.py#L203-L376)：逐条结构化译文及稳定 revision。
- [office_translate/formats/xlsx/applier.py](office_translate/formats/xlsx/applier.py#L110-L151)：结构化译文直写，不经过 TXT 反转义。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L90-L112)、[office_translate/gui/web/app.js](office_translate/gui/web/app.js#L872-L971)：手工批量边界和多行逐条编辑。
- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L347-L400)、[office_translate/gui/web/index.html](office_translate/gui/web/index.html#L573-L584)：多行安全提示与只读导出预览。
- [tests/test_roundtrip.py](tests/test_roundtrip.py#L93-L137)、[tests/test_storage.py](tests/test_storage.py#L17-L45)：控制字符无损往返和原子写失败回归。

验收结果：P0-06 strict xfail 已转为普通通过测试，当前环境与干净 Python 3.11 虚拟环境均通过完整回归。

---

## ~~🔴 P0-07. 非思考模型的结构化输出协议无法稳定标识记录，异常结果被静默补空或截断~~ ✅ 已修复

> 严重程度: 🔴 关键
> 影响范围: OpenAI 兼容输出格式、SSE 分块、行映射、最终文档
> 评级理由: 模型少行、多行、截断或格式异常时，系统仍可报告 100% 成功并写入空白或错位译文

### 原始表述

> 「在非思考模式下的模型output format异常」

### 问题描述

默认 JSON Schema 只描述单个 `translation` 字符串，GUI 流式端点却把多个源记录用换行合成一个请求，再通过 `translation.split("\n")` 恢复记录边界。译文本身合法包含换行时无法区分“记录边界”和“记录内部换行”。严格 schema 还缺少 OpenAI Structured Outputs 所要求的 `additionalProperties: false`；解析器会把畸形 JSON 降级为普通文本成功，并且没有检查拒答、空内容或 `finish_reason=length`。

服务端发现行数不一致时，少行补空、多行截断，仅向 stdout 打印警告，SSE 仍发送无 error 的 `done`、100% progress 和 end。主线程复现两条原文只返回一条译文时，得到 `(0, "ONLY", None)`、`(1, "", None)`，最终进度为 100%。

### 位置

- [office_translate/ai/translator.py](office_translate/ai/translator.py#L29-L48)：strict schema 不完整且缺少稳定 item ID/数组结构。
- [office_translate/ai/translator.py](office_translate/ai/translator.py#L89-L165)：用标量字符串换行拆分结果，畸形输出降级为成功纯文本。
- [office_translate/ai/provider.py](office_translate/ai/provider.py#L138-L230)：输出格式降级链没有完整结果语义验证。
- [office_translate/ai/provider.py](office_translate/ai/provider.py#L251-L314)：未校验 refusal、finish reason、空响应和截断。
- [office_translate/gui/server.py](office_translate/gui/server.py#L620-L674)：行数不一致时静默补空或截断并继续报告完成。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L957-L983)：流结束后强制设为 100% 并持久化结果。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L1084-L1123)：只有 `data.error` 才记录失败行。

### 影响

输出文件可丢失文本、把一条译文的第二行分配给下一原文，或把后续真实译文截掉。界面仍显示完成，现有重试入口也不会包含这些行。

### 推荐修复方案

改为 ID-bearing 结构，例如 `{"items":[{"id":0,"translation":"...","uncertain_terms":[]}]}`，对 JSON/XML 结果执行完整 schema 校验并要求 ID 唯一、连续且覆盖输入。补齐 strict schema 约束，检查 refusal、finish reason、usage limit 与空内容。任何解析或基数异常都应使整块进入失败状态，保留原文仅作草稿显示，不得开放导出；保存模型原始响应用于诊断。SSE 增加 `failed` 与最终 summary 事件，前端仅在完整 summary 校验通过后进入 ready。测试应覆盖非思考模型、内部换行、少行、多行、重复/缺失 ID、截断、拒答、畸形 JSON/XML 和流中断。

### 最终修复情况

已删除标量 `translation`、Markdown code fence 和旧式按换行拆项等无法稳定标识记录的旧协议，正式输出协议收敛为模型级 `output_format` 三选（默认 `xml`）：JSON 使用严格 `items[]`，可乱序返回并按请求 ID 归位；XML 使用带 `id` 属性的 `<items><item><translation>…</translation></item></items>`，同样校验完整 ID 集合；文本模式每条译文一行、按输入顺序对应，行内除空格外的空白字符使用 `\n`、`\t`、`\r`、`\\` 等字面转义，行数必须与输入严格一致，否则整块失败。JSON/XML 的根、结果项和不确定术语对象全部使用严格 schema/标签与属性校验，重复、缺失、未知 ID 一律拒绝；真实换行在 JSON/XML 中保留在单个 `translation` 中，在文本模式中经转义往返。

Provider 现在先检查 `refusal`、`finish_reason`、额度/限流、空响应和截断，再允许解析内容。响应诊断会保存完成原因和原始模型响应，但会移除 API key、Authorization 和请求头；异常消息不向 GUI 暴露密钥或完整本地路径。传输层只在 JSON 模式尝试 `json_object`，模型不支持时退回普通模式；文本与 XML 模式不传 `response_format`。内容协议和解析器不降级，也不存在任何旧格式兼容分支。

SSE 改为 `meta`、`thinking`、`item_preview`、`item_succeeded`、`item_failed`、`progress` 和唯一最终 `summary`。原始协议正文（content delta）不再转发给前端；服务端从累积正文中增量提取已完成的翻译片段，逐条上屏，正式结果仍以整块终态校验为准。服务端先缓存并验证整块终态 ID 集合，再发出逐项结果；缺项、重复、未知事件、畸形 payload 或流中断时，已完整解析且结构合法的条目保留为成功，缺失/损坏条目失败，不补空、不截断、不发送伪成功。`summary` 的成功、失败和取消 ID 必须无重复且恰好覆盖输入，计数必须守恒，partial 状态不可导出。XML 解析器会修复模型中未转义的裸 `&`（仅修复转义，结构校验不放松）。

`TranslationArtifact` schema 已升级到 v2，将 summary 和本地诊断绑定到 `translation_revision`。AI 输出保存接口拒绝缺失或矛盾的 summary；后端 apply 和前端导出按钮都只接受完整 succeeded summary。前端不再在连接结束后强制设置 100%，没有收到合法 summary、任务被停止或流中断时会生成明确的 failed/cancelled 草稿状态并保持导出禁用。按用户要求未实现旧产物或旧模型输出兼容。

主要实施位置：

- [office_translate/ai/contracts.py](office_translate/ai/contracts.py#L10-L520)：text/json/xml 严格解析、转义往返、完成元数据、块状态和 operation summary。
- [office_translate/ai/streaming.py](office_translate/ai/streaming.py#L1-L180)：三种协议的流式增量片段提取。
- [office_translate/ai/provider.py](office_translate/ai/provider.py#L120-L410)：output_format 协议选择、json_object 自动协商、拒答/截断/额度检测、流式终态和脱敏诊断。
- [office_translate/gui/server.py](office_translate/gui/server.py#L317-L920)：summary 持久化要求、块级集合校验、item_preview 生成和新 SSE 事件。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L115-L1480)：逐条预览、summary 严格校验、结果一致性检查、断流收口和导出门控。
- [tests/test_ai_formats.py](tests/test_ai_formats.py#L1-L160)、[tests/test_ai.py](tests/test_ai.py#L85-L300)、[tests/test_gui.py](tests/test_gui.py#L141-L800)：三协议解析、转义、流式预览、完成原因、缺项、内部换行、旧事件、断流和导出门控回归。

验收结果：P0-07 的两个 strict xfail 已转为普通测试；三协议与流式预览回归后完整测试为 `139 passed`，P0 提案保持清零。`compileall`、`node --check`、`pip check` 和 `git diff --check` 同时通过。

---
