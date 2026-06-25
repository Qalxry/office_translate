# XLSX 翻译套件

把 Excel（`.xlsx`）里需要翻译的文本导出成「一行一条」的 TXT，人工翻译后再回填，
并额外产出「原文-译文对照版」与「仅译文版」，且**完全保留原表格的所有样式**。

## 工作流程

```
            extract                          apply
xlsx ──────────────────► source.txt ──手动翻译──► translated.txt ──────────────────► out_translated.xlsx
     └──► map.json ──────────────────────────────────────────────────────────► out_bilingual.xlsx
```

1. **extract**：解析 xlsx → 输出去重后的 `source.txt`（原文） + `map.json`（位置映射）。
2. **人工翻译**：复制 `source.txt` 为 `translated.txt` 并逐行翻译。
3. **apply**：以原 xlsx 为模板 → 把译文写回原位置，输出「仅译文」与「原文-译文对照」两份文件。

### 关键约定

- **一行一条文本**：原文本中的 `\r` `\n` 在写入 TXT 时已转义为字面 `\\r` `\\n`，
  回填时会自动还原。请在译文中遵守同样的写法（需要换行就写 `\n`）。
- **去重**：完全相同的原文只导出一次，回填时同步到所有出现位置。
- **样式保留**：apply 阶段先**物理复制原 xlsx**，再替换文本，确保字体、颜色、
  合并单元格、列宽、边框等与原文件一致。
- **仅处理字符串**：数值、布尔、公式、日期、空单元格均不导出，保持原样。

## 安装

```bash
pip install -r requirements.txt
```

## 使用

### 1) 提取

```bash
python -m xlsx_translate extract \
    -i test/original_file.xlsx \
    -t work/source.txt \
    -j work/map.json
```

### 2) 翻译

```bash
cp work/source.txt work/translated.txt
# 编辑 work/translated.txt，逐行替换为译文，保持行数与顺序不变
```

### 3) 回填

```bash
python -m xlsx_translate apply \
    -i test/original_file.xlsx \
    -j work/map.json \
    -t work/translated.txt \
    --translated work/out_translated.xlsx \
    --bilingual work/out_bilingual.xlsx
```

可选参数 `--sep` 控制对照版的分隔符，默认换行（写法 `\n`）：
```bash
--sep " || "
```

## 目录结构

```
office_translate/
├─ xlsx_translate/        # 套件包
│  ├─ __init__.py
│  ├─ __main__.py         # python -m 入口
│  ├─ cli.py              # 命令行
│  ├─ escape.py           # \r \n 转义/还原
│  ├─ extractor.py        # extract 实现
│  └─ applier.py          # apply 实现
├─ requirements.txt
├─ README.md
└─ test/
   └─ original_file.xlsx  # 测试样本
```

## 作为库调用

```python
from xlsx_translate import extract, apply

extract("test/original_file.xlsx", "work/source.txt", "work/map.json")
# ... 翻译 source.txt -> translated.txt ...
apply(
    original_xlsx="test/original_file.xlsx",
    json_path="work/map.json",
    translated_txt="work/translated.txt",
    output_translated="work/out_translated.xlsx",
    output_bilingual="work/out_bilingual.xlsx",
)
```
