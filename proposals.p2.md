# P2 — 次要缺陷：健壮性、可用性与工程质量

> 最后审计日期: 2026-08-14
> 最后编号：P2-06

---

## 🟢 P2-01. 内部配置与工作区路径缺少基础校验，删除结果可能误报成功

> 严重程度: 🟢 低
> 影响范围: config.yaml、job.yaml、GUI 工作区、任务删除
> 评级理由: GUI 默认不会生成多数异常值，但手工调整配置、迁移旧工作区或磁盘异常时会出现难懂错误和状态误报

### 问题描述

配置只做浅合并，没有验证 work_dir、output_dir 和 sep 的类型；例如 `work_dir: null` 会触发未捕获的 TypeError。绝对或包含 `..` 的 output_dir 可让产物意外写到任务目录外。

`load_job()` 信任 job.yaml 中的 input 和输出字段，没有确认解析后的路径仍属于当前任务。删除接口使用 `ignore_errors=True` 并无条件返回成功，目录因权限、占用或异常结构未删除时，界面仍会把任务从列表中移除。

### 位置

- [office_translate/config.py](office_translate/config.py#L32-L57)：配置没有稳定的类型和空值校验。
- [office_translate/config.py](office_translate/config.py#L122-L160)：任务输入与输出路径没有基础包含关系校验。
- [office_translate/config.py](office_translate/config.py#L163-L175)：工作区扫描会接纳未经确认的目录结构。
- [office_translate/gui/server.py](office_translate/gui/server.py#L258-L268)：忽略删除错误并固定返回成功。

### 影响

旧配置或手工修改可能导致 traceback、产物出现在意外目录，或删除失败后界面与磁盘状态不一致。它不需要按多租户或敌意文件系统建模，但会增加本地问题恢复难度。

### 推荐修复方案

加载配置和 job.yaml 时校验必要字段类型、空值和允许的相对路径；内部生成的输入与输出路径在 `resolve()` 后确认仍位于工作区/任务目录。遇到旧版或损坏配置时，GUI 应说明具体字段和修复方法。删除后检查目标是否真的消失，失败则保留界面条目并显示可重试错误。增加 null、父目录、绝对目录、损坏 job.yaml 和删除失败测试；无需扩展为复杂的权限或沙箱体系。

### 最终修复情况

待修复。

---

## 🟢 P2-05. 测试与交付基线不可复现，关键 GUI 与 XLSX 回归缺少自动验证

> 严重程度: 🟢 低
> 影响范围: 测试入口、依赖兼容、浏览器回归、XLSX 回归、桌面分发
> 评级理由: 不直接造成单次用户数据错误，但会让已发现的跨层问题在后续修改和不同电脑上反复出现

### 问题描述

`python -m pytest -q` 可运行现有测试，但直接 `pytest -q` 在审计环境收集阶段无法导入本包并出现旧工作区路径，说明测试结果依赖启动方式和残留环境。仓库没有统一的项目/pytest 配置，运行依赖只有宽松下限，也没有记录一组已验证兼容的版本。

现有 GUI 测试只调用 FastAPI，不执行 Vue、DOM、真实浏览器事件或桌面窗口布局；XLSX 往返测试也未覆盖富文本、长文本和关键复杂对象。因此本次发现的预览失效、任务恢复、SSE 状态、离线资源和格式损失无法被现有基线阻止。

### 位置

- [requirements.txt](requirements.txt#L1-L7)：运行依赖只有宽松下限，没有已验证约束集合。
- [requirements-dev.txt](requirements-dev.txt#L1-L2)：开发测试入口只列 pytest。
- [tests/test_gui.py](tests/test_gui.py#L1-L320)：GUI 测试只覆盖后端 TestClient。
- [tests/test_ai.py](tests/test_ai.py#L1-L235)：主要使用模拟 Provider，未覆盖完整结构化协议失败。
- [tests/test_roundtrip.py](tests/test_roundtrip.py#L1-L117)：未覆盖长文本、富文本和复杂 OOXML。

### 影响

开发者可能在不同环境得到不同测试结果；依赖升级可无提示改变行为；最重要的 GUI 工作流和 Excel 保真问题往往只能由用户在实际操作或打开输出文件时发现。

### 推荐修复方案

提供一个可复制的环境安装与 pytest 命令，并用项目/pytest 配置消除导入路径差异；维护一份经过验证的依赖约束文件。围绕核心桌面工作流增加少量真实浏览器 E2E：新建任务、手动/AI 翻译、失败重试、审核、刷新恢复和导出。建立精简的 XLSX 样例回归集，至少覆盖普通样式、富文本、32,767 字符边界和核心对象往返；打包时增加断网启动与最小安装冒烟测试。先保证这些高价值门禁稳定，不要求一次引入完整 lint、类型、安全和覆盖率矩阵。

### 最终修复情况

待修复。

---

## 🟢 P2-06. 术语规范化、冲突与类别选择语义不一致，且缺少面向 GUI 的导入导出

> 严重程度: 🟢 低
> 影响范围: 术语新增、跨类别冲突、翻译类别选择、术语迁移与备份
> 评级理由: 会造成部分术语规则不可预测并增加维护成本，但影响范围小于审核决策丢失和核心翻译状态错误

### 问题描述

新增术语按原始 source 精确比较，因此同一类别可以同时保存 `API` 与 `api`；匹配时却统一转为小写，并以小写 source 去重。若不同类别存在同一原文但译法不同，按排序先遇到的条目会静默胜出，用户看不到冲突。

后端把 `None` 和空类别列表都解释为“使用全部类别”。前端默认全选，但用户明确取消全部类别后发送空列表，实际仍会注入全部术语，与界面含义相反。当前 GUI 也只有逐条新增、编辑和删除，没有适合办公用户迁移、备份或批量整理术语的导入导出流程。

### 位置

- [office_translate/glossary.py](office_translate/glossary.py#L56-L83)：新增时只按原始大小写精确判重。
- [office_translate/glossary.py](office_translate/glossary.py#L94-L124)：空列表等价于全部类别，匹配按小写 source 静默去重。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L274-L303)：类别默认全选，术语只支持逐条新增。
- [office_translate/gui/web/app.js](office_translate/gui/web/app.js#L909-L925)：翻译请求直接发送当前类别选择，未区分“全部”和“一个也不选”。
- [office_translate/gui/web/index.html](office_translate/gui/web/index.html#L23-L60)：术语管理界面没有导入、导出和冲突预览。
- [proposals.feat.md](proposals.feat.md#L95-L102)：既有 GUI 功能提案已要求术语导入导出，当前实现尚未满足。

### 影响

用户可能以为禁用了术语却实际全部启用，或保存了多个看似不同、匹配时却互相覆盖的规则；跨行业类别的同名术语可能采用错误译法。大量术语只能手工维护，也不便于换电脑、备份或与现有表格协作。

### 推荐修复方案

为 source 建立统一规范化键（至少 trim、Unicode 规范化和明确的大小写策略），新增和匹配共用同一规则；出现同类别重复或跨类别不同译法时，在 GUI 中展示冲突并让用户选择。把类别状态明确建模为“全部 / 不使用术语库 / 选定类别”，空选择不得回退为全部。增加 GUI 导入导出，优先支持办公用户可编辑的 XLSX/CSV，并提供字段映射、预览、重复项处理和错误行报告；JSON 可作为完整备份格式。该条只处理术语库能力，不与 P1-05 的审核决策持久化混合。

### 最终修复情况

待修复。

---
