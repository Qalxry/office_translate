# GOAL.md — office_translate P0 → P1 分阶段实施目标

> 创建日期：2026-08-14
> 状态：已完成，阶段 0–6 全部完成（最终回归 2026-08-17）
> 实施策略：分阶段对齐，保留可复用骨架，重建数据契约与 GUI 工作流
> 提案范围：[proposals.p0.md](proposals.p0.md) 与 [proposals.p1.md](proposals.p1.md)

---

## 1. 动机与最终目标

当前项目已经具备 FastAPI、本地 WebUI、模型 Provider 和 XLSX 读写骨架，但核心状态仍由零散文件和前端布尔值推断。翻译记录缺少修订绑定，模型输出缺少稳定 ID，失败结果又可能被当成成功。继续逐条打补丁会让同一问题在保存、恢复、审核和导出环节反复出现。

本轮实施的目标是先消除会生成错误文档的 P0，再完成影响核心可用性的 P1。最终产品保持为面向办公用户的本地 GUI 应用。

完成标准如下：

1. 任务、原文、译文、审核决策和导出文件都绑定同一 source revision。
2. 字面反斜杠、真实换行、CRLF 和多行译文可以无损保存与回填。
3. 非思考模型、流式输出和 Provider 失败都使用带 ID 的严格结果协议。
4. 任何失败、取消、部分完成、未审核或空白译文都不会被标记为可安全导出。
5. XLSX 导入、格式保真和长度边界在生成文件前完成预检。
6. GUI 在刷新、切换任务、窄桌面窗口和错误恢复场景下保持可理解、可操作。
7. 全部 P0/P1 验收测试通过后，才在对应提案中标记完成。

### 1.1 产品边界

本计划采用以下固定边界：

- 正式产品入口是本地 GUI。浏览器入口用于快速启动和开发。
- WebView 只作为简单外壳，不建设独立业务层或复杂生命周期框架。
- 当前只正式支持 .xlsx。选择 .xls 时提供另存为 .xlsx 的图形化说明。
- 不维护 CLI 和公共 Python API。
- 不建设账号、OAuth、RBAC、多租户、远程 SaaS 部署或集中式日志平台。
- 不把手机端布局列入验收范围。桌面分屏和小尺寸窗口仍需可用。

---

## 2. 现状基线与策略选择

### 2.1 可复现基线

审计时的基线结果：

| 项目 | 结果 |
|---|---:|
| 生产代码与测试代码 | 6,191 行 |
| 测试 | 72 passed |
| 测试警告 | 2 条依赖兼容/弃用警告 |
| GUI 前端 | 2,201 行 |
| GUI 后端与启动器 | 877 行 |
| AI 模块 | 768 行 |
| XLSX 模块 | 322 行 |
| 将移除的 CLI/API/转换代码及专属测试 | 656 行 |

基线命令：

~~~bash
python -m pytest -q
~~~

### 2.2 模块变更矩阵

变更程度用于估算骨架复用率。它不是代码质量评分。

| 模块 | 行数 | 变更程度 | 复用价值 | 主要原因 |
|---|---:|---|---|---|
| CLI、公共 API、PowerShell 转换及专属测试 | 656 | ❌ 删除 | 低 | 不属于目标产品面 |
| AI contracts、chunking、provider、translator | 768 | 🔴 大改 | 中 | Provider 接入可复用，结果协议需重建 |
| config、escape、base、glossary | 483 | 🟡 中改 | 中 | 加载与格式骨架可复用，持久化契约需统一 |
| XLSX adapters | 322 | 🟡 中改 | 高 | openpyxl 遍历与回填骨架可复用 |
| GUI server、launcher | 877 | 🟡 中改 | 高 | FastAPI 路由骨架可复用，业务逻辑需下沉 |
| GUI HTML、CSS、JavaScript | 2,201 | 🟡 中改 | 中 | 视觉与页面结构可复用，状态管理需重构 |
| 非 CLI 测试 | 884 | 🟡 中改 | 中 | fixture 和基本流程可复用，断言需升级 |
| **合计** | **6,191** |  |  |  |

按规划技能的复用系数计算，可复用率约为 41%。这一区间适合分阶段对齐。整库重写会丢失 FastAPI、Provider、openpyxl 和现有 GUI 骨架；按提案逐条修补又无法解决跨文件修订、结果状态和导出门控的共同依赖。

### 2.3 代码量估算

| 操作 | 估算 |
|---|---:|
| 删除旧产品面 | 约 600–700 行 |
| 重构现有生产代码 | 约 2,400–3,200 行 |
| 新增生产代码 | 约 800–1,200 行 |
| 新增或更新测试 | 约 1,200–1,800 行 |
| 预计净增长 | 约 1,300–2,300 行 |

---

## 3. 目标结构与核心契约

### 3.1 目标调用结构

