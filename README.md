# office_translate

办公文档翻译套件：把文档里需要翻译的文本导出成「一行一条」的 TXT，人工翻译后再回填，
并额外产出「原文-译文对照版」与「仅译文版」，且**完全保留原文档的所有样式**。

提供**两种使用方式**：
- **图形界面（GUI）**：5 步流程（任务 → 提取 → AI 翻译 → 审核 → 回填），
  支持 AI 翻译、不确定术语人工审核、分类术语库。推荐日常使用。
- **命令行（CLI）**：手动分步执行，或 `auto` 一键翻译（适合脚本/批量）。

当前支持 **xlsx**（Excel），架构已按「格式无关核心 + 格式适配器」设计，
可扩展 **docx**（Word）、**xls** 等格式，见「扩展新格式」。

## 安装

```bash
pip install -r requirements.txt
# GUI 用原生窗口需另装（可选，不装则自动用浏览器打开）：
pip install pywebview
```

## 图形界面（推荐）

```bash
python -m office_translate gui
```

自动启动本地 Web 服务并在浏览器（或 pywebview 原生窗口）打开界面。
界面包含三个视图：

| 视图 | 功能 |
|---|---|
| **工作流** | 5 步流程：任务 → 提取 → AI 翻译 → 审核 → 回填 |
| **术语库** | 按类别浏览/新增/编辑/删除术语 |
| **设置** | AI 供应商管理、语言、并发、Google 镜像站 |

**5 步流程**（顶部步骤条，可回跳）：
1. **任务**：选择已有任务，或输入文件路径新建（支持「浏览文件」按钮唤起系统文件选择器）
2. **提取**：解析文档，生成去重原文与位置映射
3. **AI 翻译**：选引擎（Google 镜像站 / OpenAI 兼容供应商）与模型，批量翻译
4. **审核**：模型自报的不确定术语以卡片展示，可接受（选类别入库）/ 修改 / 忽略
5. **回填**：确认译文后生成「仅译文」与「原文-译文对照」两份文件

### GUI 设置

**设置**视图（打开后自动读取 `gui_settings.json`，改后自动保存）：

- **AI 供应商**：预置 OpenAI / DeepSeek / Claude（OpenAI 兼容）/ Ollama 四个，
  可新增/删除/编辑 Base URL、API Key、模型列表；点「设为使用」切换当前供应商。
- **语言**：源语言（默认 en）、目标语言（默认 zh-CN）。
- **并发数**：批量翻译并发线程数（默认 4）。
- **Google 镜像站**：失败自动切换的镜像站列表（默认三个实测可用的），
  可编辑、保存、一键「测试全部镜像站」测连通性与延迟排序。

## CLI 使用

### 手动分步

```bash
# 1) 建任务（原始文件会被复制进 work/<job>/；job 缺省时按时间戳自动命名）
python -m office_translate init eval_2024 -i "input/EVAL 2024 - Update 250210(2).xlsx"
python -m office_translate init -i "input/EVAL 2024 - Update 250210(2).xlsx"  # 自动命名

# 2) 提取原文
python -m office_translate extract eval_2024

# 3) 翻译：复制 source.txt 为 translated.txt，逐行替换为译文
cp work/eval_2024/source.txt work/eval_2024/translated.txt
# 编辑 work/eval_2024/translated.txt ...

# 4) 回填（生成 work/eval_2024/output/ 下两份 xlsx）
python -m office_translate apply eval_2024

# 5) 查看工作区任务及进度
python -m office_translate list
```

### 一键翻译（AI 自动完成）

```bash
# 用 GUI 设置里的 AI 配置（供应商/模型/镜像站）自动完成 提取→翻译→回填
python -m office_translate auto eval_2024

# 或用命令行参数覆盖
python -m office_translate auto eval_2024 --engine openai \
    --base-url https://api.deepseek.com/v1 --api-key sk-xxx --model deepseek-chat
python -m office_translate auto eval_2024 --engine google \
    --mirrors "https://google-translate-proxy.tantu.com,https://translate.renwole.com"
```

`auto` 读 `gui_settings.json`（与 GUI 共用同一套配置）；未配置时 Google 引擎用内置默认镜像站。

### 常用可选参数

