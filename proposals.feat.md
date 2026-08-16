# Feature Proposal: 功能提案

> 最后审计日期: 2026-08-16
> 最后编号：FP-05

---

## FP-01. docx（Word）格式适配器：保留格式的翻译支持

> 推荐程度: 🟡 推荐
> 影响范围: 架构（新格式适配器，`formats/docx/`）
> 评级理由: 用户明确表示未来要扩展 Word 翻译需求，架构已预留扩展点，python-docx 1.2.0 已装，实现成本低（实测已验证格式可保留）

### 功能描述

为套件新增 `.docx`（Word）格式支持，沿用现有「extract → 人工翻译 → apply」任务制流程：

- **extract**：遍历 docx 正文段落 + 表格单元格（+ 可选页眉页脚），按段落收集文本，去重写入 `source.txt`，位置映射写入 `map.json`。
- **apply**：物理复制原 docx → 以副本为模板，段落级替换译文 → 输出「仅译文」与「原文-译文对照」两份文件，**保留全部样式**（字体、颜色、加粗、段落格式等）。
- 与 xlsx 一致：只处理可翻译的字符串文本，跳过空段；去重、CR/LF 转义、对照版分隔符（`sep`）等约定复用现有 `escape.py` 与 CLI。

**关键机理**（已实测验证）：docx 是 zip 内的 XML，文本节点 `<w:t>` 与格式节点 `<w:rPr>` 分离，只改文本即可天然保留格式——实测修改 run 文本后加粗/斜体/字号/颜色全部保留，与 xls 需手工重建样式形成鲜明对比。

### 原始表述

> 「有没有docx保留格式的翻译的方法？」
> （前情：重组架构时用户反馈「你的结构不太符合我未来希望扩展至word翻译、xls翻译的需求」，架构已据此预留适配器注册表。）
> 用户选择「先记待办」，暂不实现。

### 位置