~~~mermaid
flowchart LR
    UI["本地 WebUI<br/>浏览器或简单 WebView"]
    API["FastAPI 路由<br/>只负责校验与响应"]
    JOB["JobService<br/>任务状态、修订与导出门控"]
    AIFLOW["AI Workflow<br/>分块、Provider、结果汇总"]
    SETTINGS["SettingsStore<br/>有效配置与密钥"]
    STORE["Storage<br/>进程内锁与原子提交"]
    XLSX["XLSX Adapter<br/>提取、预检与回填"]
    PROVIDER["Provider<br/>OpenAI 兼容 / Google"]

    UI --> API
    API --> JOB
    API --> AIFLOW
    API --> SETTINGS
    JOB --> STORE
    JOB --> XLSX
    AIFLOW --> SETTINGS
    AIFLOW --> PROVIDER
    AIFLOW --> STORE
~~~

FastAPI 路由不再直接拼接文件路径、推断任务阶段或写 JSON。JobService 负责业务规则，Storage 负责单进程锁和原子替换。

### 3.2 统一产物

核心状态改为结构化 JSON。source.txt 和 translated.txt 不再作为内部真相源。

| 产物 | 必要字段 | 作用 |
|---|---|---|
| JobManifest | schema_version、job_id、stage、input_sha256、source_revision、translation_revision、operation | 显式记录任务阶段和当前操作 |
| SourceArtifact | source_revision、input_sha256、items | 保存稳定 ID、原文、工作表和单元格坐标 |
| TranslationArtifact | source_revision、translation_revision、items、review_items、summary | 保存 AI 与手工译文、状态和审核决策 |
| TranslationItem | id、source、translation、status、error、segments | 保证逐条对齐并容纳真实换行 |
| ReviewItem | id、source_item_ids、status、candidate、final_target | 持久化 accepted、edited、ignored 等决策 |
| OperationSummary | operation_id、status、total、succeeded、failed、cancelled | 决定 GUI 状态和导出门控 |

source_revision 由输入文件摘要和规范化后的 SourceArtifact 共同生成。translation_revision 由 source_revision 与 TranslationArtifact 内容生成。任何下游产物都必须声明它基于哪个 revision。

### 3.3 任务状态

~~~mermaid
stateDiagram-v2
    [*] --> created
    created --> extracted: 提取成功
    extracted --> translating: 开始翻译
    translating --> translation_partial: 失败或取消
    translating --> review_required: 存在待审核项
    translating --> ready: 全部成功且无需审核
    translation_partial --> translating: 重试
    review_required --> ready: 全部作出决定
    ready --> exported: 两份输出原子发布
    exported --> extracted: 重新提取并失效旧产物
~~~

阶段只读取 JobManifest，不再根据文件是否存在推断。重新提取会生成新的 source_revision，并使旧译文、审核和输出失效。

### 3.4 全局不变量

后续所有阶段都必须维护以下规则：

1. 请求只提交 job ID、item ID 和 revision，不提交任意输出路径。
2. 保存、审核、重试和导出前都比较 source_revision。
3. TranslationItem 的 ID 必须唯一，并完整覆盖本次输入集合。
4. 原文回退只能作为界面草稿，不计为翻译成功。
5. 解析失败、拒答、截断、少项、多项、重复 ID 和空结果都进入 failed。
6. 只有 summary 为 succeeded、审核已完成且无未确认空白时，任务才能进入 ready。
7. 多文件操作先生成临时文件，全部成功后更新 manifest 并发布。

---

## 4. 分阶段实施计划

功能修复严格按 P0 → P1 推进。阶段 0 只建立可复现基线，不提前实施 P1。

### 阶段 0：锁定测试基线 ✅ 已完成

> 目标：让后续每个阶段都有稳定、可重复的检查入口。
> 预计工作量：小，约 100–200 行。
> 对应提案：实施基础，不关闭任何提案。
> 前置依赖：无。
> 完成日期：2026-08-14。
> 完成结果：72 passed，5 xfailed；当前环境、直接 pytest 和干净虚拟环境均验证通过。

| 任务 | 文件 | 操作 | 完成要求 |
|---|---|---|---|
| 统一 pytest 入口 | pyproject.toml | 新增 | 固定 testpaths、markers 和导入路径 |
| 集中临时工作区 fixture | tests/conftest.py | 新增 | 每个测试拥有独立 config、work、input 和 glossary |
| 固化 P0 复现样例 | tests/test_gui.py、tests/test_ai.py、tests/test_roundtrip.py | 修改 | 先以 strict xfail 记录已确认缺陷 |
| 标记外部依赖测试 | tests | 修改 | 自动测试不访问真实模型与网络 |
| 记录测试环境 | requirements-dev.txt | 修改 | 固定 TestClient 与浏览器测试所需依赖范围 |

验收标准：

- [x] python -m pytest -q 在干净环境可收集并完成。
- [x] 已知 P0 复现测试使用 strict xfail，理由中包含提案 ID。
- [x] 不存在无理由 skip 或永久忽略的失败。
- [x] 现有 72 项成功用例保持通过。

---

### 阶段 1：重建任务修订与结构化产物 ✅ 已完成

