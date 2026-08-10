# Feature Proposal: 功能提案

> 最后审计日期: 2026-08-10
> 最后编号：FP-02

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

**阶段 3：审核体验打磨**
- 不确定术语卡片：原文 / 模型译文 / 不确定原因 / 候选译法；接受（选类别入术语库）/ 修改（编辑译文）/ 拒绝（忽略）
- 审核进度条、可批量接受
- 术语库管理页：按类别浏览/编辑/删除/新增/导入导出；翻译时勾选使用类别
- 匹配精简化校验：注入前确认仅含匹配条目，避免全量注入

**风险与注意**：
- AI 批量翻译长文本（如多行单元格）需按条分隔、控制并发与限流（Google 免费端点尤其）
- 模型 JSON 输出不稳定：必须容错降级，不阻塞主流程
- 术语库冲突：同一 source 已有词条时新审核默认更新并提示（按类别维度）
- 匹配精简化需处理大小写/空白差异：同一 term 的多种形态（如 "PPB" 与 "ppb"）应统一匹配
- 密钥安全：只写本地配置，前端不直接暴露
- **镜像站限流**：实测 renwole/yifan 连发会 429，需失败切换 + 冷却；冷却期过后自动恢复，避免永久弃用
- **镜像站可用性漂移**：免费镜像站随时可能失效，GUI 设置页应有「测试全部镜像站」按钮，便于用户重新测速排序

### 最终实现情况

（未实现，待办中）
