# GUI 内部契约

本文档记录本地 GUI 与后端之间的当前版本契约。它不是对外维护的 Python API；用户通过 GUI 完成全部流程。

## 运行边界

- 启动器只绑定回环地址（IPv4/IPv6 loopback）。
- 静态页面与 REST/SSE 使用同源地址，不启用通配 CORS。
- Vue 运行时位于 `office_translate/gui/web/vendor/`，页面不依赖 CDN。
- `data/logs/office_translate.log` 使用滚动文件，只记录操作、任务和错误编号；不记录 API Key、请求正文或用户文档内容。

## 设置

`GET /api/settings` 返回可供界面展示的设置快照。供应商对象不含 `api_key`，只包含：

```json
{
  "api_key_masked": "••••••••test",
  "api_key_configured": true
}
```

`PUT /api/settings` 在单个 `SettingsStore.update()` 事务中完成读、合并、校验和原子替换。省略供应商 `api_key` 表示保留后端已有密钥；只有用户显式提交的新值才会更新密钥。翻译和连接测试提交供应商 ID，由后端从本地设置解析密钥。

## 任务产物

GUI 内部真相源是任务 manifest 引用的结构化版本产物：

- `SourceArtifact`：输入摘要、稳定 `source_revision`、带 ID 的原文和单元格位置；
- `TranslationArtifact`：`source_revision`、`translation_revision`、逐项译文状态、审核决策和脱敏诊断；
- `OperationSummary`：成功、失败和取消 ID 集合，计数必须守恒。

保存译文必须提交当前 `source_revision`、完整 ID 集合和 summary。导出还必须提交当前 `translation_revision`，且 summary 为完整 `succeeded`。重新提取会使旧译文、审核状态和输出失效。当前版本不读取旧 schema 或旧模型输出。

## SSE 翻译事件

`POST /api/translate/stream` 返回事件流：

| 事件 | 用途 |
|---|---|
| `meta` | 总数、分块和术语匹配信息 |
| `thinking` | 思考过程增量 |
| `item_preview` | 已解析的逐条预览，不是原始协议正文 |
| `item_succeeded` | 终态校验后的成功项 |
| `item_failed` | 明确失败项和错误编号 |
| `progress` | 已完成项和总数 |
| `summary` | 唯一最终事件，决定是否可以保存/导出 |

断流、畸形事件、拒答、截断、缺失/重复/未知 ID 都不能生成伪成功 summary。合法的已完成条目可以保留为成功，缺失条目进入失败，partial 结果不可导出。

`POST /api/operations/{operation_id}/cancel` 只保证本地不再提交后续成功状态。供应商已经收到的请求可能继续执行并计费，界面必须如实提示这一限制。

## 模型内容协议

模型级 `output_format` 有 `xml`（默认）、`json`、`text` 三种。模型传输层的 `response_format` 是独立选项，默认值为 `none`；仅 JSON 内容协议可以显式使用 `json_object` 或 `json_schema`。普通 JSON 流可以在每个 `items[]` 元素闭合后发出逐条预览；结构化响应是否分块发送取决于供应商，部分服务会整包返回。

- JSON 使用严格的 `items[]` 和稳定 `id`。
- XML 使用带 ID 的 `<items><item>...</item></items>`。
- 文本按输入顺序一行一条；行内非普通空格的空白字符使用 `\n`、`\r`、`\t` 和 `\\` 等字面转义。

前端只展示解析后的 item，不展示 XML/JSON 原文，也不通过换行拆分内部真实多行译文。

## 审核与导出

`GET /api/jobs/{job}/review` 返回聚合审核卡片。`row_ids` 是该卡片允许作用的完整行范围，`selected_row_ids` 是用户明确选择修改的子集。`PUT /api/jobs/{job}/review` 必须完整提交当前审核项，并为每项携带 `selected_row_ids`、当前 `source_revision` 和 `translation_revision`；服务端拒绝缺失、越界、重复或过期的行选择，只修改 `selected_row_ids` 中的译文。

`POST /api/jobs/{job}/apply` 需要当前 source/translation revision，并接受 `rich_text_policy`：

- `flatten`：默认值。用纯文本译文替换整个富文本单元格，单元格内的局部字体、颜色等格式会丢失。
- `preserve_original`：受影响单元格保留原文与局部格式，不写入译文；其他单元格正常导出。

任一输出最终单元格超过 32,767 字符时，或任一候选文件验证失败时，两份输出都不会发布。