| 命令 | 参数 | 说明 |
|---|---|---|
| 所有 | `-c, --config <路径>` | 指定配置文件（默认 `config.yaml`，不存在时用内置默认值） |
| init | `job` | 任务名（可省略，缺省按时间戳 `YYYYMMDD_HHMMSS` 自动生成，重名时追加 `_1`） |
| init | `--sep <SEP>` | 本任务的对照版分隔符，字面 `\n` `\r` `\t` `\\` 会还原 |
| apply | `--sep <SEP>` | 覆盖本任务分隔符，同上 |
| apply | `--translated <路径>` | 覆盖仅译文版输出路径 |
| apply | `--bilingual <路径>` | 覆盖对照版输出路径 |

## 关键约定

- **一行一条文本**：原文本中的 `\r` `\n` 在写入 TXT 时已转义为字面 `\\r` `\\n`，回填时会自动还原。译文里需要换行就写 `\n`。
- **去重**：完全相同的原文只导出一次，回填时同步到所有出现位置。
- **样式保留**：apply 阶段先**物理复制原文档**，再替换文本，确保字体、颜色、合并单元格、列宽、边框等与原文件一致。
- **仅处理字符串**：数值、布尔、公式、日期、空单元格均不导出，保持原样。
- **对照版格式**：单元格值 = 原文 + 分隔符 + 译文（分隔符默认换行）。

## 目录结构

```
office_translate/
├─ office_translate/        # 套件包
│  ├─ __init__.py           # 顶层 extract()/apply()，按扩展名分发
│  ├─ __main__.py           # python -m 入口
│  ├─ cli.py                # 命令行（init / extract / apply / auto / list / gui）
│  ├─ config.py             # 配置加载 / 任务脚手架 / 路径推导
│  ├─ base.py               # FormatAdapter 抽象基类 + 注册表
│  ├─ escape.py             # \r \n 转义/还原（格式无关）
│  ├─ glossary.py           # 分类术语库（加载/新增/匹配精简/prompt 注入）
│  ├─ ai/                   # AI 翻译模块
│  │  ├─ provider.py        # Provider + OpenAI 兼容 + Google 镜像站 + MirrorPool 切换
│  │  └─ translator.py      # 批量翻译编排 + 不确定术语 JSON 解析
│  ├─ gui/                  # 图形界面
│  │  ├─ server.py          # FastAPI REST 后端
│  │  ├─ launcher.py        # 启动服务 + 浏览器/pywebview
│  │  └─ web/index.html     # Vue 单页前端（5 步流程）
│  └─ formats/              # 格式适配器集合
│     └─ xlsx/              # xlsx 适配器（extractor + applier）
├─ config.yaml              # 全局配置（工作区/输出/分隔符）
├─ gui_settings.json        # GUI 设置（AI 供应商/镜像站/语言/并发），GUI 或 auto 生成
├─ glossary.json            # 分类术语库（审核沉淀 + 手动管理）
├─ input/                   # 原始文档（gitignore）
├─ work/                    # 工作区（gitignore），每个任务一个文件夹
│  └─ <job>/
│     ├─ job.yaml           # 任务配置
│     ├─ <原始文件>.xlsx     # init 复制的输入副本
│     ├─ source.txt         # extract 产物：去重原文
│     ├─ map.json           # extract 产物：位置映射
│     ├─ translated.txt     # 人工翻译
│     └─ output/            # apply 产物
├─ test/                    # 测试样例数据（gitignore）
├─ tests/                   # pytest 单测（自包含）
├─ requirements.txt
└─ README.md
```

## AI 翻译与术语库

**AI 翻译引擎**：
- **Google（镜像站）**：直接请求镜像站 `/translate_a/single` 端点（与官方同协议），
  默认三个实测可用的镜像站；**失败自动切换**（连续失败进入冷却，冷却后恢复），
  全部失败才报错。GUI 设置页可编辑列表并「测试全部镜像站」测速排序。
- **OpenAI 兼容**：一套代码覆盖 OpenAI / DeepSeek / Claude / Ollama 等，
  在 GUI 设置页配置供应商（Base URL + API Key + 模型列表）。

**不确定术语审核**：AI 翻译时，模型对把握不足的术语（专有名词、缩写、多义词等）
会自报为 `uncertain_terms`（含原因与候选译法），在 GUI 审核步骤以卡片展示，
可接受（选类别入术语库）/ 修改 / 忽略。Google 引擎无自报能力，直接返回译文。