- [office_translate/base.py](office_translate/base.py#L31-L62)：`FormatAdapter` 抽象基类（新增 `DocxAdapter` 子类即挂入，无需改核心）
- [office_translate/base.py](office_translate/base.py#L70-L92)：`register_adapter` / `get_adapter` 注册表与 `UnsupportedFormatError`（`.docx` 当前会报「暂不支持」）
- [office_translate/formats/__init__.py](office_translate/formats/__init__.py#L7)：注册入口（新增 `from . import docx`）
- [office_translate/cli.py](office_translate/cli.py)：任务制 CLI（init/extract/apply 按 job.yaml 的输入扩展名分发，docx 接入后无需改动）
- [office_translate/escape.py](office_translate/escape.py)：文本转义工具（格式无关，docx 复用）

### 方案比较

**方案 A：python-docx 段落级处理（推荐）**
- 用 python-docx 遍历 `paragraphs` + `tables` 收集文本；apply 时物理复制原文件，打开副本，把段落所有 run 清空并合并为一个 run（保留首个 run 的格式），写入译文。
- 优点：代码量小、可读性好、生态成熟；段落格式（样式、对齐、缩进）天然保留。
- 缺点：页眉/页脚/文本框需额外处理；多 run 合并会丢失段落内「部分字符特殊格式」（如一段中个别红色词）——可接受，因为翻译本身会改写整段。

**方案 B：直接操作 XML（zipfile + lxml）**
- 解包 docx，直接改 `word/document.xml` 中 `<w:t>` 文本节点，再重新打包。
- 优点：格式 100% 保留（连 run 结构都不动）、可精确控制（如跳过域代码 `<w:fldChar>`）。
- 缺点：工作量大、需自行处理 XML 转义与 run 边界、维护成本高。

**方案 C：LibreOffice headless 查找替换**
- 依赖外部 soffice，本机未安装；查找替换对「原文→译文」多对一映射支持差。

**推荐**：方案 A。与 xlsx 适配器「物理拷贝 + 定位回填」思路一致，复用现有架构最自然；若日后遇到域代码/复杂嵌套需求，再升级到方案 B 的 XML 处理。

### 推荐实现方案

1. 新增 `office_translate/formats/docx/__init__.py`，实现 `DocxAdapter(FormatAdapter)`：
   - `extract(src, txt, json)`：遍历 `doc.paragraphs` 与 `doc.tables`（递归单元格段落），对每个非空段落收集文本（多 run 拼接为整段），去重写 txt + 映射 JSON（记录段落所在容器：body / table / cell，及段落索引）。页眉页脚作为可选开关。
   - `apply(original, json, translated_txt, out_translated, out_bilingual, sep)`：`shutil.copy2` 复制原文件 → python-docx 打开副本 → 按映射定位段落，清空 runs 后写译文（保留首个 run 的格式）→ 对照版写「原文 + sep + 译文」→ 保存两份输出。
2. `formats/__init__.py` 加 `from . import docx` 完成注册。
3. `requirements.txt` 追加 `python-docx>=1.2.0`。
4. 新增测试：构造带样式（加粗/颜色/表格/多 run 段落）的 docx → extract → apply → 校验译文位置、样式保留、对照版格式。
5. README「扩展新格式」一节补充 docx 已支持。

**风险与注意**：
- 域代码（目录、页码、交叉引用）内的文本不应导出/替换；方案 A 下需按 `run` 的 XML 属性判断并跳过。
- 空段落、纯数字/代码段落默认不导出（与 xlsx 约定一致）。
- 对照版若段落内有表格，需确保追加的译文 run 落在正确容器内。

### 最终实现情况

（未实现，待办中）

---

## FP-02. 跨平台 GUI：Web 前端 + AI 翻译 + 不确定术语审核 + 术语库

> 推荐程度: 🔴 强烈推荐
> 影响范围: 全局（新增 gui/ 与 ai/ 模块，任务制流程扩展为 5 步）
> 评级理由: 用户明确的核心诉求——现代美观跨平台 GUI、AI 翻译主动标出不确定术语供审核、明确的流程感；所有关键决策已确认，环境依赖基本就绪

### 功能描述

为套件新增一个跨平台桌面 GUI，把「init → extract → 人工翻译 → apply」任务制流程升级为带 AI 辅助的 5 步流程：

1. **任务选择/新建**（对应 init）
2. **提取原文**（对应 extract）
3. **AI 翻译**：选模型 → 批量翻译 → 模型自报不确定术语
4. **审核**：UI 以卡片列表展示每个不确定术语，可接受 / 修改 / 拒绝；接受时**选择存入的术语类别**（已有类别或新建），自动沉淀入术语库
5. **回填输出**（对应 apply）

UI 顶部有**步骤条（stepper）**，当前步骤高亮、完成步骤打勾、可回跳——「流程感」的核心载体。

**已确认的决策**：
- GUI 形态：Web 前端 + 本地服务；有 PyWebView 开本地原生窗口，否则自动开默认浏览器
- AI 接入：OpenAI 兼容 API（Claude/OpenAI/DeepSeek 等，base_url+key+model 可配）+ Google Translate API（端点/镜像可配，deep-translator 支持 proxies 加速）
- **Google 镜像站实测（2026-08-10）**：三个站点翻译质量一致（同代理 Google 引擎）；速度 yifan(~0.3s) > renwole(~0.6s) > tantu(~1s)；稳定性 tantu(3/3) > renwole(2/3) > yifan(0/3)，后两者连发会触发 429 限流。**默认首选 tantu**，renwole/yifan 作备选
- **失败自动切换镜像站**：单站请求失败或 429 时，自动切换到下一个可用镜像站，全部失败才报错；每个镜像站维护失败计数（连续失败 N 次则暂缓使用一段时间）
- 不确定术语判定：**仅 AI 自报**（prompt 要求返回结构化 JSON 含不确定列表，不叠加规则启发式）
- 审核结果**沉淀术语库**（按类别），下次翻译注入 prompt 优先采用，审核负担随使用递减
- 术语库**分类管理**：审核时选类别存入；翻译时可勾选使用类别；支持手动查看/编辑/删除/新增/导入导出
- 术语**匹配精简化**：翻译前先匹配「确实出现在本次待译文本中的术语」再注入 prompt，避免全量注入、控制上下文

### 原始表述

> 「现在缺少一个跨平台的GUI，但我又希望这个GUI能够比较现代美观。并且能够让外部翻译AI 模型对于一些他感到不确定性较高的术语提供给用户进行审核和修改。有一个明确的流程感。」
> 追问后补充：「可能我感觉设计为自动开浏览器会更好。或者用WebView。」
> AI 接入补充：「支持 OpenAI Compatible API + Google Translate API(支持镜像加速)」
> 镜像站需求：「我有这些加速站点，你测试测试这些的google api是否可用加速。」（提供 3 个镜像站）；「行，最好可失败后自动切换镜像站。」（决定采用失败自动切换机制）

### 位置

- [office_translate/cli.py](office_translate/cli.py#L197-L212)：`main()`（GUI 复用其 extract/apply 调用，或另走库接口）
- [office_translate/__init__.py](office_translate/__init__.py#L35-L73)：顶层 `extract()`/`apply()`（GUI 后端直接调用）
- [office_translate/config.py](office_translate/config.py#L20-L66)：`DEFAULT_CONFIG` / `load_config`（GUI 需读取同一配置，新增 AI 相关配置项）
- [office_translate/config.py](office_translate/config.py#L68-L148)：`init_job` / `load_job` / `list_jobs`（GUI 的任务选择/新建直接复用）
- [office_translate/base.py](office_translate/base.py#L31-L62)：`FormatAdapter`（GUI 与 AI 翻译均与格式无关，天然兼容）
- [office_translate/escape.py](office_translate/escape.py)：转义工具（AI 翻译产出译文写 txt 时复用）

### 方案比较

**GUI 技术栈（已确认 Web + WebView/浏览器）**：
- 后端 FastAPI + uvicorn（127.0.0.1 随机端口本地服务，已装 fastapi 0.136 / uvicorn 0.46）
- 前端 Vue 3 + Vuetify（Material Design，现代美观，CDN 或本地打包）
- 呈现层：优先 `pywebview`（已装则开原生窗口，体验最像桌面应用）；未装则 `webbrowser.open` 自动开默认浏览器。两条路径共用同一套 Web UI，跨平台一致。

**AI 接入（已确认）**：
- OpenAI 兼容：`openai` 2.52 已装，配 base_url + api_key + model，一套代码覆盖 Claude/OpenAI/DeepSeek/本地 Ollama 等
- Google Translate：`deep-translator` 1.9.1 已装，GoogleTranslator 支持 `proxies` 参数（镜像/加速的关键），端点域名可配置
- **镜像站机制**：预置实测过的 3 个镜像站，GUI 设置页可增删；默认顺序按稳定性排（tantu → renwole → yifan）；请求失败或 429 时自动切下一个，连续失败 N 次暂缓该站（冷却）；全部失败才报错
- 抽象 `Provider` 接口，GUI 里选择模型并配置密钥，密钥存本地（config.yaml 或独立 settings，不硬编码）

**不确定术语判定（已确认仅 AI 自报）**：
- prompt 要求返回 JSON：`{"translation": ..., "uncertain_terms": [{"term", "reason", "candidate"}]}`
- 术语库已有词条注入 prompt 作为「已知术语表，必须优先采用」
- 优点：实现简单、语义准确（模型自知）；风险：漏报（模型把握不足但没标出），用「仅 AI 自报」的承诺接受该风险，后续如需可叠加规则

**术语库（已确认沉淀 + 升级：分类 / 匹配精简 / 按类别选用 / 手动管理）**：
- 持久化：项目根 `glossary.json`，**带类别**：`{"categories": {"<类别名>": [{"source", "target", "note", "created"}]}}`，可 git 管理
- 分类：审核接受时**用户选择把术语存入哪个类别**（可选已有类别或新建）；类别天然对应领域（如「汽车行业」「软件」「财务」）
- **匹配精简化**：翻译注入前，把术语库条目与本次待译文本做匹配，**只把「确实出现在本次文本中」的术语注入 prompt**，而非全量注入——控制上下文长度、减少无关术语干扰模型
- 按类别选用：**每次翻译可勾选使用哪些类别**的术语库（默认全部），未勾选类别的术语不注入、不参与匹配
- 手动管理：术语库管理页支持**查看、编辑、删除、新增、导入导出**；既可在审核时增量添加，也可手动整理
- 增长：每次审核接受的条目按所选类别入库，审核负担随使用递减

### 推荐实现方案

**阶段 1：AI 翻译核心（无 GUI，纯库 + pytest 可测）**
1. `office_translate/ai/provider.py`：`Provider` 抽象基类 + `OpenAICompatProvider`（openai 客户端）+ `GoogleProvider`（deep-translator，proxies/端点可配 + **镜像站列表与失败切换/冷却**：`MirrorPool`，按序尝试、失败切下一个、连续失败冷却）
2. `office_translate/ai/translator.py`：`translate_batch(texts, glossary, provider) -> [{id, translation, uncertain_terms}]`；prompt 含已匹配术语表；解析模型 JSON 输出（含失败回退——模型不返回 JSON 时降级为纯文本译文、无不确定项）
3. `office_translate/glossary.py`：`load_glossary` / `add_terms(category, ...)` / `match_terms(categories, texts)`（**匹配精简化**：只返回出现在 texts 中的条目）/ `list_categories` / 术语注入 prompt 格式化
4. `requirements.txt` 追加 `fastapi`、`uvicorn`、`openai`、`deep-translator`（均为必选）；`pywebview` 为可选

**阶段 1 最终实现情况（已完成）**：
- `office_translate/ai/provider.py`：`Provider` ABC + `OpenAICompatProvider`（openai 客户端）+ `GoogleProvider`（**直接请求镜像站 `/translate_a/single` 端点**，`client=gtx&dt=t`，与插件做法一致）+ `MirrorPool`（失败自动切换、连续失败冷却）
- `office_translate/ai/translator.py`：`translate_batch` 批量翻译 + `_parse_result` JSON 解析（模型不返回 JSON 时降级为纯文本、无不确定项）+ 失败降级（保留原文并标注）
- `office_translate/glossary.py`：分类术语库 `load/add/save/remove/match_terms/format_glossary_prompt`；匹配精简化按类别 + 大小写不敏感
- **实测**：三个镜像站（tantu/renwole/yifan）均可用，翻译质量一致；失败自动切换生效（模拟第一个镜像失败自动切到 tantu）；批量翻译成功
- **修正**：最初用 `deep-translator`（走 `/m` 网页端点）实测失败 → 改直接请求 `/translate_a/single`（镜像站只代理此端点）→ 验证通过
- **42 个测试全部通过**（含 MirrorPool 切换/冷却、JSON 解析、术语库匹配精简）

**阶段 2：GUI 壳（Web 后端 + 前端 + 启动器）**
1. `office_translate/gui/server.py`：FastAPI 应用，REST 接口：任务 CRUD/list、extract、ai_translate（分批+进度回调或轮询）、审核提交、apply、术语库 CRUD
2. `office_translate/gui/web/`：Vue 3 + Vuetify 前端，静态资源由 FastAPI 挂载；5 步 stepper 界面
3. `office_translate/gui/launcher.py`：启动 uvicorn（随机端口）→ 有 pywebview 开原生窗口 / 否则开浏览器
4. `python -m office_translate gui` 入口（cli.py 增加子命令）

**阶段 2 最终实现情况（已完成）**：
- `office_translate/gui/server.py`：FastAPI 应用，REST 接口：任务列表/新建、extract、source 读取、translated 保存、apply、AI 翻译（google/openai 双引擎 + 术语匹配）、术语库 CRUD、镜像站列表
- `office_translate/gui/web/index.html`：Vue 3 CDN 单页应用（**无构建、无 node 依赖**），5 步 stepper 界面（任务→提取→AI 翻译→审核→回填）。**设计约束：无渐变、扁平纯色、细边框、淡彩系**（用户明确要求「不要任何渐变，简约线条，淡彩」）
- `office_translate/gui/launcher.py`：启动 uvicorn（自动选空闲端口）+ 优先 pywebview（未装则回退浏览器自动打开）
- `python -m office_translate gui` 已接入 CLI
- `requirements.txt`：+requests、openai、fastapi、uvicorn（deep-translator 不再需要，已改直接请求镜像站）
- **实测**：GUI 服务启动、前端页面加载（200）、任务列表、AI 翻译（真实 eval_2024 任务前 3 条：Questionnaire:/PRE EVAL/Progress: → 调查问卷：/预评估/进步：）、术语库读取均正常
- **47 个测试全部通过**（含 GUI 后端 6 个接口测试）

**阶段 3：审核体验打磨**
- 不确定术语卡片：原文 / 模型译文 / 不确定原因 / 候选译法；接受（选类别入术语库）/ 修改（编辑译文）/ 拒绝（忽略）
- 审核进度条、可批量接受
- 术语库管理页：按类别浏览/编辑/删除/新增/导入导出；翻译时勾选使用类别
- 匹配精简化校验：注入前确认仅含匹配条目，避免全量注入

**阶段 3 最终实现情况（已完成）**：
- 前端新增「术语库管理」视图：按类别浏览、新增、编辑（PUT）、删除（DELETE）、筛选
- 前端新增「设置」视图：镜像站列表编辑、保存（本次会话生效）、「测试全部镜像站」（真实测连通性与延迟并排序）
- 后端新增 `/api/mirrors/test`（镜像测试排序）、`PUT /api/glossary/terms`（术语编辑）
- 实测：镜像测试 tantu 可用 795ms / yifan 失败；术语库新增→编辑→匹配全流程正常
- **50 个测试全部通过**

**正式化增强（用户体验反馈后追加，已完成）**：
- 用户反馈：「功能太简陋，复杂度太低，需要大幅细化，面向正式可用」
- 后端：`/api/settings` 读写（供应商/镜像站/语言/并发，持久化到 `gui_settings.json`）；`/api/pick_file` 用 tkinter 弹原生文件选择器；术语类别删除、批量删除
- 前端：新建任务「浏览文件」按钮（file picker）；设置页供应商管理（预置 OpenAI/DeepSeek/Claude/Ollama，可增删改/设为主用）；翻译步骤从设置拉供应商与模型；术语库类别删除
- CLI：新增 `auto` 子命令（extract→AI 翻译→apply 一条命令，读同一 gui_settings.json，支持 --engine/--model/--mirrors 覆盖）
- 翻译并发：`translate_batch` 支持并发（ThreadPoolExecutor），失败单条降级为原文
- README 全面同步（GUI 使用、设置、一键翻译、术语库、目录结构）
- **55 个测试全部通过**；一键翻译真机实测（问卷→问卷调查 / 供应商质量评估）

**风险与注意**：
- AI 批量翻译长文本（如多行单元格）需按条分隔、控制并发与限流（Google 免费端点尤其）
- 模型 JSON 输出不稳定：必须容错降级，不阻塞主流程
- 术语库冲突：同一 source 已有词条时新审核默认更新并提示（按类别维度）
- 匹配精简化需处理大小写/空白差异：同一 term 的多种形态（如 "PPB" 与 "ppb"）应统一匹配
- 密钥安全：只写本地配置，前端不直接暴露
- **镜像站限流**：实测 renwole/yifan 连发会 429，需失败切换 + 冷却；冷却期过后自动恢复，避免永久弃用
- **镜像站可用性漂移**：免费镜像站随时可能失效，GUI 设置页应有「测试全部镜像站」按钮，便于用户重新测速排序

### 最终实现情况

GUI 主体已实现：本地 FastAPI + Web 前端/轻量 WebView、五步工作流、AI 翻译、三种模型内容协议、流式逐条预览、术语审核和分类术语库均已落地。阶段 3 又完成了 GUI-only 产品收缩、离线静态资源、同源回环边界和后端密钥持有。

阶段 4–6 已补齐 Provider 状态、上下文安全分块、XLSX 预检与富文本策略、逐行审核、错误恢复、键盘/焦点和浏览器 E2E。上文关于 CDN、Vuetify、CLI、宽松 JSON 降级、失败原文回退和 tkinter 文件选择的内容只保留为历史实施记录，不再是当前方案；当前权威行为以 GOAL.md、P1 最终修复情况和 GUI 内部契约为准。

本 Feature 暂不标记整体完成，剩余范围主要是术语库导入/导出等原始功能缺口。视觉与信息架构重构由 FP-05 单独跟踪，风险报告和持久修订历史分别由 FP-03、FP-04 跟踪；旧 CLI/API/TXT 工作流不再是本 Feature 的实现目标。

---

## 🔴 FP-03. 导出前翻译质量闸门与风险摘要

> 推荐程度: 🔴 强烈推荐
> 影响范围: 导出、审核、失败回退、译文完整性
> 评级理由: 在基础正确性修复后，可显著降低把空译文、原文回退或未审核内容交付出去的概率

### 功能描述

在生成 Office 文件前执行一次可解释的质量预检，汇总并定位：空译文、与原文完全相同、Provider 失败回退、未完成审核、ID/行数异常、超长单元格、未保存编辑和基于旧 source revision 的结果。

质量闸门不取代 P0/P1 的服务端正确性校验。它面向正常但有风险的结果，让用户在交付前看到一份简洁风险摘要，并能跳到对应原文、译文和审核项。

### 位置

- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L573-L593)：当前导出页只有自由文本框和生成按钮。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L1195-L1209)：导出前没有质量预检。
- [office_translate/gui/server.py](office_translate/gui/server.py#L397-L414)：后端 apply 入口没有风险摘要协议。
- [office_translate/formats/xlsx/applier.py](office_translate/formats/xlsx/applier.py#L94-L149)：当前仅做条数和 ID 连续性校验。

### 方案比较

- **方案 A：只显示被动统计。** 成本低，但高风险项容易被忽略。
- **方案 B：按风险分级。** 空译文、失败、映射异常、旧 revision 和长度超限硬阻止；原文保留、未审核术语等允许显式确认。信息与可用性平衡最好。
- **方案 C：任何异常都硬阻止。** 最安全，但合法保留原文、专有名词不翻译等场景会过于僵硬。

### 推荐实现方案

采用方案 B。服务端生成结构化报告，包含规则 ID、严重程度、受影响 item/cell、解释和修复入口；前端按“必须修复 / 需要确认 / 提示”三组展示。用户对“保留原文”或“清空单元格”的确认应成为持久化决策，并与 source revision 绑定。导出文件记录使用的 revision 和质量报告摘要。增加每条规则、确认失效、定位跳转和导出阻断测试。

### 最终实现情况

基础硬门控已由 P0/P1 完成：失败、取消、partial、pending review、未确认空译文、revision 不一致、富文本策略和 Excel 长度越界都会阻止导出。FP-03 剩余范围收窄为面向用户的风险分级、同原文等软风险规则、集中质量摘要、定位跳转和可持久确认，不重复实现现有正确性门控。

---

## 🟡 FP-04. 可恢复的翻译操作与逐版本修订历史

> 推荐程度: 🟡 推荐
> 影响范围: AI 翻译、取消、恢复、手动编辑、术语替换、回滚
> 评级理由: 正式使用会反复覆盖译文和重试模型，持久操作与版本历史可把不可逆流程变成可审计、可恢复流程

### 功能描述

为每次翻译建立 job-scoped operation ID 和状态：`queued/running/cancelling/cancelled/succeeded/failed/partial`。浏览器刷新、断开或切换任务后仍能查询进度、重放事件并从未完成块继续。

同时保存 AI 初稿、手动修改、术语批量替换、失败重试和导出前版本。用户可以查看逐行差异、恢复旧版本，并知道每份输出基于哪个 source revision、模型配置和译文 revision。

### 位置

- [office_translate/gui/server.py](office_translate/gui/server.py#L356-L395)：当前 AI 输出使用单一 JSON 文件覆盖。
- [office_translate/gui/server.py](office_translate/gui/server.py#L568-L674)：翻译操作完全依附单个 HTTP 流。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L881-L1047)：进度、取消和持久化主要由当前浏览器页面控制。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L1049-L1080)：逐行编辑没有修订历史。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L1143-L1177)：术语替换直接覆盖当前结果。

### 方案比较

- **方案 A：浏览器 localStorage。** 实现快，但跨窗口、清缓存和任务迁移后丢失，不能成为任务真相源。
- **方案 B：仅内存 operation registry。** 可正确取消和查询，但应用重启后丢失。
- **方案 C：任务目录中的操作 journal + 译文修订。** 可恢复、可备份、符合单机桌面规模，不需要外部数据库，推荐。

### 推荐实现方案

采用方案 C。提供创建操作、查询状态、订阅事件、取消和恢复 API；操作快照绑定 source revision、provider ID、模型和非敏感参数。完成块原子追加到 journal，SSE 支持事件序号和重放。译文修订记录父版本、来源、时间、原因和内容哈希，可采用周期性完整快照加中间差异。取消至少阻止后续块，并把不可中断的当前请求标为 cancelling。导出记录所用修订 ID，恢复前显示差异并确认。

### 最终实现情况

已完成内存级 operation ID、状态查询、协作取消、SSE 最终 summary 和刷新后的任务产物恢复。FP-04 剩余范围是跨应用重启的持久 journal、事件序号/重放、译文父子修订历史、差异查看和回滚；不会重复建设当前已完成的进程内取消与结果守恒逻辑。

---

## 🔴 FP-05. 淡彩 Expressive 翻译工作台与可复用交互组件体系

> 推荐程度: 🔴 强烈推荐
> 影响范围: GUI 信息架构、任务工作流、翻译与审核工作区、视觉 Token、前端工程化、无障碍与桌面窗口适配
> 评级理由: 本产品面向办公小白，GUI 是唯一正式产品入口；当前界面已具备完整功能骨架，但仍以表单和纵向卡片堆叠为主，视觉层级、下一步引导和高频翻译工作区均不足以支撑低学习成本的正式使用

### 原始表述

> 注意 UI 也要好好优化一下，让它更实用也更精致。design 还是保持现在的淡彩风格，但圆角可以更大些，设计可以更有个性些（例如 Google Material 3 Expressive）。也可以加入一些 UI 库来省事。

### 功能描述

将当前“一个页面中依次展开多个表单卡片”的界面升级为面向办公用户的本地翻译工作台。保留浅色、低饱和、纯色、无渐变的淡彩基调，同时借鉴 Material 3 Expressive 的设计方法：用分层大圆角、柔和色面、形状变化、清晰的主次动作和有节制的状态动效表达任务进度，不照搬 Google 产品皮肤。

核心体验围绕“当前任务和下一步动作”组织。用户进入应用后先看到最近任务、文件状态和继续入口；选择文件后，顶部任务上下文持续显示当前文件、所在阶段、保存状态和下一步；翻译阶段以原文/译文对照编辑器为主工作面，进度、失败行、思考过程和术语审核作为可展开的辅助区域；导出阶段先呈现简短检查清单，再突出下载结果。设置和术语库继续存在，但不与核心任务争夺视觉注意力。

**Direction Lock**

- 选定方向：淡彩 Expressive 桌面工作台，而不是通用后台管理模板。
- 创意姿态：探索性，在不改变产品流程和数据契约的前提下强化个性与易用性。
- 核心机制：持续可见的任务上下文、一个明确主动作、状态驱动的工作面，以及可复用的交互原语。
- 必须保留：淡彩低饱和、纯色无渐变、本地离线资源、浏览器与轻量 WebView 共用界面、桌面优先。
- 允许改变：页面信息架构、组件层级、圆角尺度、图标、动效、前端构建方式和局部组件依赖。
- 主要取舍：接受一次有边界的前端结构重整，换取后续新增状态和功能时不再继续堆叠内联样式与一次性组件。

**与既有提案的关系**

- FP-02 负责已经落地的 GUI 壳、五步流程和基础功能，FP-05 接替其“现代美观”目标，负责信息架构、视觉系统、语义组件和精细交互重构。
- FP-03 负责导出前风险分级与质量报告，FP-05 只负责这些状态的清晰呈现，不重新定义门控规则。
- FP-04 负责持久 operation journal、事件重放和译文修订历史，FP-05 只消费其状态与差异数据，不重复定义持久化契约。
- 当前 P1 已建立的 loading/error、逐行审核、富文本策略、键盘焦点和桌面窗口行为是 FP-05 必须保留的基线，而不是待重写的临时实现。

### 位置

- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L13-L22)：当前顶栏只用三个小按钮切换工作流、术语库和设置，缺少持续任务上下文与明确的信息层级。
- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L277-L335)：五步条、文件路径表单和任务列表集中在同一张纵向卡片中，新用户首先面对的是配置表单而不是“选择文件并继续”的主动作。
- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L368-L530)：AI、手工粘贴、模型设置、进度、思考和译文列表在同一页面连续展开，功能丰富但主工作面不够集中。
- [office_translate/gui/web/style.css](office_translate/gui/web/style.css#L3-L25)：现有 Token 只有单一 `6px` 圆角与极轻阴影，难以表达不同层级和更有个性的形状语言。
- [office_translate/gui/web/style.css](office_translate/gui/web/style.css#L36-L100)：页面、步骤、卡片、输入和按钮共用近似的矩形轮廓，主要依赖边框区分层级。
- [office_translate/gui/web/style.css](office_translate/gui/web/style.css#L154-L206)：翻译区采用固定 440px 高度与固定 250px 术语侧栏，桌面分屏下的空间利用和重点区域弹性有限。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L1-L160)：视图、工作流、翻译、审核、设置和模态框状态集中在单个 Vue Options 对象中，继续扩展精细交互会增加耦合与回归风险。
- [DESIGN.md](DESIGN.md#L1-L25)：当前设计文档已明确浅色、低饱和、纯色无渐变基调，但仍把统一 6px 圆角作为全局规则，需要扩展为分层形状与动效 Token。

### 方案比较

- **方案 A：只修改现有 CSS。** 把圆角调大、增加阴影和留白，成本最低，也能快速改善观感；但信息架构、内联样式、复杂模态框和高频工作区不会因此变得更易用，后续仍会继续累积一次性样式。
- **方案 B：整体采用带视觉皮肤的组件库。** Vuetify、PrimeVue 或同类库可以快速获得完整表单、弹层和布局组件；代价是默认外观容易把产品变成通用后台模板，大量主题覆盖也会抵消省下的工作量，并增加离线包体和升级约束。
- **方案 C：自定义 Expressive 视觉系统，加少量无样式或弱样式交互原语。** 保留产品自己的淡彩视觉，使用成熟库解决对话框、弹出层、选择器、焦点约束、提示和图标等容易出错的基础能力。它需要一次前端结构整理，但最能同时满足个性、可维护性和办公用户的低学习成本。

### 推荐实现方案

采用方案 C。前端继续使用 Vue 3，但允许引入开发期构建工具，把运行时产物编译成随应用分发的本地静态文件，浏览器和 WebView 启动时仍不依赖 Node 或网络。交互原语优先选择支持 Vue 3、键盘操作和焦点管理的轻量无样式组件库，再配合本地图标库；最终依赖应通过一个小型验证页面比较包体、离线构建、WebView 行为和无障碍能力，不为追求 Material 外观引入整套重皮肤。

建立分层设计 Token：控件圆角约 12px，普通卡片 16px，主工作面和模态框 24px，胶囊标签使用全圆角；间距、字号、色面、边框、阴影、形状和 120–240ms 状态动效分别定义语义 Token。大圆角不应机械地应用到每个元素，危险操作、表格密集区和小尺寸控件仍需保持清晰。所有动效支持 `prefers-reduced-motion`，状态不能只靠颜色表达，继续坚持纯色无渐变。

首个完整切片覆盖三个连续场景：

1. **任务首页。** 以拖放/选择 `.xlsx` 的主入口和最近任务卡片替代“先填写本地路径”的开发式入口。任务卡片显示文件名、阶段、最近状态和一个明确的“继续”动作，路径和高级信息放入次级详情。
2. **翻译工作区。** 顶部固定当前任务与进度，中部为可调整的原文/译文对照编辑器；失败、预览、已修改和待审核状态有一致的行级反馈。模型参数、思考过程和术语列表进入可折叠检查区，避免挤压译文主工作面。
3. **审核与导出。** 审核采用聚焦队列和明确的接受、修改、忽略动作，导出页展示检查结果、被阻断原因和两份输出的下载卡片；主要动作始终只有一个，辅助动作保持可发现但不抢占焦点。

该切片同时建立可复用的 `Button`、`Field`、`Card/Surface`、`StatusBadge`、`Progress`、`Dialog`、`Toast`、`Empty/ErrorState`、`SplitPane` 和 `ActionBar` 语义组件。组件按产品语义命名，页面不直接散布尺寸、颜色和焦点细节。视觉调整不能绕过现有 loading、empty、error、partial、cancelled、pending review 和 export blocked 状态。

验收证据包括：

- 断网启动时字体、图标、组件和样式均可完整加载，不访问 CDN。
- 900×700、1024×768、1280×800 三种桌面窗口均可完成选择文件、提取、手工翻译、审核和导出，无关键按钮被遮挡，无页面级横向滚动。
- 仅用键盘可以完成主流程；对话框具备焦点进入、约束和关闭后恢复，状态变化由 live region 提示。
- 新用户进入后第一视觉焦点是“选择文件/继续任务”，每个阶段都有唯一主动作和可理解的下一步说明。
- 翻译区在 100 条以上文本时仍以译文编辑为主，不被模型设置、思考过程或术语面板固定挤压。
- Playwright 或等价浏览器测试保存关键状态截图，覆盖空状态、进行中、部分失败、待审核、导出阻断和完成状态；视觉差异需显式审核。
- `DESIGN.md` 更新为颜色、形状、排版、间距、动效和组件状态的完整设计规范，不再只记录色板。

### 非目标与后续边界

- 不在首个切片加入深色模式、手机端布局、换肤系统、复杂动画展示或 WebView 专属业务逻辑。
- 不把 Material 3 Expressive 当作像素级复刻目标，也不使用渐变、过度弹跳或大面积高饱和色。
- 不借视觉重构修改翻译、审核和导出的业务规则；状态契约先稳定，页面再按同一契约重排。
- 组件库和构建工具只服务前端开发与产物生成，不在用户机器上要求 Node 环境。

### 最终实现情况

待实现。

---
