# DESIGN.md — UI 色彩设计风格 Token

本文档整理 office_translate Web 界面当前的色彩设计风格 Token，作为后续 UI 开发与迭代的权威参考。前端已拆分为 `index.html`（结构）+ `style.css`（样式）+ `app.js`（逻辑），色彩 Token 全部定义在 `style.css` 的 `:root` 内。当前实现为**浅色、扁平、低饱和**风格，全部使用纯色，不使用任何渐变。更有个性的分层圆角、信息架构和组件体系属于 `proposals.feat.md` 的 FP-05，尚未作为本 Goal 的实现内容。

---

## 1. 设计基调

| 维度 | 取向 |
|---|---|
| 主题 | 浅色（Light） |
| 质感 | 扁平纯色，无渐变、无高光 |
| 饱和度 | 低饱和、柔和（淡蓝 / 淡绿 / 淡橙 / 淡红） |
| 对比 | 以中性灰为底，功能色仅用于状态语义，不喧宾夺主 |
| 圆角 | 统一 6px（`--radius`） |
| 阴影 | 极轻投影，仅用于卡片层级（`--shadow`） |

代码中的核心注释：`/* 无任何渐变：全部扁平纯色 */`

---

## 2. 色彩 Token 总览

所有主色通过 CSS 自定义属性（`:root` 内）定义。下表为完整色板。

### 2.1 中性色（背景 / 文字 / 边框）

| Token | 变量 | 色板 | Hex | RGB |
|---|---|---|---|---|
| 页面背景 | `--bg` | <span style="display:inline-block;width:14px;height:14px;background:#f7f8fa;border:1px solid #e3e6ea;border-radius:3px"></span> | `#f7f8fa` | `rgb(247, 248, 250)` |
| 卡片 / 面板背景 | `--card` | <span style="display:inline-block;width:14px;height:14px;background:#ffffff;border:1px solid #e3e6ea;border-radius:3px"></span> | `#ffffff` | `rgb(255, 255, 255)` |
| 边框 / 分隔线 | `--border` | <span style="display:inline-block;width:14px;height:14px;background:#e3e6ea;border:1px solid #d3d7dc;border-radius:3px"></span> | `#e3e6ea` | `rgb(227, 230, 234)` |
| 主文字 | `--text` | <span style="display:inline-block;width:14px;height:14px;background:#2c3e50;border-radius:3px"></span> | `#2c3e50` | `rgb(44, 62, 80)` |
| 次级 / 弱化文字 | `--text-dim` | <span style="display:inline-block;width:14px;height:14px;background:#7f8c9b;border-radius:3px"></span> | `#7f8c9b` | `rgb(127, 140, 155)` |

### 2.2 强调色（主色）

| Token | 变量 | 色板 | Hex | RGB |
|---|---|---|---|---|
| 主强调色 | `--accent` | <span style="display:inline-block;width:14px;height:14px;background:#5b8db8;border-radius:3px"></span> | `#5b8db8` | `rgb(91, 141, 184)` |
| 主强调色浅底 | `--accent-soft` | <span style="display:inline-block;width:14px;height:14px;background:#eaf1f7;border:1px solid #d3d7dc;border-radius:3px"></span> | `#eaf1f7` | `rgb(234, 241, 247)` |

### 2.3 功能 / 状态色

| Token | 变量 | 语义 | 色板 | Hex | RGB |
|---|---|---|---|---|---|
| 成功 / 完成 | `--ok` | 完成、通过、入库 | <span style="display:inline-block;width:14px;height:14px;background:#6da58a;border-radius:3px"></span> | `#6da58a` | `rgb(109, 165, 138)` |
| 警告 / 提示 | `--warn` | 待确认、思考、候选译法 | <span style="display:inline-block;width:14px;height:14px;background:#c9a15e;border-radius:3px"></span> | `#c9a15e` | `rgb(201, 161, 94)` |
| 错误 / 危险 | `--err` | 删除、危险操作、错误 | <span style="display:inline-block;width:14px;height:14px;background:#c07a7a;border-radius:3px"></span> | `#c07a7a` | `rgb(192, 122, 122)` |

---

### 2.4 衍生浅底 / 组件色

功能色的浅底变体与跨组件色，用于 hover、进行中、提示等弱强调场景。

| Token | 色板 | Hex | 用途 |
|---|---|---|---|
| `--bg-hover` | <span style="display:inline-block;width:14px;height:14px;background:#fafbfc;border:1px solid #e3e6ea;border-radius:3px"></span> | `#fafbfc` | 列表项 / 模型行悬停背景 |
| `--ok-soft` | <span style="display:inline-block;width:14px;height:14px;background:#e8f3ee;border:1px solid #d3d7dc;border-radius:3px"></span> | `#e8f3ee` | 成功浅底（绿色标签背景） |
| `--warn-soft` | <span style="display:inline-block;width:14px;height:14px;background:#f7efe0;border:1px solid #d3d7dc;border-radius:3px"></span> | `#f7efe0` | 警告浅底（不确定术语 chip） |
| `--err-soft` | <span style="display:inline-block;width:14px;height:14px;background:#fdf5f5;border:1px solid #d3d7dc;border-radius:3px"></span> | `#fdf5f5` | 错误浅底（危险按钮悬停、失败行） |
| `--busy-soft` | <span style="display:inline-block;width:14px;height:14px;background:#fdfcf7;border:1px solid #d3d7dc;border-radius:3px"></span> | `#fdfcf7` | 进行中浅底（翻译中行） |
| `--on-accent` | <span style="display:inline-block;width:14px;height:14px;background:#ffffff;border:1px solid #e3e6ea;border-radius:3px"></span> | `#ffffff` | 彩色底上的文字（按钮/序号/toast） |
| `--toast-bg` | <span style="display:inline-block;width:14px;height:14px;background:#333333;border-radius:3px"></span> | `#333333` | toast 提示深色背景 |
| `--overlay` | <span style="display:inline-block;width:14px;height:14px;background:rgba(0,0,0,0.4);border:1px solid #e3e6ea;border-radius:3px"></span> | `rgba(0,0,0,.4)` | 模态框遮罩 |
| `--danger` / `--danger-soft` | — | `#c07a7a` / `#fdf5f5` | 危险操作语义别名（映射 `--err` / `--err-soft`） |

