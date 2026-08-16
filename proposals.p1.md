# P1 — 重要缺陷：核心流程、可靠性与规格实现缺口

> 最后审计日期: 2026-08-17
> 最后编号：P1-15

---

## ~~🟡 P1-01. Provider 失败、取消和部分结果会被标记为翻译成功~~ ✅ 已修复

> 严重程度: 🟡 中高
> 影响范围: Google/OpenAI Provider、GUI 停止与重试、导出门控
> 评级理由: 翻译完全失败时仍可能被界面计入成功、生成部分结果并显示 100% 完成

### 问题描述

基础批量接口在单条失败时直接返回原文；OpenAI 编排把失败包装成“不确定术语”；Google 流式失败同样保留原文但不提供机器可读 `error`。GUI 只按 `data.error` 识别失败，因此 Google 失败不会进入重试列表。用户停止翻译后，前端持久化部分结果并把 `translated` 设为真，服务端也没有真正取消正在执行的 Provider 请求。

审查使用始终失败的 Google Provider 复现：SSE 仍发送无 error 的结果、100% progress 和 end，界面会把保留原文计入完成。

### 位置

- [office_translate/ai/provider.py](office_translate/ai/provider.py#L40-L84)：批量失败以原文回退，状态信息不足。
- [office_translate/ai/provider.py](office_translate/ai/provider.py#L435-L455)：Google 流式失败没有 error 字段。
- [office_translate/ai/translator.py](office_translate/ai/translator.py#L188-L212)：失败被转换为普通结果。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L881-L1030)：停止、完成和重试共用不可靠的布尔状态。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L1084-L1123)：只通过 SSE error 识别失败。
- [office_translate/gui/server.py](office_translate/gui/server.py#L620-L674)：流式生成器没有协作取消与最终失败摘要。

### 影响

用户可能把未翻译原文或部分结果当作完整输出交付；GUI 的停止按钮仍可能产生费用，并且失败行无法可靠批量重试。

### 推荐修复方案

统一结果模型为 `succeeded/failed/cancelled/partial`，失败回退原文只能作为显示值，不能算成功。GUI 的后端操作必须支持取消标记和最终 summary，只有所有 ID 成功或经用户明确接受后才能进入 ready。增加全站失败、部分失败、停止、断连、重试和部分结果确认测试。CLI 路径不再单独修补，按 P1-11 移除。

### 最终修复情况

已统一同步、重试和流式路径的结果状态为 `succeeded`、`failed`、`cancelled`，部分完成通过 `partial` summary 表达。失败时可以保留原文作为界面显示值，但不会计入成功，也不会进入可导出状态。Provider 诊断包含脱敏错误编号与可重试标记。

服务端为每个作业维护操作状态，支持取消端点、客户端断开后的取消摘要和有界并发；所有结果按原始 item ID 汇总，summary 对成功、失败、取消 ID 集合做守恒校验。前端只有完整成功且 revision 一致时才允许保存和导出，并明确提示已发出的供应商请求可能仍产生费用。

相关回归覆盖全失败、部分失败、取消、断开、重试、进度守恒和导出门控，主要位于 [tests/test_ai.py](tests/test_ai.py)、[tests/test_gui.py](tests/test_gui.py) 和 [tests/e2e/test_gui_workflow.py](tests/e2e/test_gui_workflow.py)。

---

## ~~🟡 P1-15. 模型输出格式选择与实际请求不一致，流式界面把原始 JSON 重复显示在每一行~~ ✅ 已修复

> 严重程度: 🟡 中高
> 影响范围: 模型级输出格式设置、SSE 流式渲染、逐条对照预览、协议解析
> 评级理由: 界面选项承诺 XML，后端却强制 JSON；流式期间块内每一行显示同一段原始协议正文，办公用户无法辨认正在翻译哪些内容

### 问题描述

“输出格式”下拉实际绑定的是 `response_format`（`json_schema` / `json_object` / `none`），其中“无（XML 标签）”选项并没有实现 XML 协议：选择后后端仍按严格 JSON `items[]` 提示词与解析器处理，用户看到 JSON 流式内容，与界面选择完全不符。

SSE 把 Provider 的原始 `content` delta 原样转发给前端；前端把整个块的增量文本保存在 `translateBuffer[block_id]`，再把该值赋给块内每一行（`translateRows` 中 `buffer` 字段由块内所有行共享）。因此流式过程中块内每一条待翻译文本下方都显示同一段正在累积的原始 JSON，而不是逐条出现的译文。

### 位置

- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L165-L170)：response_format 下拉含“无（XML 标签）”伪 XML 选项。
- [office_translate/ai/provider.py](office_translate/ai/provider.py#L193-L220)：后端忽略 XML 选择，始终构造严格 JSON 请求。
- [office_translate/gui/server.py](office_translate/gui/server.py#L704-L715)：SSE 原样转发 provider 的原始 content delta。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L121-L148)：块内所有行共享同一 buffer 渲染字段。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L1437-L1440)：前端把原始增量累积进 translateBuffer。
- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L481-L486)：把 buffer 原文直接渲染到每一行。

### 影响

用户选择 XML 或文本格式时实际仍走 JSON，配置不可信；流式翻译过程中界面显示无意义的协议正文，且无法逐个看到已翻译片段，核心工作流体验严重受损。

### 推荐修复方案

新增模型级 `output_format`（`text` / `json` / `xml`，默认 `xml`），替代误导性的 `response_format` 下拉。三种协议分别构建提示词并严格解析：JSON 沿用 ID-bearing `items[]`；XML 使用带 `id` 属性的 `<items><item>` 结构；文本模式每条译文一行，行内除空格外的空白字符统一使用 `\n`、`\t` 等字面转义，行数必须与输入一致，否则整块失败。JSON 模式在模型支持时自动使用 `json_object`，不支持则退回普通模式；文本与 XML 模式不传 `response_format`。

SSE 新增 `item_preview` 事件：服务端从累积的协议正文中增量提取已完成的翻译片段（JSON 提取完整 item、XML 提取完整 `</item>`、文本提取完整行并反转义），前端逐条上屏；不再转发原始 `content` 事件，界面不显示协议正文。最终仍以整块校验后的 `item_succeeded` / `item_failed` 与守恒 summary 为准。

### 最终修复情况

已新增模型级 `output_format`（`text` / `json` / `xml`，默认 `xml`），UI“模型输出格式”下拉只保留这三个真实协议选项。传输层强化改为独立的模型级 `response_format` 选项（`auto` / `none` / `json_object` / `json_schema`，默认 `none`，仅 JSON 协议生效）：普通 JSON 默认不发送强化参数，以获得更好的流式兼容性；`auto`、`json_object` 和 `json_schema` 仅在用户明确选择时发送，部分供应商可能整包返回。与文本/XML 协议组合的配置会明确拒绝。

三种协议均严格校验：JSON 沿用 ID-bearing `items[]`；XML 使用 `<items><item id="..."><translation>…</translation><uncertain_terms>…</uncertain_terms></item></items>`，拒绝无 ID、未知标签/属性、重复/缺失/未知 ID 与畸形 XML；文本模式每条译文一行、按输入顺序对应，行内除空格外的空白字符使用 `\n`、`\t`、`\r`、`\\` 等字面转义，行数必须与输入完全一致，否则整块失败。

SSE 新增 `item_preview` 事件：服务端从累积协议正文中增量提取已完成的翻译片段（JSON 提取完整 item、XML 提取完整 `</item>`、文本提取完整行并反转义），前端逐条上屏；不再转发原始 `content` 事件，界面不显示协议正文。真实模型回归发现 JSON 输入和输出都使用相近的 `text` 字段会诱导模型返回非法 `items[].text`，导致预览为零并在最终校验失败；输入现改为 `source_items[].source_text`，提示明确要求唯一输出字段 `items[].translation`。正式结果仍以整块校验后的 `item_succeeded` / `item_failed` 与守恒 summary 为准。主要实现见 [office_translate/ai/contracts.py](office_translate/ai/contracts.py#L220-L460)、[office_translate/ai/streaming.py](office_translate/ai/streaming.py#L1-L180)、[office_translate/ai/translator.py](office_translate/ai/translator.py)、[office_translate/gui/server.py](office_translate/gui/server.py#L640-L760) 与 [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L115-L150)。

收尾补充：整块校验失败时不再把已预览条目全部标失败——已完整解析且结构合法的条目保留为 `succeeded`，仅缺失/损坏条目标记 `failed`，summary 为 partial 且不可导出；XML 解析器会修复未转义的裸 `&`（结构校验不放松）。翻译中预览片段出现即同步推动前端进度显示；翻译列表与思考面板支持接近底部自动跟随、用户上滚后解除。

---

## ~~🟡 P1-02. GUI 内部存在多个 AI 设置真相源，部分设置显示可用但运行时被忽略~~ ✅ 已修复

> 严重程度: 🟡 中高
> 影响范围: 模型参数、thinking、response format、术语库、并发、镜像站、供应商选择
> 评级理由: 用户保存的配置不能可信决定实际请求，故障定位和结果复现均受到影响

### 问题描述

GUI 主流程调用流式端点，虽然请求携带 concurrency，服务端从未读取该字段，所有块仍串行执行。同步重试、流式翻译和设置页也没有通过同一套 effective configuration 构造请求。

前端挂载时并发调用 `/api/settings` 和始终返回内置默认值的 `/api/mirrors`，两者竞态覆盖 `mirrorsText`；删除当前供应商后也没有同步持久化的 active provider。最终表现为界面显示值、配置文件和实际请求三者不一致。

### 位置

- [office_translate/ai/provider.py](office_translate/ai/provider.py#L99-L149)：真实请求参数入口与 GUI 设置解析分离。
- [office_translate/gui/server.py](office_translate/gui/server.py#L418-L420)：镜像接口固定返回默认列表。
- [office_translate/gui/server.py](office_translate/gui/server.py#L568-L632)：流式端点不读取 concurrency，按块串行运行。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L364-L386)：加载与保存持久化设置。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L648-L705)：供应商删除与镜像默认值覆盖。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L909-L925)：前端发送未被服务端采用的并发数。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L1212-L1216)：两个设置来源并发加载。

### 影响

用户认为已启用的 thinking、输出格式、术语和并发可能没有生效；自定义镜像可能被默认值覆盖；主翻译与失败重试也可能使用不同参数。

### 推荐修复方案

建立唯一的 `ProviderConfig` 解析与校验服务，让 GUI 的同步重试与流式翻译全部复用。`/api/settings` 成为设置唯一真相源，区分 defaults 与 effective settings；保存前校验 active provider/model 引用。明确实现有界并发及顺序汇总，或在未实现前移除无效控件和文档承诺。加入请求快照一致性、重载、删除当前供应商、自定义镜像和并发峰值测试。

### 最终修复情况

已由 `SettingsStore` 和经校验的 `ProviderConfig` 快照统一 defaults、saved、effective 配置。同步翻译、流式翻译、失败重试和连接测试使用同一快照；并发限制、模型上下文、输出协议、thinking 和供应商镜像均从该快照构造请求。保存前会校验 active provider/model 引用，删除当前配置后不会写入无效设置。

API Key 只从后端设置存储解析，浏览器只提交 provider/model ID 和非敏感配置。请求体中的密钥覆盖会被忽略，设置响应只提供掩码和已配置标记。新增设置一致性、删除当前 provider/model、自定义参数、密钥边界和并发峰值测试，主要位于 [office_translate/settings.py](office_translate/settings.py)、[office_translate/ai/provider.py](office_translate/ai/provider.py) 和 [tests/test_gui.py](tests/test_gui.py)。

---

## ~~🟡 P1-03. 分块预算可能超过模型上下文，超长单条文本永远不拆分~~ ✅ 已修复

> 严重程度: 🟡 中高
> 影响范围: LLM 上下文、Google 请求上限、长单元格、重试
> 评级理由: 合法长文本会稳定失败或被回退原文，模型费用与上下文配置也不可预测

### 问题描述

代码实现了 token 估算器，却在实际分块时用固定“两字符一个 token”反推字符数。中文更接近一字符一个 token，且预算没有扣除 system prompt、术语库和输出 token。审查复现：8,000-token 上下文下，12,000 个中文字符仍保留为一个块，而本地估算已达 12,001 token。

任何超过 max_chars 的单条记录都被原样单独成块，不再拆分。Excel 单元格可远大于 Google 的 4,500 字符阈值，因此这种输入必然交给供应商后失败。

### 位置

- [office_translate/ai/chunking.py](office_translate/ai/chunking.py#L11-L18)：token 估算器未用于真实预算。
- [office_translate/ai/chunking.py](office_translate/ai/chunking.py#L19-L50)：超长单条记录直接越过上限。
- [office_translate/ai/chunking.py](office_translate/ai/chunking.py#L53-L81)：字符反推忽略语种、prompt、术语和输出预算。
- [office_translate/ai/provider.py](office_translate/ai/provider.py#L410-L426)：Google 直接用 GET 发送整个文本。

### 影响

中文长文本、术语表较大或输出较长时会触发上下文错误、URL/请求限制或供应商拒绝；当前失败回退机制又可能把原文伪装成成功结果。

### 推荐修复方案

用目标模型 tokenizer 或保守的多语种估算，预算中显式扣除 system、glossary、schema 和 max output。对超长单条文本按句段切分，以稳定 item ID 和 segment offset 重组，并验证重组完整性；Google 改用受支持的 POST，并按实际字节/字符限制拆分。增加中英混合、CJK、超长单元格、超大术语库和输出膨胀测试。

### 最终修复情况

分块现在使用实际 system prompt、术语表、协议 schema、提示开销和最大输出预算计算上下文余量，并采用保守的混合语言/CJK 估算。超过单块预算的 item 会按稳定 source ID、segment offset 和 segment index 拆分，供应商完成后校验 offset 并折叠回原始 item，不向 GUI 暴露内部 segment ID。

Google 请求已改为 POST，并复用同一上下文安全分块策略。同步、流式和重试路径都覆盖长单元格、大术语表、CJK、混合语言、结果重组和 segment 失败/取消折叠测试，主要位于 [office_translate/ai/chunking.py](office_translate/ai/chunking.py)、[office_translate/ai/translator.py](office_translate/ai/translator.py) 和 [tests/test_chunking.py](tests/test_chunking.py)。

---

## ~~🟡 P1-04. XLSX 富文本 run 在回填后被扁平化，无法满足“完全保留样式”~~ ✅ 已修复

> 严重程度: 🟡 中高
> 影响范围: Excel 富文本单元格、样式保真、README 约定
> 评级理由: 已验证的格式损失直接违反核心产品承诺

### 问题描述

工作簿加载没有启用 rich text，回填又把整个 cell value 替换为普通字符串。审查构造带加粗红色 run 的 `CellRichText`，经过当前流程后变成纯字符串，局部格式全部丢失。普通单元格样式、公式、数值、超链接、批注、合并单元格和重复文本 fan-out 在针对性样例中可以保留，但图表、图片、pivot、slicer、外部链接、保护和签名尚未得到系统验证，因此“完全保留所有样式”目前缺乏成立边界。

### 位置

- [README.md](README.md#L1-L12)：宣称完全保留原文档所有样式。
- [README.md](README.md#L104-L111)：把样式保留列为关键约定。
- [office_translate/formats/xlsx/extractor.py](office_translate/formats/xlsx/extractor.py#L67-L93)：默认方式读取工作簿和文本。
- [office_translate/formats/xlsx/applier.py](office_translate/formats/xlsx/applier.py#L59-L91)：用普通字符串覆盖整个单元格值。

### 影响

含局部颜色、粗体、字号或多 run 的单元格会在翻译后失去内部格式。复杂企业工作簿还可能存在未被当前测试发现的 OOXML 特性损失。

### 推荐修复方案

先定义可验证的 XLSX 保真矩阵。加载时启用富文本支持，并确定翻译改变长度后 run 的映射策略：默认可采用保留首 run、按源片段映射或要求用户选择扁平化，但必须明确提示。对无法由 openpyxl 可靠往返的对象，评估直接修改 OOXML 文本节点或显式声明不支持。增加富文本、多种对象、外链、保护、打印设置和签名样例的文件级回归比较。

### 最终修复情况

已建立 XLSX 前置校验和可验证的保真边界。提取阶段启用富文本和链接保留检查，并报告富文本 run、外链、保护和未验证 OOXML 对象。多 run 富文本默认使用 `flatten` 翻译并明确说明局部 run 格式会丢失；用户也可选择 `preserve_original`，保留受影响单元格原文与局部格式。

输出阶段在写盘前检查所有目标单元格，先分别生成并验证“仅译文”和“原文-译文对照”候选文件，再以原子方式发布两份输出；任何一份失败都不会让半成品可见。普通样式、公式、合并单元格、超链接、批注、冻结窗格、数据验证和图表均有文件级回归，详细证据位于 [office_translate/formats/xlsx/extractor.py](office_translate/formats/xlsx/extractor.py)、[office_translate/formats/xlsx/applier.py](office_translate/formats/xlsx/applier.py) 和 [tests/test_workbook_fidelity.py](tests/test_workbook_fidelity.py)。

浏览器 GUI 已补齐富文本处理闭环。默认策略为 `flatten`，生成完整译文并明确提示局部 run 格式会丢失；用户可以在策略对话框中选择 `preserve_original`，跳过受影响单元格并保留其原文格式。服务端只接受这两种策略，成功后才原子发布两份输出。`tests/e2e/test_gui_workflow.py::test_gui_rich_text_policy_defaults_to_flatten_and_can_preserve` 覆盖默认扁平化、策略选择和重试导出。

---

## ~~🟡 P1-05. 审核决策未持久化，未处理项仍可导出且批量替换缺少作用范围~~ ✅ 已修复

> 严重程度: 🟡 中高
> 影响范围: 不确定术语审核、任务恢复、导出门控、译文替换
> 评级理由: 面向办公用户的核心审核步骤无法可靠完成，并可能在用户不知情时误改译文

### 问题描述

接受和忽略操作只删除内存中的 `pendingTerms`，没有把决策写回 `ai_output.json`；重载后会从原始 uncertain terms 再次生成全部项目。导出门控也不要求待审核项清零。接受术语后的“应用到当前译文”使用全局 `split().join()`，没有词边界、大小写、上下文或差异预览。

### 位置

- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L747-L759)：恢复时重新生成全部不确定项。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L1130-L1194)：审核状态不持久化，并执行无上下文字符串替换。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L241-L247)：导出门控不检查未审核项。
- [office_translate/gui/server.py](office_translate/gui/server.py#L356-L395)：AI 输出持久化结构没有审核决策字段。

### 影响

用户刷新后需重复审核，未审核术语可以直接进入输出；自动替换可能改变不相关子串。界面虽然提供独立审核步骤，但任务状态无法证明该步骤已经完成。

### 推荐修复方案

为每个不确定项保存稳定 ID、来源行、`pending/accepted/edited/ignored` 状态、最终译法、类别和修订号。导出要求所有项有明确决策，或记录一次“全部忽略并继续”。替换前展示逐行差异，只作用于用户确认的行和匹配范围；无法安全定位时要求逐行确认。增加接受、编辑、忽略、刷新恢复、批量操作和导出门控测试。

### 最终修复情况

审核记录现在由后端基于稳定 `review_id` 生成并持久化，记录 `pending`、`accepted`、`edited`、`ignored` 决策、最终译法、revision 和适用行号。GET/PUT 审核接口校验 source/translation revision，过期记录会被拒绝；刷新后不会重新生成或丢失已处理项。

术语替换只作用于审核卡片记录的 `row_ids`，并同时约束 candidate、term、apply_to_text 和 final target。存在 pending review、失败/取消 item 或不完整 summary 时导出保持禁用。相关 API、作用域和导出门控测试位于 [office_translate/artifacts.py](office_translate/artifacts.py)、[office_translate/jobs.py](office_translate/jobs.py)、[office_translate/gui/server.py](office_translate/gui/server.py) 和 [tests/test_gui.py](tests/test_gui.py)。

行作用域已经完整交给用户控制。审核卡片显示每行“当前/应用后”差异，并通过 `selected_row_ids` 逐行勾选；服务端要求该字段存在、无重复且是 `row_ids` 的子集，只修改最终选中的行。缺失字段、重复字段和越界字段都会被拒绝，不保留旧协议兼容猜测。API 与浏览器回归覆盖未选行保持不变、持久化和导出门控。

---

## ~~🟡 P1-06. 手动翻译预览被 Vue 同名属性覆盖，空译文可无确认清空单元格~~ ✅ 已修复

> 严重程度: 🟡 中高
> 影响范围: 无 API 手动翻译、逐行校对、导出正确性
> 评级理由: 备用核心工作流的预览失效，且等行数空白可直接删除原文内容

### 问题描述

`manualMappings` 同时在 `data()` 中定义为空数组，又在 computed 中定义映射。Vue Options API 会报告属性冲突，模板无法可靠获得计算结果，生产页面的“对照预览”可能一直为空。

行数校验只在总行数不足时收集空行。两条原文配 `"译文\n"` 时拆分后恰好两行，保存按钮可用，第二条空译文随后被合法回填为空单元格。

### 位置

- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L15-L21)：data 中定义 `manualMappings`。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L85-L105)：computed 再次定义同名属性，空行校验不完整。
- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L364-L398)：预览、逐行编辑和保存依赖该映射。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L824-L870)：允许保存等行数的空译文。
- [office_translate/formats/xlsx/applier.py](office_translate/formats/xlsx/applier.py#L123-L149)：空字符串会正式覆盖原单元格。

### 影响

用户无法按界面承诺逐行核对；合法操作可能无警告清空部分输出单元格，直到打开 Excel 后才发现。

### 推荐修复方案

删除同名 data 字段，为 computed 映射使用唯一名称。分别校验总行数、空译文、额外行和未保存编辑；默认禁止空译文，确需清空时要求逐行显式确认并记录该决策。增加真实 Vue/DOM 测试覆盖粘贴、预览、逐行修改、尾随换行、空译文和导出。

### 最终修复情况

手动翻译改为结构化 item 状态，移除了同名 data/computed 属性冲突，逐行预览、编辑、保存和刷新恢复使用同一数据源。空译文默认不能直接导出，用户必须逐项确认清空并持久化该决定；服务端保存前会取得 canonical `review_id`，不会使用前端猜测 ID 绕过审核接口。

保存成功后 revision 和 `translated`/`reviewReady` 状态会重新计算，刷新不会以旧的 `complete=false` 覆盖最终状态。尾随换行、等行数空译文、空译文确认、保存失败重试和实际浏览器手工流程由 [office_translate/gui/web/app.js](office_translate/gui/web/app.js)、[tests/test_gui.py](tests/test_gui.py) 与 [tests/e2e/test_gui_workflow.py](tests/e2e/test_gui_workflow.py) 覆盖。

---

## ~~🟡 P1-07. 文件导入缺少前置校验与冲突处理，错误文件会先创建无效任务~~ ✅ 已修复

> 严重程度: 🟡 中高
> 影响范围: GUI 文件选择、上传暂存、新建任务、格式能力检查、错误恢复
> 评级理由: 办公用户可以在界面承诺下创建必然失败的任务，或因同名文件覆盖而选错输入

### 问题描述

前端允许选择 `.xls` 并明确提示会自动转换。GUI 后端实际只复制文件，格式注册表又只支持 `.xlsx`。审查复现 `.xls` 创建返回 200，直到提取才返回 400“不支持 .xls”。假扩展名或损坏的 `.xlsx` 也会先上传并创建任务，错误同样延迟到后续步骤。

上传使用一次性 `file.read()`，并以原始 basename 直接写入公共暂存目录；两个同名文件会静默后写覆盖先写。任务名只排除路径分隔符，`a#b` 等名称创建后会破坏前端 URL；未支持格式的错误信息还会把 `.xlsx` 拆成 `., l, s, x`。这些不是需要 SaaS 级攻击防护的问题，而是小白用户在普通选错文件、重名和命名操作下会直接遇到的导入失败。

### 位置

- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L267-L280)：界面承诺 `.xls` 自动转换。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L336-L363)：文件选择接受 `.xls`。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L707-L721)：任务创建继续接受 `.xls`。
- [office_translate/gui/server.py](office_translate/gui/server.py#L270-L309)：上传整文件读入内存、同名覆盖，创建与提取之间没有格式预检。
- [office_translate/config.py](office_translate/config.py#L60-L66)：任务名未限制会破坏 URL 的保留字符。
- [office_translate/base.py](office_translate/base.py#L83-L92)：未支持格式提示错误地逐字符展开扩展名。
- [tests/test_gui.py](tests/test_gui.py#L40-L48)：假 `.xlsx` 被固定为上传成功行为。

### 影响

用户会得到看似创建成功、实际无法继续的任务，并留下无效目录；同名上传可能让任务引用另一份文件；文件较大时页面等待和内存占用也会明显增加。当前错误出现得过晚，且没有说明如何恢复。

### 推荐修复方案

前端和后端当前只接受 `.xlsx`；用户选择 `.xls` 时，在创建任务前说明“请用 Excel/WPS 另存为 `.xlsx`”，并给出简短图形化引导，不再接入将被 P1-11 移除的 CLI/PowerShell 转换链路。上传采用分块写入和唯一暂存标识，在创建任务前校验扩展名、OOXML ZIP 与工作簿可打开；同名文件不静默覆盖。任务名应限制为界面和 URL 均可安全显示的字符，所有失败都使用面向办公用户的原因、处理方法和重试入口。增加 `.xls`、假/损坏 `.xlsx`、同名、大文件、异常任务名和拒绝后无残留测试。

### 最终修复情况

浏览器上传使用唯一暂存名和保留扩展名，创建任务前执行扩展名、OOXML ZIP 和工作簿可打开性预检，失败时不发布任务目录并清理暂存文件。同名上传不会相互覆盖；任务名和内部相对路径经过安全校验。`.xls` 在前端和后端均明确拒绝，并提示在 Excel/WPS 中另存为 `.xlsx`，不再承诺自动转换。

错误响应包含办公用户可执行的处理方法，覆盖假扩展名、损坏文件、`.xls`、重名文件和非法任务名。相关实现位于 [office_translate/gui/server.py](office_translate/gui/server.py)、[office_translate/config.py](office_translate/config.py)、[office_translate/gui/web/index.html](office_translate/gui/web/index.html) 和 [office_translate/gui/web/app.js](office_translate/gui/web/app.js)，测试覆盖位于 [tests/test_gui.py](tests/test_gui.py) 与 [tests/e2e/test_gui_workflow.py](tests/e2e/test_gui_workflow.py)。

---

## ~~🟡 P1-09. 设置、术语库和任务产物缺少锁与原子提交，存在丢更新和半文件~~ ✅ 已修复

> 严重程度: 🟡 中高
> 影响范围: GUI 设置、术语库、source/map、AI 输出、译文、XLSX 输出
> 评级理由: FastAPI 并发请求和写盘中断可丢失用户数据或留下看似存在但内容不完整的产物

### 问题描述

设置和术语采用“读取整个 JSON → 修改 → 直接覆盖”的方式，没有进程内锁或原子替换。即使产品只在本机运行，FastAPI 的同步路由仍会在线程池中并发执行，前端自动保存也会产生重叠请求。审查通过屏障让两个术语请求同时读取旧快照，两次均返回 200，最终只保留一个条目。

source.txt 与 map.json 分两次写最终路径；translated.txt、ai_output.json 和输出工作簿也直接覆盖最终文件。apply 先把原文件复制到最终路径，再修改保存；中途异常时可能留下未翻译副本，而阶段判断仅看文件是否存在。

### 位置

- [office_translate/gui/server.py](office_translate/gui/server.py#L131-L198)：设置 read-modify-write 和直接覆盖。
- [office_translate/gui/server.py](office_translate/gui/server.py#L301-L414)：任务产物直接写最终路径。
- [office_translate/gui/server.py](office_translate/gui/server.py#L684-L757)：术语 CRUD 无锁 read-modify-write。
- [office_translate/glossary.py](office_translate/glossary.py#L33-L49)：术语 JSON 非原子保存。
- [office_translate/formats/xlsx/extractor.py](office_translate/formats/xlsx/extractor.py#L95-L107)：TXT 与 JSON 分别提交。
- [office_translate/formats/xlsx/applier.py](office_translate/formats/xlsx/applier.py#L50-L91)：最终输出先出现，再进行可能失败的回填。

### 影响

并发编辑可丢失术语或设置；读取者可能看到截断 JSON；提取、取消、删除和 apply 并发时可能留下混合版本、半成品或错误阶段。

### 推荐修复方案

按单进程本地应用设计：为设置、术语库和每个 job 建立进程内锁，将同一资源的保存、提取、回填和删除串行化。JSON/TXT/XLSX 先写同目录临时文件，完成基本结构校验后用 `os.replace()` 提交；source/map 只在两者都成功后更新任务阶段，两份输出也应全部生成成功后再对用户可见。不建设分布式锁、ETag 或多实例一致性协议。增加重叠自动保存、并发术语编辑、运行中删除、模拟保存异常和临时文件清理测试。

### 最终修复情况

阶段 1 已完成任务产物部分：新增每个 job 的进程内重入锁、同目录临时文件、`fsync`、`os.replace()`、版本化 JSON/XLSX 和 manifest 最后提交；提取、保存、回填、删除不会并发修改同一任务，双输出发布失败会保留上一组完整输出。对应实现见 [office_translate/storage.py](office_translate/storage.py#L18-L109) 与 [office_translate/jobs.py](office_translate/jobs.py#L146-L529)。

阶段 3 已补齐设置与术语库：`SettingsStore.update()` 和 `GlossaryStore.update()` 在同一进程内锁住完整 read-modify-write 事务，使用 JSON 校验、同目录临时文件、flush/fsync、原子替换和失败清理。GUI 路由已全部切换到事务 API；并发新增、校验失败和替换失败回归通过。当前版本不保留旧 CLI/API 兼容路径。

---

## ~~🟡 P1-10. 本地 GUI 的同源边界与离线资源不符合桌面分发方式~~ ✅ 已修复

> 严重程度: 🟡 中高
> 影响范围: 本地 WebUI、浏览器开发模式、轻量 WebView、API Key、前端资源
> 评级理由: 不需要 SaaS 鉴权体系，但当前通配 CORS、明文密钥往返和远程运行时依赖仍不适合分发给办公用户

### 原始表述

> 「浏览器打开是一种快速开发的考虑，WebView是可能会做的一块，但不会很重要，只是一个很简单的壳。」

### 问题描述

产品是单机 GUI，不存在多租户、远程账号或 SaaS 权限模型，因此原 P0-01 提出的完整会话认证方案过重。但浏览器开发模式下，服务仍开启任意来源 CORS；设置接口把完整 API Key 返回前端；页面又从未固定版本的远程 CDN 加载 Vue。远程脚本在本地页面权限域中执行，断网时界面也无法启动。

这些问题应按“本地桌面应用的同源与离线边界”处理，而不是建设账号、OAuth、RBAC 或多租户鉴权。

### 位置

- [office_translate/gui/server.py](office_translate/gui/server.py#L117-L129)：本地服务启用通配 CORS。
- [office_translate/gui/server.py](office_translate/gui/server.py#L131-L200)：完整 API Key 在设置接口中读写。
- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L1-L8)：从可变 CDN 加载 Vue。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L364-L405)：密钥进入浏览器状态并用于连接测试。
- [office_translate/gui/launcher.py](office_translate/gui/launcher.py#L41-L80)：浏览器与 WebView 共用回环服务。

### 影响

开发时打开恶意网页、CDN/代理异常或远程资源不可达，都可能影响本地应用；密钥在浏览器状态中扩大了不必要的暴露面。风险低于互联网 SaaS，但正式分发前仍应处理。

### 推荐修复方案

保持简单的单机模型：服务固定监听 `127.0.0.1`；删除通配 CORS并只接受同源；Vue 和全部运行时资源随应用本地分发；设置读取只返回密钥掩码和是否已配置，翻译请求按 provider ID 由后端取密钥。若增加 WebView，只需禁用外部导航并沿用同源页面。浏览器模式保留为开发和快速启动入口，不建设用户账号、OAuth、RBAC、多租户或复杂会话体系。增加断网启动、恶意 Origin、密钥掩码和 WebView 外部导航测试。

### 最终修复情况

阶段 3 已完成本地分发基础：启动器拒绝非回环地址，服务删除通配 CORS，Vue 3.5.18 随应用本地分发，GUI 设置 GET 只返回 `api_key_masked` 与 `api_key_configured`，翻译和供应商测试按 provider ID 由后端解析密钥。新增离线静态资源、恶意 Origin、回环绑定和密钥不进入前端状态的回归。

按已确认的产品边界关闭本提案：当前正式入口是本地浏览器 GUI，WebView 只是复用同一页面的简单外壳，不建设独立业务层或复杂桌面打包能力。回环绑定、同源静态资源、离线 Vue、无通配 CORS、后端密钥持有和密钥掩码均已完成，并由 [tests/test_launcher.py](tests/test_launcher.py)、[tests/test_gui.py](tests/test_gui.py) 和 [tests/test_frontend_static.py](tests/test_frontend_static.py) 覆盖。WebView 专属外部导航策略和正式打包不属于当前产品的阻塞验收项，保留为未来分发工作。

---

## ~~🟡 P1-11. 产品应收缩为 GUI-only，移除无维护承诺的 CLI、Python 公共 API 和 PowerShell 转换链路~~ ✅ 已修复

> 严重程度: 🟡 中高
> 影响范围: 产品入口、CLI、Python API、`.xls` 转换、README、测试范围
> 评级理由: 当前仓库公开并承诺了不准备维护的产品面，继续修补会分散 GUI 质量投入并保留额外风险

### 原始表述

> 「CLI和Python API库不考虑维护，可移除。该软件面向办公小白，着力设计GUI。」

### 问题描述

README、`python -m office_translate` 和顶层包仍把 init/extract/apply/auto/list 以及 Python `extract()` / `apply()` 当成正式能力。原 P0-03 的 PowerShell 注入与同名覆盖、原 P0-04 的公共 API 路径别名破坏，都主要来自这些非目标入口。

既然产品面已明确为 GUI，继续为 CLI/库 API 增加兼容校验和专属修复会形成双重工作流。更干净的方向是移除这些入口，只保留 GUI 内部所需的格式服务。`python -m office_translate gui` 可在缺少打包启动器时暂时作为开发入口，但不再被视为面向用户的 CLI 产品。

### 位置

- [README.md](README.md#L55-L103)：把 CLI 手动流程和 auto 作为正式使用方式。
- [README.md](README.md#L211-L229)：公开 Python 库调用方式。
- [office_translate/cli.py](office_translate/cli.py#L1-L311)：维护完整 CLI 工作流和危险的自定义输出参数。
- [office_translate/__init__.py](office_translate/__init__.py#L24-L73)：公开 extract/apply 库 API。
- [office_translate/win_convert.py](office_translate/win_convert.py#L23-L93)：仅为旧 CLI `.xls` 自动转换服务，并含路径插值与覆盖风险。
- [office_translate/formats/xlsx/extractor.py](office_translate/formats/xlsx/extractor.py#L63-L107)：公共调用可把输出指向输入。
- [office_translate/formats/xlsx/applier.py](office_translate/formats/xlsx/applier.py#L94-L149)：公共调用可让输入输出或两个输出路径冲突。

### 影响

办公用户会看到不需要理解的命令行和库概念；维护者必须同时保证多套状态、配置和错误语义；不被 GUI 触达的 PowerShell 与任意路径表面仍随软件分发。

### 推荐修复方案

删除 init/extract/apply/auto/list 子命令、顶层公共 extract/apply 包装器及 `win_convert.py`；GUI 后端直接依赖受控的内部格式服务，并由服务端生成和验证所有路径。暂时保留最小 GUI 启动入口，待桌面打包后改为应用可执行入口。同步删除 README 的 CLI/库教程和相关专属测试，不保留兼容 shim。`.xls` 在 GUI 中按 P1-07 明确拒绝并提供另存为 `.xlsx` 的小白引导。

### 最终修复情况

已删除文档处理 CLI、顶层 `extract()` / `apply()` 公共 API、PowerShell `.xls` 转换链路及其专属测试。`python -m office_translate` 现在直接启动本地 GUI，仅保留 GUI 启动参数，不再提供旧任务命令或兼容 shim。GUI 上传和建任务会拒绝 `.xls`，并提示用户在 Excel/WPS 中另存为 `.xlsx`。README 已改为 GUI-first，并移除 CLI、库调用和旧 TXT/map 工作流说明；内部测试改为验证结构化 artifact 服务。

---

## ~~🟡 P1-12. 超过 Excel 单元格上限的译文会被静默截断为 32,767 字符~~ ✅ 已修复

> 严重程度: 🟡 中高
> 影响范围: XLSX 回填、仅译文版、对照版、长文本
> 评级理由: 问题会造成真实数据截断，但只在接近 Excel 单元格上限的低频输入中触发，不应占用 P0

### 问题描述

Excel 单元格文本上限为 32,767 个字符。回填前没有检查译文或“原文 + 分隔符 + 译文”的最终长度。审查用 40,000 字符译文复现：apply 返回成功，重新打开输出后只剩 32,767 字符。对照版即使原文和译文单独都未超限，拼接后也可能触发截断。

### 位置

- [office_translate/formats/xlsx/applier.py](office_translate/formats/xlsx/applier.py#L72-L91)：直接给单元格赋值，没有长度预检。
- [office_translate/formats/xlsx/applier.py](office_translate/formats/xlsx/applier.py#L94-L149)：两种输出都在保存后直接报告成功。

### 影响

长段落、说明文本和对照版内容可能在用户不知情时丢失尾部。输出文件可以正常打开，因此截断很难在交付前发现。

### 推荐修复方案

生成工作簿前逐项计算两种模式的最终单元格长度。默认遇到超限应中止并给出任务 ID、工作表、单元格、原长度和超出量；不要自动截断。面向办公小白的 GUI 应提供直接定位和清晰处理建议。若未来需要长文本策略，再通过显式选项选择拆分到相邻单元格、批注或独立工作表。增加 32,766、32,767、32,768 字符以及双语拼接超限的回归测试。

### 最终修复情况

在生成两种 XLSX 输出前逐项检查最终单元格长度，严格允许不超过 32,767 个字符；32,768 及以上会返回工作表、坐标、长度、超出量和处理建议，不会自动截断。两份候选文件都通过完整性验证后才同时发布，超限或其他写盘失败不会留下可下载的半成品。边界覆盖位于 [office_translate/formats/xlsx/applier.py](office_translate/formats/xlsx/applier.py)、[tests/test_roundtrip.py](tests/test_roundtrip.py) 和 [tests/test_workbook_fidelity.py](tests/test_workbook_fidelity.py)。

---

## ~~🟡 P1-13. 桌面 GUI 缺少键盘与焦点语义，窄窗口下核心工作区会被压缩到不可用~~ ✅ 已修复

> 严重程度: 🟡 中高
> 影响范围: 键盘操作、焦点反馈、模态框、分屏与小尺寸桌面窗口
> 评级理由: GUI 是唯一正式产品入口，基础操作语义和常见桌面窗口适配直接决定办公用户能否顺利完成流程

### 原始表述

> 「UI/UX不佳、用户体验差不易上手」

### 问题描述

步骤、术语筛选项和审核行号使用可点击 div/span，没有原生 button、tab 顺序或键盘事件。模态框没有 dialog 语义、初始焦点、焦点约束与关闭后恢复；toast 没有 live region；部分 label 未和控件关联。CSS 还移除默认 outline，却没有统一的 `:focus-visible` 替代，键盘用户难以判断当前位置。

界面也没有明确的最小桌面窗口布局策略。五段步骤条禁止换行，翻译区使用固定高度和固定侧栏；在笔记本分屏、缩小的浏览器窗口或简单 WebView 壳中，主要内容会被挤压。手机端不是产品目标，因此不需要建立完整移动端响应式体系，但常见桌面窄窗口必须可用。

### 位置

- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L256-L262)：步骤条不是可聚焦的原生交互控件。
- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L475-L560)：术语筛选、审核跳转与标签语义不足。
- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L598-L625)：toast 与模态框缺少辅助技术和焦点语义。
- [office_translate/gui/web/style.css](office_translate/gui/web/style.css#L36-L59)：步骤条禁止换行。
- [office_translate/gui/web/style.css](office_translate/gui/web/style.css#L69-L93)：移除默认 outline，缺少 focus-visible 规范。
- [office_translate/gui/web/style.css](office_translate/gui/web/style.css#L144-L184)：工作区高度和侧栏宽度固定。

### 影响

仅使用键盘、需要清晰焦点反馈或使用屏幕放大的用户无法可靠完成部分导航、筛选和确认操作；普通用户在分屏或较小窗口中也可能看不到关键按钮、文本或审核上下文。

### 推荐修复方案

将可点击 div/span 改为原生 button/link，保留清晰的 `:focus-visible`，并补齐 label、当前步骤和禁用状态语义。模态框打开时把焦点移入，限制焦点在框内，支持 Escape，并在关闭后恢复到触发控件；持久错误消息和 toast 使用合适的 live region。定义受支持的最小桌面窗口宽度，在窄桌面窗口中允许步骤条滚动/收缩、侧栏折叠或上下排列，避免固定高度遮挡；不把手机布局列入验收范围。增加纯键盘回归、焦点顺序、模态框和若干桌面窗口尺寸截图测试。

### 最终修复情况

前端已使用原生 button/link、`focus-visible`、明确 label 和 live region；模态框具备初始焦点、Tab 约束、Escape 关闭和关闭后恢复触发焦点。翻译、思考、审核和错误状态不依赖单一颜色表达，核心工作区在 900×700、1024×768 桌面窗口保持可用，不额外承诺手机布局。

静态前端测试覆盖焦点语义；浏览器 E2E 使用连续真实 Tab 事件完成主流程，覆盖模态框初始焦点、Tab/Shift+Tab 约束、Escape 关闭、焦点恢复以及 900×700、1024×768、1280×800 三种桌面尺寸。另以临时浏览器截图完成三种尺寸的无横向溢出视觉检查。主要文件为 [office_translate/gui/web/index.html](office_translate/gui/web/index.html)、[office_translate/gui/web/app.js](office_translate/gui/web/app.js)、[office_translate/gui/web/style.css](office_translate/gui/web/style.css)、[tests/test_frontend_static.py](tests/test_frontend_static.py) 和 [tests/e2e/test_gui_workflow.py](tests/e2e/test_gui_workflow.py)。

---

## ~~🟡 P1-14. 关键加载与失败只显示短暂提示，用户无法判断状态、重试或恢复~~ ✅ 已修复

> 严重程度: 🟡 中高
> 影响范围: 任务、设置、术语库、任务恢复、SSE 翻译、导出与本地诊断
> 评级理由: 面向办公小白的 GUI 若把失败显示为空数据或三秒提示，会诱导用户继续在错误状态上操作并失去恢复路径

### 原始表述

> 「UI/UX不佳、用户体验差不易上手」

### 问题描述

任务、术语和设置没有独立的 idle/loading/success/empty/error 状态，启动时会先显示“暂无任务”，即使请求仍在进行。任务原文和 AI 输出恢复会吞掉异常，SSE JSON 解析失败也被无提示忽略。多数错误只显示三秒 toast，没有留在对应页面的错误说明、重试按钮或恢复建议。

后端多个核心路由把不同异常统一转换成 400，少数诊断使用 `print`，本地日志又固定为 warning。损坏文件、配置问题、磁盘写入失败、供应商失败与用户输入错误因此在界面上难以区分，用户也没有可复制给维护者的最小诊断信息。

### 位置

- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L4-L72)：关键资源缺少独立加载与错误状态。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L201-L211)：toast 固定短时消失。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L747-L780)：任务恢复异常被静默忽略。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L941-L954)：畸形 SSE 事件被直接丢弃。
- [office_translate/gui/server.py](office_translate/gui/server.py#L301-L414)：核心任务操作广泛把不同异常映射为 400。
- [office_translate/gui/server.py](office_translate/gui/server.py#L620-L680)：错位告警只输出到控制台，缺少可关联上下文。
- [office_translate/gui/launcher.py](office_translate/gui/launcher.py#L69-L80)：本地服务日志级别固定为 warning。

### 影响

请求失败会被误认为空数据，旧状态或半恢复状态仍可能继续参与后续操作；短暂提示消失后，办公用户不知道失败发生在哪一步、数据是否保存、能否重试，也很难提供足以定位问题的信息。

### 推荐修复方案

为任务、设置、术语和当前作业建立明确的 loading/empty/error/ready 状态；失败时在对应区域保留错误卡片，说明“发生了什么、数据是否已保存、下一步怎么做”，并提供就地重试或返回安全步骤。SSE 解析失败应终止本次操作并进入可恢复的失败状态。后端区分可预期的输入/文件/供应商错误与内部错误，并写入简单的本地滚动日志；界面提供“复制诊断信息”，只包含时间、作业、操作和错误编号，不暴露路径或密钥。不建设集中式日志平台。增加加载失败、损坏状态文件、断流、重试成功和提示持久性测试。

### 最终修复情况

阶段 3 的滚动日志基础已扩展为完整的持久错误恢复：任务、设置、术语库和作业均区分 loading/empty/error/ready；错误卡片保留在对应区域并提供重试或安全返回，严格 SSE 解析失败会终止当前操作并进入可恢复状态。前端诊断复制仅包含时间、任务、操作和错误编号，不包含路径、密钥或文档内容；服务端日志继续按工作区滚动并脱敏。

浏览器 E2E 已覆盖离线启动、任务创建、提取、手工翻译、空译文确认、审核 revision、导出、刷新恢复以及真实请求失败后的持久错误卡片和 Tab/Enter 重试；错误卡片在超过 3 秒 toast 生命周期后仍保持可见。严格 SSE 解析和结构化诊断另有 API/静态回归。实现与测试见 [office_translate/gui/web/app.js](office_translate/gui/web/app.js)、[office_translate/gui/server.py](office_translate/gui/server.py)、[tests/test_frontend_static.py](tests/test_frontend_static.py) 和 [tests/e2e/test_gui_workflow.py](tests/e2e/test_gui_workflow.py)。

---