> 目标：先解决跨任务、旧映射、转义和半文件导致的错误文档。
> 预计工作量：大，约 900–1,300 行。
> 对应提案：P0-05、P0-06；同时建立 P1-09 的任务存储基础。
> 前置依赖：阶段 0。
> 完成日期：2026-08-15。
> 完成结果：P0-05、P0-06 已关闭，P1-09 的任务产物部分完成；当前环境与干净 Python 3.11 环境均为 87 passed，2 xfailed，剩余 xfail 仅对应阶段 2 的 P0-07。

| 任务 | 文件 | 操作 | 完成要求 |
|---|---|---|---|
| 定义产物数据类与校验 | office_translate/artifacts.py | 新增 | 实现 JobManifest、SourceArtifact、TranslationArtifact |
| 建立本地原子存储 | office_translate/storage.py | 新增 | 同目录临时文件、os.replace、进程内锁、失败清理 |
| 集中任务生命周期 | office_translate/jobs.py | 新增 | JobService 负责 create、extract、save、apply、invalidate |
| 扩展任务配置 | office_translate/config.py | 修改 | 校验 schema_version、路径和显式 stage |
| 提取结构化原文 | office_translate/formats/xlsx/extractor.py | 修改 | 返回带 input_sha256、source_revision、items 的产物 |
| 改造回填入口 | office_translate/formats/xlsx/applier.py | 修改 | 接收结构化译文并校验 revision、ID 和当前原文 |
| 收窄任务路由 | office_translate/gui/server.py | 修改 | 路由通过 JobService 操作，不直接读写任务文件 |
| 建立 job-scoped 前端状态 | office_translate/gui/web/app.js | 修改 | 切换任务先清空，异步响应带 request token |
| 处理旧任务 | office_translate/jobs.py、office_translate/gui/web/index.html | 修改 | 旧目录显示“需要重新提取”，禁止静默沿用旧产物 |
| 转换 P0 回归测试 | tests/test_artifacts.py、tests/test_storage.py、tests/test_gui.py、tests/test_roundtrip.py | 新增/修改 | 将 P0-05、P0-06 strict xfail 转为普通通过测试 |

关键实现要求：

- JSON 原生保存真实换行和反斜杠。前端通过 items 数组保存，不再用物理换行拼接内部记录。
- 批量手工粘贴只用于单行记录。含内部换行的条目使用逐行编辑器，并作为单个 item 保存。
- 重新提取先完整生成新 SourceArtifact，再原子更新 manifest。旧译文、审核和输出随 revision 变化失效。
- apply 在写入前检查映射中的原文是否仍等于当前单元格值。

验收标准：

- [x] 相同条数的两个任务快速切换，旧响应不能写入新任务。
- [x] 重新提取后，旧译文、AI 输出和下载链接全部失效。
- [x] 交换单元格内容后使用旧映射，apply 必须拒绝并指出单元格。
- [x] C:\new\report、字面 \n、真实 LF、CR、CRLF 和尾随反斜杠均可无损往返。
- [x] 保存任一步骤模拟异常时，不出现可被识别为成功的半文件。
- [x] 阶段 1 完成后 P0-05、P0-06 的回归测试全部通过。

---

### 阶段 2：建立严格 AI 结果协议 ✅ 已完成

> 目标：让非思考模型和流式翻译按稳定 ID 返回结果，任何错位都显式失败。
> 预计工作量：大，约 700–1,000 行。
> 对应提案：P0-07。
> 前置依赖：阶段 1 的 SourceArtifact 与 TranslationArtifact。
> 完成日期：2026-08-15。
> 完成结果：P0-07 已关闭；模型输出收敛为模型级 `output_format` 三协议（text/json/xml，默认 xml），全部严格校验并禁止旧格式兼容；SSE 新增逐条 `item_preview`，原始协议正文不再上屏，持久化和导出均由守恒 summary 门控。P1-15（协议选择与流式渲染误导）已同步关闭；完整回归为 139 passed，P0 清零。

| 任务 | 文件 | 操作 | 完成要求 |
|---|---|---|---|
| 定义 AI 结果契约 | office_translate/ai/contracts.py | 新增/修改 | 定义 text/json/xml 三协议解析、item、block、status、summary 和严格 schema |
| 三协议提示词与请求 | office_translate/ai/translator.py | 修改 | 按 output_format 构建提示词、请求与解析 |
| 流式增量预览 | office_translate/ai/streaming.py | 新增 | JSON/XML/文本各自提取已完成片段 |
| 暴露 Provider 完成信息 | office_translate/ai/provider.py | 修改 | 返回 refusal、finish_reason、raw response 和错误类型 |
| 校验集合完整性 | office_translate/ai/translator.py | 修改 | 检查缺失、重复、越界 ID 和空结果 |
| 重定义 SSE 事件 | office_translate/gui/server.py | 修改 | 输出 item_preview、item_succeeded、item_failed、progress、summary，不转发 content 正文 |
| 按 summary 更新界面 | office_translate/gui/web/app.js | 修改 | 逐条预览、完整 summary 才进入下一状态、导出保持门控 |
| 完成协议回归集 | tests/test_ai_formats.py、tests/test_ai.py、tests/test_gui.py | 新增/修改 | 覆盖 JSON/XML/文本、非思考、截断、拒答和断流 |