**分类术语库**（`glossary.json`）：
- 术语按**类别**组织（如「汽车行业」「软件」），审核接受时选择存入类别。
- **匹配精简化**：翻译前只把「确实出现在本次待译文本中的术语」注入 prompt，
  控制上下文、减少干扰。
- **按类别选用**：翻译时可勾选使用哪些类别。
- 手动管理：GUI 术语库视图按类别浏览/新增/编辑/删除（含整类删除）。

## 配置说明

**全局配置 `config.yaml`**（缺省项用内置默认值）：

```yaml
work_dir: work      # 工作区根目录，每个翻译任务一个子文件夹
output_dir: output  # 每个任务内 apply 产物的存放子目录名
sep: '\n'           # 对照版分隔符，字面 \n \r \t 会还原为真实字符
```

**GUI 设置 `gui_settings.json`**（GUI 设置页自动生成与维护，`auto` 命令共用）：

```json
{
  "ai": {
    "engine": "google",
    "providers": {
      "openai": {"name": "OpenAI", "base_url": "...", "api_key": "", "models": ["gpt-4o-mini"]}
    },
    "active_provider": "openai",
    "mirrors": ["https://google-translate-proxy.tantu.com"],
    "source_lang": "en",
    "target_lang": "zh-CN",
    "concurrency": 4
  }
}
```

**任务配置 `work/<job>/job.yaml`**（由 init 自动生成，一般无需手改）：

```yaml
input: EVAL 2024 - Update 250210(2).xlsx  # 输入副本（相对任务目录）
source_path: /原始/文件/路径.xlsx           # 原始路径，仅供追溯
sep: '\n'                                 # 可选，覆盖全局默认
```

分隔符优先级：命令行 `--sep` > `job.yaml` 的 `sep` > `config.yaml` 的 `sep` > 内置默认 `\n`。
复制进任务目录时，文件名中的不可断行空格（U+00A0）会替换为普通空格。

## 作为库调用

```python
from office_translate import extract, apply

extract("input/sample.xlsx", "work/source.txt", "work/map.json")
# ... 翻译 source.txt -> translated.txt ...
apply(
    original="input/sample.xlsx",
    json_path="work/map.json",
    translated_txt="work/translated.txt",
    output_translated="work/out_translated.xlsx",
    output_bilingual="work/out_bilingual.xlsx",
)
```

`extract` / `apply` 按文件扩展名自动分发到对应格式适配器；对未支持的格式会抛出
`UnsupportedFormatError`（含当前支持列表）。

## .xls 旧格式处理

`.xls`（旧版 Excel 二进制格式）**不直接支持**。由于 xlutils 生态老化，就地改 .xls
会导致样式（字体、边框等）丢失，因此采用「先转 xlsx 再走现有套件」的策略：

- **Windows + 已装 Excel**：`init` 时检测到 `.xls` 输入会自动调用 PowerShell 的
  Excel COM 转换为同目录 `.xlsx`（保真度最高），然后继续正常流程。
- **其他情况**：`init` 会提示手动转换并给出操作步骤（Excel/WPS 另存为 .xlsx 后
  重新作为输入传给 init）。

## 扩展新格式

以新增 docx 为例，三步即可挂入套件，核心与 CLI 无需任何改动：

1. 新建 `office_translate/formats/docx/__init__.py`，实现 `DocxAdapter`：

   ```python
   from ...base import FormatAdapter, register_adapter

   class DocxAdapter(FormatAdapter):
       format = "docx"
       extensions = (".docx",)

       def extract(self, src_path, txt_path, json_path):
           """导出去重原文 txt 与位置映射 json（约定见 base.FormatAdapter）。"""
           ...

       def apply(self, original, json_path, translated_txt,
                 output_translated, output_bilingual, sep):
           """以 original 为模板回填译文，保留全部样式。"""
           ...

   register_adapter(DocxAdapter)
   ```

2. 在 `office_translate/formats/__init__.py` 中 `from . import docx`。
3. 完成。`init / extract / apply` 命令、顶层 `extract()` / `apply()` 自动识别 `.docx`。

适配器的两个方法可复用 `office_translate/escape.py` 的转义工具与
`xlsx/formats/xlsx/applier.py` 中「物理拷贝 + 定位回填」的思路。