---

## 3. Token 使用约定

### 3.1 `--bg` 页面背景

- `body` 整体背景。
- 步骤条未激活序号圆点的背景。
- 进度条轨道（`.progress-bar`）。
- 思考过程块（`.thinking-block`）与嵌套表单卡片（如新增术语区）。

### 3.2 `--card` 卡片背景

- `.card`、`.list`、`.map-list`、`.term-panel`、`.model-row-head`、`.model-detail` 等所有「内容面」的底色。

### 3.3 `--border` 边框

- 所有输入框、按钮、卡片、列表项、分隔线的 1px 边框。
- 滚动条轨道（`::-webkit-scrollbar-thumb`）。

### 3.4 `--text` / `--text-dim` 文字

- `--text`：正文、标题、按钮默认文字。
- `--text-dim`：描述文字、行号、元信息、占位符、标签说明、次级说明（如「`原文 → 译文`」中的原文）。

### 3.5 `--accent` / `--accent-soft` 主色

- `--accent`：激活步骤边框与序号、输入框焦点边框、主要按钮（`.btn.primary`）、进度条填充、已解析流式条目的状态强调、悬停态文字与边框、滚动条悬停色。流式协议正文不会直接显示，也不使用闪烁光标。
- `--accent-soft`：激活步骤背景、激活术语项背景、术语筛选命中的行背景、蓝色标签（`.tag.blue`）背景、激活模型行头部背景。

### 3.6 功能色 `--ok` / `--warn` / `--err`

- `--ok`：完成步骤（边框 + 序号底色）、成功按钮（`.btn.ok`）、绿色状态点（`.dot.ok`）、绿色标签文字（`.tag.green`）。
- `--warn`：警告状态点（`.dot.warn`）、思考块左侧强调边、候选译法文字（`.term-candidate`）、提示警告文字（`.hint.warn`）、影响行警告（`.rows.warn`）。
- `--err`：危险按钮（`.btn.danger`）、错误状态点（`.dot.err`）。

---

## 4. 硬编码色 Token 化状态

此前散落写死的硬编码色已全部提升为 `:root` 变量（见 2.4），规则层不再直接出现色值。仅保留 `--shadow` 内部的 `rgba(0,0,0,.05)` 作为阴影色值（未单独成 token，属预期）。

---

## 5. 相关视觉 Token

与色彩同处 `:root`、共同构成整体风格的其它 Token：

| Token | 值 | 说明 |
|---|---|---|
| `--radius` | `6px` | 当前实现的基础圆角（卡片、按钮、输入框、标签为 10px 胶囊时单独写死）；FP-05 计划改为按控件、卡片和主工作面分层定义 |
| `--shadow` | `0 1px 2px rgba(0,0,0,.05)` | 卡片轻投影 |
| 字体（正文） | `-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif` | 系统字体栈，中文优先 PingFang SC / 微软雅黑 |
| 字体（等宽） | `"Cascadia Code", Consolas, monospace` | 译文编辑、文本框等需要对齐的等宽场景 |
| 基准字号 | `14px`，行高 `1.6` | 正文基准 |

---

## 6. 来源与维护

- **样式来源文件**：`office_translate/gui/web/style.css`
  - 主色 Token：文件顶部 `:root { … }` 块。
  - 组件样式（模态框 / toast / 状态栏 / 统计网格等）追加在文件后段。
- 结构文件 `index.html` 引用 `style.css` 与 `app.js`，逻辑在 `app.js`。
- 后端 `StaticFiles` 直接服务 `web/` 目录，无 CSS 预处理器、无构建步骤。
- 修改色彩时，应优先改 `--accent`、`--ok` 等语义 Token，保持各状态一致性。

## 7. 当前交互状态约定

- 翻译条目通过 `item_preview`、`item_succeeded`、`item_failed` 等结构化状态更新，不把模型 XML、JSON 或文本协议正文直接渲染到每一行。
- 翻译列表和思考面板在用户接近底部时自动跟随；用户向上滚动后解除跟随，回到底部附近时恢复。
- `loading`、`empty`、`error`、`ready`、`partial`、`cancelled`、`pending review` 和 `export blocked` 必须有文字或结构化标识，不能只依靠颜色。
- 持久错误提供重试和诊断复制；诊断内容只包含时间、任务、操作和错误编号，不包含路径、密钥或文档正文。
- 支持桌面 900×700、1024×768 和常规桌面窗口；手机布局不属于当前产品边界。
- 同一术语影响多行时，审核卡片必须逐行展示当前译文和应用后译文，并把行级勾选作为服务端替换范围，不能用整卡接受代替用户选择。
- 富文本导出默认使用 `flatten`，直接翻译并转为纯文本，明确说明局部 run 格式会丢失；用户也可以选择 `preserve_original`，保留受影响单元格原文与局部格式。
- 模态框打开时焦点进入主要控件，Tab/Shift+Tab 约束在框内，Escape 关闭后焦点返回触发控件。