关键实现要求：

- JSON 结构统一为 items 数组，不再对 translation 字符串执行 split("\n")。
- 三种正式协议（text/json/xml，默认 xml）各有严格解析与 ID/行数校验；不保留旧式无 ID XML、标量 JSON、Markdown fence 或按行拆分兼容路径。
- 文本模式每条译文一行，行内除空格外的空白字符用 `\n`、`\t` 等字面转义，行数必须与输入一致。
- raw response 只写入本地诊断数据，不返回密钥、完整系统路径或敏感请求头。
- summary 的 total、succeeded、failed、cancelled 之和必须等于输入数。

验收标准：

- [x] 两条输入只返回一条结果时，合法条目保留成功、缺失条目失败，summary 为 partial 且不可导出；不补空、不报告 succeeded。
- [x] 翻译内部包含真实换行时，仍保持一个 item。
- [x] 重复、缺失、乱序和未知 ID 都有确定结果。
- [x] finish_reason=length、refusal、空响应和畸形 JSON/XML 都不能进入 succeeded。
- [x] 非思考模型协议测试不依赖 thinking 字段。
- [x] 流式期间每行只显示已解析译文片段，不显示原始协议正文。
- [x] 阶段 2 完成后 P0-07 回归测试全部通过，P0 清零。

---

### 阶段 3：收缩产品面并完成本地可靠性基础 ✅ 已完成

> 目标：在 P0 数据契约稳定后，移除非目标入口，统一本地持久化与运行边界。
> 预计工作量：中，净删除约 300–500 行。
> 对应提案：P1-09、P1-10、P1-11；建立 P1-14 的诊断基础。
> 前置依赖：阶段 2。
> 完成日期：2026-08-16。
> 完成结果：P1-09、P1-11 已关闭；P1-10 的本地同源、离线资源和后端密钥边界已完成。P1-14 在本阶段建立滚动诊断日志与错误编号基础，持久错误恢复、诊断复制和浏览器 E2E 已在阶段 6 完成；WebView 外部导航与桌面打包不属于当前简单外壳边界。

| 任务 | 文件 | 操作 | 完成要求 |
|---|---|---|---|
| GUI 直接使用内部服务 | office_translate/gui/server.py、office_translate/formats/xlsx/__init__.py | 修改 | 不再经过顶层公共 extract/apply 包装器 |
| 移除 CLI | office_translate/cli.py、tests/test_cli.py | 删除 | 删除 init、extract、apply、auto、list 命令面 |
| 移除公共 Python API | office_translate/__init__.py | 修改 | 只保留版本与内部包信息 |
| 移除 PowerShell 转换 | office_translate/win_convert.py | 删除 | .xls 改由 GUI 提供另存为说明 |
| 保留最小 GUI 启动 | office_translate/__main__.py、office_translate/gui/launcher.py | 修改 | python -m office_translate 直接启动本地 GUI |
| 本地化 Vue | office_translate/gui/web/vendor/vue.global.prod.js、index.html | 新增/修改 | 固定版本并随应用分发 |
| 收紧本地来源 | office_translate/gui/server.py、launcher.py | 修改 | 监听 127.0.0.1，删除通配 CORS，只使用同源请求 |
| 统一设置持久化 | office_translate/settings.py、gui/server.py | 新增/修改 | SettingsStore 使用进程内锁与原子提交 |
| 统一术语库持久化 | office_translate/glossary.py、gui/server.py | 修改 | CRUD 在同一锁内完成 read-modify-write |
| 建立本地诊断日志 | office_translate/gui/server.py、launcher.py | 修改 | 标准 logging、滚动文件、操作与 job 上下文 |
| 同步产品文档 | README.md | 修改 | 只说明 GUI、.xlsx 和本地运行方式 |

验收标准：

- [x] 仓库不再包含 CLI、公共 extract/apply 教程和 win_convert 调用。
- [x] python -m office_translate 可直接启动 GUI。
- [x] 断网时页面仍能加载 Vue 和全部静态资源。
- [x] 跨来源请求不获得通配 CORS 许可。
- [x] 设置和术语库的重叠保存不会丢失更新或产生截断 JSON。
- [x] API Key 的 GET 响应只返回掩码与 configured 状态。
- [x] 日志不包含 API Key、完整请求体或用户文档内容。

---

### 阶段 4：完善 Provider、配置、分块与取消语义 ✅ 已完成

> 目标：让所有 Provider、重试和流式路径共享同一配置与结果状态。
> 预计工作量：大，约 700–1,000 行。
> 对应提案：P1-01、P1-02、P1-03；完成 P1-10 的密钥边界。
> 前置依赖：阶段 2 的 AI contract，阶段 3 的 SettingsStore。
> 完成日期：2026-08-16。
> 完成结果：Provider 结果状态、统一配置快照、有界并发、协作取消、上下文预算、超长条目分段与 Google POST 已完成；失败和取消不会伪装成成功，密钥不进入浏览器。

