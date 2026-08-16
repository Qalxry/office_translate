# Docs Updates - 需要同步进项目文档的实现差异

> 最后审计日期: 2026-08-17
> 最后编号：DU-08

---

## ~~🟡 DU-01. README 缺少模型级设置、流式事件与 AI 输出恢复契约~~ ✅ 已同步

> 状态: ✅ 已同步
> 影响文档: README、配置文档、GUI API/架构文档
> 影响范围: 供应商、模型参数、SSE、AI 输出持久化

### 背景

实现已超过 README 中“供应商 + 模型列表”的简化描述：每个模型可配置上下文、温度、输出上限、top_p、top_k、thinking、reasoning effort、response format 和额外参数；还实现了 OpenRouter 元数据填充、供应商连接测试，以及严格的 ID-bearing SSE 与 revision-bound TranslationArtifact 恢复。

### 相关位置

- [README.md](README.md#L172-L210)：当前设置示例只有 models 数组和少量全局字段。
- [office_translate/gui/server.py](office_translate/gui/server.py#L45-L113)：实际默认模型配置结构。
- [office_translate/gui/server.py](office_translate/gui/server.py#L356-L395)：AI 输出持久化接口。
- [office_translate/gui/server.py](office_translate/gui/server.py#L422-L566)：OpenRouter、供应商测试和同步翻译接口。
- [office_translate/gui/server.py](office_translate/gui/server.py#L568-L674)：实际 SSE 事件生成。
- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L109-L208)：模型级设置界面。

### 当前文档描述

README 只说明 Base URL、API Key、模型列表、语言和并发，没有字段优先级、空值语义、模型删除记录、SSE 事件或恢复文件说明。

### 实际实现或建议描述

正式文档应说明 GUI 的有效配置模型、模型级参数覆盖顺序、thinking 与输出协议策略、AI 输出恢复文件和流式事件字段。P0-07、P1-15 以及阶段 4 已将模型内容协议固定为模型级 `output_format` 三选（`text` / `json` / `xml`，默认 `xml`），SSE 事件为 `meta`、`thinking`、`item_preview`、`item_succeeded`、`item_failed`、`progress`、`summary` 及导出门控；后续文档不得再描述旧 `response_format` 下拉、`done/end`、`content` 事件、标量 JSON 或换行拆项。阶段 4 已补齐 P1-01、P1-02 的失败状态、重试、容量和配置快照策略。

### 推荐同步方案

新增 `docs/gui-api.md` 或等价文档，列出设置 schema、参数优先级、REST endpoint、严格 SSE 事件、summary 守恒规则、错误码和恢复语义；README 只保留用户级摘要与链接。更新 JSON 示例，明确 `model_configs`、active model、removed models 和额外参数边界。

### 最终同步情况

已重写 README 的 GUI-first 设置说明，并新增 [docs/gui-api.md](docs/gui-api.md)，记录模型级配置、密钥掩码、结构化产物、summary 门控、错误诊断、失败/取消状态、分块预算和重试边界。

---

## ~~🟡 DU-07. 模型输出协议三格式与流式逐条预览需要同步到 README/GUI API 文档~~ ✅ 已同步

> 状态: ✅ 已同步
> 影响文档: README、GUI API/架构文档
> 影响范围: 模型配置 `output_format`、SSE 事件、文本转义、XML 协议

### 背景

P1-15 修复后，模型级“输出格式”从旧 `response_format` 下拉（`json_schema` / `json_object` / `none`，其中“无（XML 标签）”并未实现 XML）改为真实协议三选 `output_format`：`text` / `json` / `xml`，默认 `xml`。JSON 模式默认使用 `response_format=none` 以保证流式兼容性；`auto`、`json_object` 和 `json_schema` 仅在用户明确选择时发送，文本与 XML 模式不发送这类参数。SSE 新增 `item_preview` 事件，原始协议正文不再以 `content` 事件转发，前端逐条显示已解析片段而非协议正文。

### 相关位置

- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L165-L171)：模型输出格式下拉。
- [office_translate/ai/contracts.py](office_translate/ai/contracts.py#L220-L460)：三协议严格解析与文本转义。
- [office_translate/ai/streaming.py](office_translate/ai/streaming.py#L1-L180)：流式增量片段提取。
- [office_translate/ai/provider.py](office_translate/ai/provider.py#L120-L200)：output_format 与 json_object 协商。
- [office_translate/gui/server.py](office_translate/gui/server.py#L700-L760)：item_preview 生成。

### 当前文档描述

README 与 DU-01 目前只描述严格 JSON `items[]`，没有 `output_format`、XML 结构、文本转义规则或 `item_preview` 事件。

### 实际实现或建议描述

文档应列出：模型级 `output_format` 三选及默认值；JSON 的严格 `items[]`；XML 的 `<items><item id="..."><translation>…</translation><uncertain_terms>…</uncertain_terms></item></items>`；文本模式“每条译文一行、行内除空格外的空白字符使用 `\n`、`\t`、`\r`、`\\` 等字面转义、行数必须与输入一致”；SSE 的 `item_preview` 语义；旧 `content` 事件与旧 `response_format` 选项已移除，不提供兼容。

另外记录：整块校验失败时，已完整解析且结构合法的条目保留成功，缺失/损坏条目失败（summary partial 不可导出）；XML 会修复未转义的裸 `&`；翻译列表与思考面板在接近底部时自动跟随滚动，上滚解除；预览片段出现即推动前端进度显示。传输层强化是独立于 `output_format` 的模型级 `response_format`（auto/none/json_object/json_schema，仅 JSON 协议生效，默认 none）。JSON 请求使用 `source_items[].source_text`，输出严格使用 `items[].translation`，避免模型镜像输入字段导致预览和最终解析失败。

### 推荐同步方案

在建立 `docs/gui-api.md` 时一并写入三协议 schema、SSE 事件表与文本转义规则；README 的用户级说明只保留“模型输出格式：XML（默认）/ JSON / 文本”一句话。

### 最终同步情况

已在 README 和 [docs/gui-api.md](docs/gui-api.md) 同步 XML（默认）、JSON、文本三协议、模型级 response_format 边界、逐条 item_preview 语义、文本转义和部分失败不可导出规则；旧 content/标量 JSON/TXT 拆项流程不再作为文档能力。

---

## ~~🟡 DU-02. 浏览器上传流程与拆分后的前端资源结构未同步到 README 和 FP-02~~ ✅ 已同步

> 状态: ✅ 已同步
> 影响文档: README、架构文档、proposals.feat.md
> 影响范围: 文件选择、上传暂存目录、前端文件职责

### 背景

既有提案记录的是 tkinter `/api/pick_file`，当前实现改为浏览器原生文件选择后 multipart 上传到本地服务。这一方向对浏览器和 WebView 更统一，可以视为可接受的等价实现，但暂存位置和清理策略尚未定稿。前端也已拆分为 HTML、CSS、JS 三个文件，README 目录树仍只列 index.html。

### 相关位置

- [proposals.feat.md](proposals.feat.md#L190-L196)：仍声称实现 `/api/pick_file`。
- [office_translate/gui/server.py](office_translate/gui/server.py#L284-L299)：实际 multipart 上传到 `<config-root>/data/input/`。
- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L1-L8)：独立加载 style.css。
- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L628-L630)：独立加载 app.js。
- [README.md](README.md#L112-L151)：目录结构只列 index.html，并把输入目录描述为根 `input/`。
- [DESIGN.md](DESIGN.md#L127-L134)：已记录三个前端文件的职责。

### 当前文档描述

README 将原始输入放在根 `input/`，把前端概括为单一 index.html；FP-02 则描述不存在的原生文件选择 API。

### 实际实现或建议描述

浏览器选择文件后上传给本地服务，再由服务复制到任务工作区；当前暂存目录是 `data/input/`。`index.html` 负责结构，`app.js` 负责状态与交互，`style.css` 负责 Token 和组件样式。

### 推荐同步方案

先决定暂存目录正式采用根 `input/` 还是 `data/input/`，并定义同名冲突和清理策略；随后统一 README、FP-02 最终实现说明与架构文档。目录树列出三个静态文件并沿用 DESIGN.md 的职责描述。

### 最终同步情况

已确定浏览器原生文件选择 + multipart 上传为当前 GUI 流程；静态前端由 index.html/app.js/style.css 组成，Vue vendor 随应用分发。当前暂存目录为 config 根下的 data/input；阶段 5 已完成唯一暂存名、同名不覆盖、文件级前置校验和失败清理，README 已按当前行为说明。

---

## ~~🟡 DU-03. FP-02 的阶段完成记录与最终状态互相矛盾~~ ✅ 已同步

> 状态: ✅ 已同步
> 影响文档: proposals.feat.md
> 影响范围: GUI 功能跟踪、验收状态、后续去重

### 背景

FP-02 的阶段 1、2、3 和“正式化增强”均写为已完成，条目标题没有标记完成，结尾又写“未实现，待办中”。本次审计还确认术语导入/导出、密钥不进入前端等既有验收项尚未满足。

### 相关位置

- [proposals.feat.md](proposals.feat.md#L148-L197)：多个阶段记录为已完成。
- [proposals.feat.md](proposals.feat.md#L199-L210)：仍列风险并把整体标记为未实现。
- [proposals.feat.md](proposals.feat.md#L95-L102)：既有需求包含仍缺失的术语导入/导出。
- [proposals.p0.md](proposals.p0.md)：本次审计记录了 GUI 的关键安全和正确性缺陷。
- [proposals.p1.md](proposals.p1.md)：本次审计记录了尚未通过的可靠性和规格项。

### 当前文档描述

同一提案同时表达“多个阶段已完成”和“整体未实现”，无法准确用于判断现有能力、去重或启动实施。

### 实际实现或建议描述

GUI 主体和大量功能已经落地，但还没有达到 FP-02 的整体验收状态。当前应视为“已实现主体、验收未通过”，并链接本次 P0/P1。

### 推荐同步方案

暂不把 FP-02 标记为 `✅ 已完成`。把最终实现部分重写为“已落地能力 / 未通过验收项 / 关联缺陷”，删除相互矛盾的阶段结论；待关键缺陷和原始规格缺口完成后，再统一更新标题、最终实现和测试数量。

### 最终同步情况

已将 FP-02 的状态改写为“GUI 主体已实现、关键验收项由 P1/P2 跟踪”，删除“阶段已完成”与“整体未实现”的矛盾表述；阶段 4–6 已关闭对应 P1，术语导入导出等未完成能力仍保留为后续缺口。

---

## ~~🟢 DU-04. README 需要给出可验证的 XLSX 保真矩阵和明确边界~~ ✅ 已同步

> 状态: ✅ 已同步
> 影响文档: README、格式支持文档、测试说明
> 影响范围: XLSX 样式、对象、文本长度、保真承诺

### 背景

README 当前使用“完全保留所有样式”的绝对表述。针对性审查确认公式、数值、超链接、批注、普通单元格样式、合并单元格和重复文本 fan-out 可以保留；阶段 5 已将多 run 富文本收敛为默认 `flatten`，并提供 `preserve_original` 作为保留原文的明确选项。图表、图片、pivot、slicer、外部链接、保护和签名仍按未验证或预检警告处理。

### 相关位置

- [README.md](README.md#L1-L12)：绝对化的样式保留承诺。
- [README.md](README.md#L104-L111)：关键约定中的样式说明。
- [office_translate/formats/xlsx/extractor.py](office_translate/formats/xlsx/extractor.py#L67-L93)：当前 openpyxl 加载和文本提取方式。
- [office_translate/formats/xlsx/applier.py](office_translate/formats/xlsx/applier.py#L50-L91)：物理复制后由 openpyxl 重写工作簿。
- [tests/test_roundtrip.py](tests/test_roundtrip.py#L1-L117)：现有往返测试覆盖范围。
- [proposals.p1.md](proposals.p1.md)：P1-04 记录已验证的富文本缺陷。

### 当前文档描述

文档把“物理复制 + 只替换 value”直接等同于完整保真，没有列出 openpyxl 保存时会重写 OOXML 包，也没有支持/未验证/不支持对象矩阵。

### 实际实现或建议描述

当前可以确认普通样式和若干常见对象保留，但不能宣称所有 XLSX 特性均无损。富文本在修复前属于明确不支持，其他复杂对象应标记为未验证而非默认保证。

### 推荐同步方案

已建立“已验证保留 / 已知限制 / 未验证”的矩阵，并链接对应测试样例。README 的短文案使用准确边界；复杂对象继续按预检警告或未验证处理，不扩大为绝对保真承诺。

### 最终同步情况

README 已加入当前格式边界矩阵：普通字符串/样式、公式与数值、多 run 富文本的默认扁平化与原文保留、`.xls`、`.docx` 和 Excel 长度限制分别标注为支持、保持原样、明确选择或未来功能。阶段 5 文件级回归已完成；复杂对象仍按预检警告或未验证处理，不扩大为绝对保真承诺。

---

## ~~🟡 DU-05. 项目文档应明确 GUI-only 产品定位和轻量本地运行模型~~ ✅ 已同步

> 状态: ✅ 已同步
> 影响文档: README、架构文档、安装与分发说明、proposals.feat.md
> 影响范围: 产品定位、运行入口、CLI/Python API、浏览器/WebView

### 背景

用户已明确软件面向办公小白，核心投入应集中在 GUI。浏览器打开仅用于快速开发或快速启动；WebView 以后可以作为简单外壳，但不是独立产品层。CLI 和 Python 公共 API 不再作为维护能力，可以移除。

### 相关位置

- [README.md](README.md#L1-L12)：当前把 GUI 和 CLI 并列为两种正式使用方式。
- [README.md](README.md#L55-L103)：完整介绍 CLI 手动和自动流程。
- [README.md](README.md#L211-L229)：把 Python 库调用列为正式能力。
- [office_translate/cli.py](office_translate/cli.py#L1-L311)：当前仍维护完整 CLI 产品面。
- [office_translate/__init__.py](office_translate/__init__.py#L24-L73)：当前仍公开 extract/apply 库 API。
- [proposals.p1.md](proposals.p1.md)：P1-10 与 P1-11 记录本地 GUI 边界和产品面收缩。

### 当前文档描述

README 把命令行、脚本调用和 GUI 放在相近地位，并把浏览器/WebView 视为两种等价呈现方式。这会让用户和后续实现者继续维护多套工作流。

### 实际实现或建议描述

产品应描述为“面向非技术办公用户的本地 GUI 文档翻译工具”。本地后端与 Web 前端属于内部实现。浏览器模式是开发和快速启动入口；WebView 只是可选轻量壳。正式用户不需要理解任务目录、TXT/map 中间文件、命令行参数或 Python API。

### 推荐同步方案

README 重写为 GUI-first：安装/启动、选择文件、提取、AI 翻译、审核、导出和常见错误。删除 CLI 与 Python API 教程；开发者内部入口移入贡献文档。架构文档说明“本地回环服务 + 同源静态前端 + 可选轻量 WebView”，并明确不建设 SaaS 用户系统、多租户或远程部署能力。

### 最终同步情况

README 已改为 GUI-only、回环本地服务、离线静态资源和轻量 WebView 说明；已删除 CLI、公共 Python API 和旧 TXT/map 教程。详细 revision、SSE 和密钥契约写入 docs/gui-api.md。

---

## ~~🟡 DU-06. README 与 GUI API 文档需要同步 revision-bound 任务产物和运行依赖~~ ✅ 已同步

> 状态: ✅ 已同步
> 影响文档: README、GUI API/架构文档、安装与依赖说明
> 影响范围: 任务状态机、产物目录、REST 请求、XLSX 控制字符

### 背景

阶段 1 已将 GUI 主流程从 `source.txt`、`map.json`、`translated.txt` 和文件存在性推断迁移到 manifest、SourceArtifact、TranslationArtifact 及版本化输出。阶段 2 又把 TranslationArtifact schema 升级到 v2，将逐项状态、守恒 summary 和脱敏 Provider 诊断绑定到 `translation_revision`。README 仍把旧 TXT/map 目录和顶层 extract/apply API 描述为正式工作流，也没有说明保存与导出请求必须携带 revision 和 succeeded summary。

干净环境回归还确认，独立 CR 的无损 OOXML 往返依赖 `openpyxl` 使用 `lxml` 后端；该依赖现已显式加入运行要求。

### 相关位置

- [README.md](README.md#L55-L103)：仍以 CLI/TXT 流程解释主要使用方式。
- [README.md](README.md#L139-L145)：任务目录仍列固定 source/map/translated 文件。
- [README.md](README.md#L172-L180)：依赖和配置说明没有结构化产物或 revision。
- [office_translate/artifacts.py](office_translate/artifacts.py#L137-L551)：实际 source、translation 与 manifest schema。
- [office_translate/jobs.py](office_translate/jobs.py#L146-L529)：实际任务状态、原子提交、失效和输出发布行为。
- [office_translate/gui/server.py](office_translate/gui/server.py#L268-L363)：实际 revision-aware REST 契约。
- [requirements.txt](requirements.txt#L1-L2)：CR 无损所需的显式 XML 后端。

### 当前文档描述

文档把 TXT 和 map 文件描述为用户及内部共同依赖的固定产物，以固定文件名判断任务步骤，并把 `extract()` / `apply()` 作为正式 Python API；没有描述旧任务升级、409 revision 冲突、版本化文件名、双输出发布或当前产物下载门控。

### 实际实现或建议描述

GUI 内部真相源是 `manifest.json` 指向的版本化 `source.<revision>.json` 和 `translation.<revision>.json`。保存 AI 译文必须提交当前 source revision、完整 ID 状态集和守恒 summary；导出还必须提交当前 translation revision，且 summary 必须为 succeeded。重新提取会失效旧译文和输出。两份 XLSX 先完整生成，再由 manifest 一次切换为当前下载。按当前产品决策不读取旧 schema 或旧模型输出，只允许重新提取/重新翻译。

### 推荐同步方案

阶段 3 移除 CLI/公共 Python API 后，重写 README 的目录结构和用户流程；新增 GUI API/架构文档，列出 manifest 与 artifact schema、任务阶段、409 冲突、无旧 schema 兼容策略、输出发布和下载语义，并纳入阶段 2 已稳定的 AI result/summary 契约。安装说明明确 `lxml` 是确保 CR/CRLF 无损往返的运行依赖。

### 最终同步情况

README 与 docs/gui-api.md 已同步当前结构化 artifact、revision/summary 导出门控、无旧 schema 兼容策略、lxml 运行依赖和双输出发布边界。

---

## ~~🟡 DU-08. 阶段 5–6 的富文本、逐行审核、错误恢复和浏览器验收需要同步~~ ✅ 已同步

> 状态: ✅ 已同步
> 影响文档: README、DESIGN、GUI 内部契约、Feature Proposal
> 影响范围: 富文本导出、审核作用域、revision、键盘与焦点、错误恢复、桌面尺寸、浏览器 E2E

### 背景

阶段 5–6 的最终审计发现，早期文档只描述富文本默认处理和聚合审核卡片，没有说明用户如何选择保留原文或明确扁平化，也没有定义逐行替换范围、审核保存后 revision 推进、复制诊断和真实浏览器验收。FP-02、FP-03、FP-04 与新建的 FP-05 之间也存在范围重叠。

### 相关位置

- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L1163-L1310)：审核 `row_ids` / `selected_row_ids`、翻译完成与审核就绪的独立状态。
- [office_translate/jobs.py](office_translate/jobs.py#L400-L625)：服务端行级作用域校验和仅选中行替换。
- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L598-L708)：逐行差异、富文本两种策略和持久错误恢复入口。
- [tests/e2e/test_gui_workflow.py](tests/e2e/test_gui_workflow.py#L100-L475)：离线手工流程、纯键盘、失败重试、富文本、逐行审核和三种桌面尺寸。

### 当前文档描述

README 仅给出简单格式边界，DESIGN 仍以色板为主，GUI 契约没有审核选中行和富文本策略字段；Feature Proposal 中 FP-02 的历史技术路径与当前实现及 FP-05 的视觉方向重叠。

### 实际实现或建议描述

模型结果完整后可以进入审核，review pending 只阻止导出，不再把翻译误报为失败。审核卡片展示逐行替换前后差异，`selected_row_ids` 为必填字段，且必须是 `row_ids` 的无重复子集。富文本导出默认 `flatten`，用户可明确选择 `preserve_original` 保留受影响单元格原文与局部格式。审核保存推进 `translation_revision` 后，导出使用服务端返回的新 revision。浏览器 E2E 覆盖 900×700、1024×768、1280×800、纯键盘、焦点约束、失败重试和刷新恢复。

### 推荐同步方案

README 保留办公用户可理解的行为与测试命令；DESIGN 记录交互状态和无障碍边界；docs/gui-api.md 记录字段、错误码和 revision 契约；FP-05 明确与 FP-02/03/04 的职责关系。

### 最终同步情况

README、DESIGN、docs/gui-api.md 和 proposals.feat.md 已同步上述实现、验收范围和提案去重关系；旧 CDN/Vuetify/CLI/宽松解析内容仅作为 FP-02 历史记录，不再视为当前方案。

---
