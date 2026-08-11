# SPEC Writing Rules

## Content Boundary

SPEC describes **how the system is implemented**. It is addressed to developers, code reviewers, and test engineers who need exact data structures, algorithms, interfaces, and error codes.

**SPEC MUST contain:**
- TypeScript type definitions (interface / type / enum)
- Database table schemas (SQL DDL with constraints)
- Processing algorithms (pseudocode or step-by-step)
- State machine tables (current, event, target, condition, side-effect)
- API endpoint tables (method, path, request, response, errors)
- Module interfaces and function signatures
- Error code tables (code, HTTP status, description)
- Configuration items (key, default, description)

**SPEC MUST NOT contain:**
- Large verbatim code blocks (>30 lines) — use concise pseudocode instead
- Design rationale or motivation (that belongs in PRD)
- Vague natural language where precise definitions are needed
- Duplicate type definitions across files (centralize in core-types)

## Information Density

SPEC should maximize information per line. Prefer:

| Instead of | Use |
|---|---|
| 50-line function implementation | 10-line pseudocode with numbered steps |
| Narrative paragraphs explaining flow | Numbered step lists with clear inputs/outputs |
| Inline code comments explaining "why" | A one-line note before the block |
| Full ORM query builder code | SQL query or WHERE-clause summary |

## Document Structure

```markdown
# SPEC {NN} — {模块名称}

> **版本**: V{X} | **对应 PRD**: [{name}](../prd/{file}) | **前版**: [V{X-1}](../v{x-1}/specs/{file})

---

## 1. {主题 A}
### 1.1 接口
{TypeScript interface 或函数签名}
### 1.2 处理流程
{编号步骤伪代码}

## N. 错误码
| 错误码 | 说明 |
|--------|------|
```

## TypeScript 类型规范

- 所有共享类型集中在 `01_core-types.md`
- 其他 SPEC 中只定义该模块私有的类型
- 类型定义使用 `interface`（数据结构）或 `type`（联合/交叉/别名）
- 字段注释用 `//` 行尾注释，保持紧凑
- V1 新增的字段在注释中标注 `// V1:`

```typescript
interface Task {
  id: ID;
  status: TaskStatus;
  origin_task_id: ID;             // V1: 整条链的源头
  trace_id: ID;                   // V1: 贯穿协作链
}
```

## SQL Schema 规范

- 所有 enum 列必须有 CHECK 约束
- 所有 boolean 列必须有 CHECK (col IN (0,1))
- 主要查询场景必须有对应 INDEX
- append-only 表必须有防 UPDATE/DELETE trigger
- V1 新增的表用注释标注 `-- V1 新增`

## State Machine 表格式

```markdown
| 当前 | 事件 | 目标 | 条件 | 副作用 |
|------|------|------|------|--------|
| `queued` | 调度检查 | `in_progress` | 无前置排队 | 创建 Run |
```

## API 端点表格式

```markdown
| 方法 | 路径 | 请求 | 响应 | 错误 |
|------|------|------|------|------|
| GET | `/api/nodes` | — | `Page<Node>` | — |
| POST | `/api/messages` | `{ from, to[], ... }` | `{ message_id }` 201 | 403, 404 |
```

## Processing Flow Format

使用编号伪代码，不使用完整可运行代码：

```
executeRun(taskId):
  1. 原子调度检查: CAS 校验无 active task
  2. worktreePath = acquireWorktree(nodeId, taskId)
  3. bundle = resolveBundle(nodeId, taskId)
  4. session = adapter.startSession(...)
  5. result = await session.wait()
  6. if diff → createPatchArtifact(...)
  7. Event: run.completed
```

## Error Code 规范

每个 SPEC 文件末尾有独立的错误码表。错误码格式：
- 大写下划线命名：`PERMISSION_DENIED`, `TASK_ALREADY_RUNNING`
- 每个错误码必须出现在至少一个处理流程中
- 跨模块共享的错误码也在使用它的 SPEC 中列出

## Cross-SPEC Traceability

- 每个 SPEC 文件头部标注对应的 PRD 章节
- SPEC 中的类型必须在 `01_core-types.md` 中定义
- SPEC 中的表必须在 `02_storage.md` 中定义
- 新增 Event 类型必须在 `01_core-types.md` 的 EventType 联合中声明

## Quality Criteria

- [ ] 对应 PRD 中的每个概念都有 SPEC 覆盖
- [ ] 所有类型在 core-types 中定义
- [ ] 所有表在 storage 中定义
- [ ] 所有处理流程有编号步骤
- [ ] 所有 API 端点有完整的请求/响应/错误
- [ ] 所有状态机有完整的转换表
- [ ] 所有错误码有说明
- [ ] 无超过 30 行的连续代码块