| 任务 | 文件 | 操作 | 完成要求 |
|---|---|---|---|
| 建立有效配置解析 | office_translate/settings.py | 修改 | defaults、saved、effective 只在后端合并一次 |
| 统一 Provider 构造 | office_translate/ai/provider.py、gui/server.py | 修改 | 流式、同步重试和连接测试复用同一 ProviderConfig |
| 后端持有密钥 | office_translate/gui/server.py、web/app.js | 修改 | 前端只提交 provider ID 和模型 ID |
| 统一失败状态 | office_translate/ai/provider.py、translator.py | 修改 | Google/OpenAI 都返回 succeeded/failed/cancelled |
| 实现有界并发 | office_translate/gui/server.py | 修改 | 应用配置中的 concurrency，并保持结果按 ID 汇总 |
| 重写上下文预算 | office_translate/ai/chunking.py | 修改 | 扣除 system、glossary、schema 和最大输出预算 |
| 拆分超长单条 | office_translate/ai/chunking.py、contracts.py | 修改 | 以 item ID、segment offset 重组并验证完整性 |
| 修正 Google 请求 | office_translate/ai/provider.py | 修改 | 使用受支持的 POST，并按实际限制拆分 |
| 加入协作取消 | office_translate/gui/server.py、web/app.js | 修改 | 标记 cancelling/cancelled，停止发布后续成功状态 |
| 完成可靠性测试 | tests/test_ai.py、test_chunking.py、test_gui.py | 修改 | 覆盖全失败、部分失败、重试、取消、配置一致性 |

关键实现要求：

- 取消只能保证本地状态不再提交。已经发出的供应商请求可能仍产生费用，GUI 必须如实说明。
- 原文回退可显示在失败行中，但 status 保持 failed。
- 并发完成顺序可以变化，最终结果必须按 item ID 排序。
- 未实现或不可靠的模型参数应从 GUI 移除，不能保留无效控件。

验收标准：

- [x] Google 全失败时 failed 数量等于输入数量，导出保持禁用。
- [x] 停止操作后 summary 为 cancelled 或 partial，不进入 translated=true。
- [x] 同一设置快照驱动流式、同步重试和连接测试。
- [x] 删除当前 Provider 后，保存操作拒绝无效 active provider/model。
- [x] concurrency 峰值不超过配置值，且大于 1 时确实并发。
- [x] CJK、混合语言、超长单元格和大术语表不会越过预算。
- [x] 供应商请求、浏览器状态和普通日志中不出现完整 API Key。

---

### 阶段 5：建立文件导入与 XLSX 完整性闸门

> 目标：在创建任务和生成输出前发现错误文件、格式损失和 Excel 长度越界。
> 预计工作量：中到大，约 500–800 行。
> 对应提案：P1-04、P1-07、P1-12。
> 前置依赖：阶段 1 的 JobService 与原子发布。
> 当前结果：上传、OOXML 预检、富文本后端策略、GUI 策略选择与重试、Excel 长度检查和双输出原子发布均已完成。

| 任务 | 文件 | 操作 | 完成要求 |
|---|---|---|---|
| 分块上传到唯一暂存文件 | office_translate/gui/server.py | 修改 | 同名文件不覆盖，失败自动清理 |
| 前置校验 .xlsx | office_translate/gui/server.py、formats/xlsx/extractor.py | 修改 | 扩展名、ZIP 结构和工作簿打开均在建任务前检查 |
| 修正任务名与错误文案 | office_translate/config.py、web/app.js、index.html | 修改 | URL 安全名称，错误包含处理方法 |
| 明确拒绝 .xls | office_translate/gui/web/app.js、index.html | 修改 | 展示 Excel/WPS 另存为 .xlsx 的简短步骤 |
| 建立保真预检 | office_translate/formats/xlsx/extractor.py | 修改 | 识别富文本、外链、保护及未验证对象 |
| 实现富文本安全策略 | office_translate/formats/xlsx/applier.py、web/index.html | 修改 | 多 run 默认 flatten 并明确说明格式损失，提供保留原文选项 |
| 检查单元格长度 | office_translate/formats/xlsx/applier.py | 修改 | 两种输出都在保存前检查 32,767 字符 |
| 建立工作簿样例集 | tests/test_workbook_fidelity.py、tests/fixtures/xlsx | 新增 | 覆盖普通样式、富文本、对象和边界长度 |

富文本的当前实施边界：

- 普通字符串和单一文字样式继续自动回填。
- 多 run 富文本默认使用 flatten 翻译并明确说明局部格式损失；用户可选择 preserve_original 保留受影响单元格原文与局部格式。
- 用户可以选择保留原单元格不翻译，或明确确认“统一为首段样式后翻译”。
- 在没有可靠语义映射前，不承诺自动把源文字局部样式正确映射到译文词组。
- README 使用保真矩阵说明已验证、需确认和不支持的对象。

验收标准：

- [x] .xls、假 .xlsx、损坏 ZIP 和无法打开的工作簿不会创建任务。
- [x] 两个同名上传都可被独立识别，任何一个都不会静默覆盖另一个。
- [x] 任务名含 #、? 等保留字符时，在创建前给出可理解提示。
- [x] 多 run 富文本默认 flatten 并在 GUI 明确说明局部格式损失，也可选择保留原文与局部格式。
- [x] 32,766、32,767、32,768 字符及双语拼接边界结果符合预期。
- [x] 输出失败时两份文件都不可见，成功时两份文件同时发布。
- [x] 文件级回归证明已声明支持的样式与对象可以往返。

---

### 阶段 6：完成审核、手工翻译、桌面可用性与错误恢复

> 目标：把结构化数据契约落实为办公用户可理解、可恢复的完整 GUI 工作流。
> 预计工作量：大，约 900–1,300 行。
> 对应提案：P1-05、P1-06、P1-13、P1-14。
> 前置依赖：阶段 4 的结果状态，阶段 5 的文件预检。
> 当前结果：审核持久化、手工翻译、空译文确认、逐行差异与选择、导出门控、键盘与焦点、窄桌面布局、持久错误恢复、诊断复制和浏览器 E2E 均已完成。

| 任务 | 文件 | 操作 | 完成要求 |
|---|---|---|---|
| 持久化审核决策 | office_translate/artifacts.py、jobs.py、gui/server.py | 修改 | 保存稳定 review ID、状态、译法与 revision |
| 建立审核 API | office_translate/gui/server.py | 修改 | 接受、编辑、忽略和全部忽略均原子保存 |
| 恢复审核状态 | office_translate/gui/web/app.js | 修改 | 刷新后不重新生成已处理项 |
| 限定替换范围 | office_translate/gui/web/app.js、index.html | 修改 | 展示逐行差异，只修改确认的 item |
| 修复手工预览 | office_translate/gui/web/app.js | 修改 | 删除同名状态，预览只由结构化 items 计算 |
| 处理空译文 | office_translate/gui/web/app.js、jobs.py | 修改 | 默认阻止，显式清空需逐项确认并持久化 |
| 增加资源状态 | office_translate/gui/web/app.js、index.html | 修改 | 任务、设置、术语和作业均有 loading/empty/error/ready |
| 增加持久错误与重试 | office_translate/gui/web/app.js、index.html | 修改 | 错误留在对应区域，说明保存状态与下一步 |
| 完善键盘与模态框 | office_translate/gui/web/index.html、app.js、style.css | 修改 | 原生控件、focus-visible、焦点进入/约束/恢复、live region |
| 适配桌面窄窗口 | office_translate/gui/web/style.css | 修改 | 900×700、1024×768 和常规桌面窗口可完成流程 |
| 提供诊断复制 | office_translate/gui/web/app.js、server.py | 修改 | 只复制时间、job、operation 和错误编号 |
| 建立浏览器 E2E | tests/e2e/test_gui_workflow.py | 新增 | 覆盖任务、翻译、失败、审核、刷新、导出和键盘操作 |
| 同步交互文档 | DESIGN.md、README.md | 修改 | 记录状态语义、桌面窗口边界和恢复方式 |

验收标准：

- [x] accepted、edited、ignored 决策刷新后保持不变。
- [x] 存在 pending review、failed、cancelled 或未确认空译文时不能导出。
- [x] 批量术语替换前可看到逐行差异，且不会修改未选行。
- [x] 尾随换行和等行数空译文不能绕过手工翻译校验。
- [x] 加载失败不显示为“暂无数据”，错误区提供重试和恢复说明。
- [x] SSE 畸形事件会结束当前操作并进入可重试失败状态。
- [x] 全流程只用键盘可以完成，模态框关闭后焦点返回触发控件。
- [x] 900×700 窗口无关键控件被遮挡，不要求手机端布局。
- [x] 断网浏览器 E2E 可以启动并完成不依赖模型的手工翻译流程。
- [x] 阶段 6 完成后全部 P1 验收通过。

---

## 5. 阶段依赖总览

~~~mermaid
flowchart TD
    S0["阶段 0<br/>测试基线"]
    S1["阶段 1<br/>P0：任务修订与结构化产物"]
    S2["阶段 2<br/>P0：严格 AI 结果协议"]
    S3["阶段 3<br/>P1：产品面与本地可靠性"]
    S4["阶段 4<br/>P1：Provider、配置与分块"]
    S5["阶段 5<br/>P1：导入与 XLSX 完整性"]
    S6["阶段 6<br/>P1：审核、GUI 与恢复"]

    S0 --> S1
    S1 --> S2
    S2 --> S3
    S3 --> S4
    S4 --> S5
    S5 --> S6
~~~

默认按图串行执行。阶段 4 与阶段 5 虽然部分文件不同，但都会修改 server、JobService 和集成测试。为减少合并风险，本计划不预设并行实施。当前阶段 4–6 已按该依赖顺序完成。

---

## 6. 提案追踪矩阵

| 提案 | 主阶段 | 依赖 | 完成判定 |
|---|---:|---|---|
| P0-05 | 1 | 阶段 0 | revision、任务隔离、重新提取失效和 current-source 校验通过 |
| P0-06 | 1 | P0-05 统一产物 | 反斜杠与所有换行形态无损往返 |
| P0-07 | 2 | P0-05 的 item ID | 严格 ID 集合校验与失败 summary 通过 |
| P1-09 | 1、3 | P0 产物契约 | job、settings、glossary 均使用锁与原子提交 |
| P1-10 | 3、4 | SettingsStore | 同源、离线资源、密钥掩码与后端取密钥通过 |
| P1-11 | 3 | P0 稳定内部服务 | CLI、公共 API 和 PowerShell 转换删除 |
| P1-01 | 4 | P0-07 result contract | 失败、取消、partial 与重试状态准确 |
| P1-02 | 4 | 阶段 3 SettingsStore | 设置唯一真相源，所有请求使用 effective config |
| P1-03 | 4 | P0-07 item/segment contract | 预算与超长记录拆分测试通过 |
| P1-04 | 5 | 阶段 1 JobService | 富文本无静默损失，保真矩阵真实 |
| P1-07 | 5 | 阶段 3 GUI-only | 文件在建任务前校验，同名不覆盖 |
| P1-12 | 5 | P1-04 预检 | Excel 长度边界在写盘前阻止 |
| P1-05 | 6 | P0-05 revision、P0-07 item ID | 审核持久化、替换预览与导出门控通过 |
| P1-06 | 6 | P0-06 structured items | 手工预览和空译文确认通过 |
| P1-13 | 6 | GUI 状态稳定 | 键盘、焦点和桌面窗口测试通过 |
| P1-14 | 3、6 | operation summary | 持久错误、重试、诊断复制和日志通过 |

不存在无归属的 P0/P1 条目。已删除的 P1-08 不重新使用编号。

---

## 7. 文件变更清单

### 7.1 新增文件

| 文件 | 阶段 | 用途 |
|---|---:|---|
| pyproject.toml | 0 | pytest 与项目测试配置 |
| tests/conftest.py | 0 | 临时工作区和工作簿 fixture |
| office_translate/artifacts.py | 1 | 任务、原文、译文和审核数据契约 |
| office_translate/storage.py | 1 | 原子写入、临时文件和进程内锁 |
| office_translate/jobs.py | 1 | 任务生命周期与导出门控 |
| tests/test_artifacts.py | 1 | revision 与 schema 测试 |
| tests/test_storage.py | 1 | 原子提交和并发交错测试 |
| office_translate/ai/contracts.py | 2 | AI item、block、status 与 summary |
| tests/test_ai_contracts.py | 2 | 严格输出协议测试 |
| office_translate/settings.py | 3 | GUI 设置唯一真相源 |
| office_translate/gui/web/vendor/vue.global.prod.js | 3 | 固定版本的本地 Vue 运行时 |
| tests/test_workbook_fidelity.py | 5 | XLSX 保真与边界测试 |
| tests/fixtures/xlsx/ | 5 | 文件级工作簿样例 |
| tests/e2e/test_gui_workflow.py | 6 | 真实浏览器核心流程测试 |

### 7.2 删除文件

| 文件 | 阶段 | 原因 |
|---|---:|---|
| office_translate/cli.py | 3 | 不维护 CLI 产品面 |
| office_translate/win_convert.py | 3 | 不维护 PowerShell .xls 转换 |
| tests/test_cli.py | 3 | 对应产品面删除 |

### 7.3 修改文件

| 文件 | 阶段 | 变化要点 |
|---|---|---|
| office_translate/__init__.py | 3 | 移除公共 extract/apply |
| office_translate/__main__.py | 3 | 直接启动 GUI |
| office_translate/base.py | 1、3 | 收窄为内部格式适配契约 |
| office_translate/config.py | 1、5 | manifest、路径与任务名校验 |
| office_translate/escape.py | 1 | 仅保留显式文本序列化用途，不再承担内部状态 |
| office_translate/glossary.py | 3 | 锁内 CRUD 和原子保存 |
| office_translate/ai/chunking.py | 4 | 上下文预算与 segment |
| office_translate/ai/provider.py | 2、4 | 完成信息、状态与 ProviderConfig |
| office_translate/ai/translator.py | 2、4 | 严格 items schema 与完整性校验 |
| office_translate/formats/xlsx/__init__.py | 1、3 | 内部适配器入口 |
| office_translate/formats/xlsx/extractor.py | 1、5 | SourceArtifact、revision 与保真预检 |
| office_translate/formats/xlsx/applier.py | 1、5 | revision、原文、富文本和长度校验 |
| office_translate/gui/launcher.py | 3、6 | 本地启动、日志和简单 WebView 边界 |
| office_translate/gui/server.py | 1–6 | 路由变薄、SSE、设置、上传、错误语义 |
| office_translate/gui/web/app.js | 1–6 | job-scoped 状态、结果、审核、错误与焦点 |
| office_translate/gui/web/index.html | 3、5、6 | 本地 Vue、导入说明、语义与错误区 |
| office_translate/gui/web/style.css | 6 | focus-visible 与桌面窄窗口布局 |
| tests/test_ai.py | 0、2、4 | Provider 与协议回归 |
| tests/test_chunking.py | 4 | CJK、预算和超长记录 |
| tests/test_escape.py | 1 | 字面转义与控制字符回归 |
| tests/test_glossary.py | 3 | 并发保存与原子性 |
| tests/test_gui.py | 0–6 | API、状态、SSE、上传和门控 |
| tests/test_roundtrip.py | 0、1、5 | 直接内部 adapter 与文件回归 |
| requirements.txt | 0、3 | 记录兼容运行依赖 |
| requirements-dev.txt | 0、6 | TestClient、pytest 与浏览器测试依赖 |
| README.md | 3、5、6 | GUI-only、格式边界和恢复说明 |
| DESIGN.md | 6 | 状态语义、焦点和桌面窗口规范 |

---

## 8. 质量保障

### 8.1 测试分层

| 类型 | 重点 | 主要文件 |
|---|---|---|
| 单元测试 | revision、schema、状态转换、分块、转义 | test_artifacts.py、test_ai_contracts.py、test_chunking.py |
| 存储测试 | 原子替换、锁、失败清理、重叠保存 | test_storage.py、test_glossary.py |
| API 集成测试 | job、SSE、取消、审核、上传、导出门控 | test_gui.py |
| XLSX 文件测试 | 原文核对、样式、富文本、对象、长度 | test_roundtrip.py、test_workbook_fidelity.py |
| 浏览器 E2E | 刷新恢复、键盘、错误重试、断网启动 | tests/e2e/test_gui_workflow.py |
| 可选人工冒烟 | 真实 Provider、简单 WebView | 不进入默认自动测试 |

### 8.2 每阶段共同检查

每个阶段结束时都执行：

1. python -m pytest -q 全部通过。
2. 本阶段对应的 strict xfail 已转为普通测试，不保留 xpass。
3. git diff --check 通过。
4. 新增状态或字段有 schema 校验和迁移行为。
5. 错误路径与成功路径均有测试。
6. 阶段验收未全部通过时，不把提案标记为完成。

最终发布前额外执行：

- [x] 断网浏览器 E2E。
- [x] 900×700、1024×768、1280×800 三组桌面截图检查。
- [x] 两份 XLSX 输出的文件级回归。
- [x] 日志、API 响应和前端状态中搜索 API Key。
- [x] 从阶段 0 建立的全部 defect xfail 已清零。

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 旧任务没有 revision | 无法证明旧译文和映射匹配 | 只读显示任务，要求重新提取，不自动猜测 |
| 多文件无法形成真正文件系统事务 | 崩溃时可能只生成部分临时文件 | 所有临时文件成功后最后更新 manifest，启动时清理孤立临时文件 |
| Provider 请求已经发出后无法保证停止计费 | 用户以为点击停止即可取消费用 | 使用 cancelling/cancelled 准确表述，并在 GUI 明示限制 |
| 富文本样式与译文词组没有确定映射 | 自动保留可能制造错误格式 | 默认 flatten 并明确说明局部格式损失，另提供保留原文选项 |
| app.js 仍然较大 | 状态重构容易产生回归 | 先集中 API、job state 和 operation reducer，再分步骤迁移，不同时更换前端框架 |
| server.py 被多个阶段修改 | 合并和回归风险高 | 阶段 1 先下沉 JobService，后续路由只做薄层改动 |
| 本地 Vue 资产引入版本与许可证问题 | 分发缺失或版本漂移 | 固定版本、保留许可证、断网测试加载 |
| 测试使用 fake Provider 与真实端点有差异 | 自动测试无法覆盖所有供应商行为 | 保存原始元数据契约，发布前执行可选真实端点冒烟 |

---

## 10. 实施确认

以下三点已经确认：

1. 接受“结构化 JSON 为内部真相源，TXT 不再承担任务状态”的方向。
2. 接受多 run 富文本默认 flatten，并由用户明确选择是否保留受影响单元格原文与局部格式。
3. 接受先完成全部 P0，再删除 CLI/API 并进入 P1 的顺序。

阶段 0–6 已按依赖顺序完成并通过最终验收。全量回归为 `214 passed, 4 warnings`；最终审计确认富文本策略、逐行审核选择、JSON/XML/文本逐条流式预览、纯键盘 E2E、失败恢复、刷新下载恢复和审核后最新 revision 均已闭环。P2 与远期 FP-05 不属于本 Goal；FP-05 已作为后续淡彩 Expressive 视觉与信息架构增强提案保留。
