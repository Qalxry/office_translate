# PRD Writing Rules

## Content Boundary

PRD describes **what the system does** and **why it does it that way**. It is addressed to product owners, architects, and senior engineers who need to understand the system design without implementation details.

**PRD MUST contain:**
- Problem statement and motivation for each design
- Conceptual data models (as field tables, not code)
- Behavioral rules in natural language
- State machines and process flows (as mermaid diagrams)
- Design decisions with rationale or source reference
- Scope boundaries (what's in, what's out, what's deferred)
- Cross-references to related PRD sections

**PRD MUST NOT contain:**
- TypeScript interfaces or code blocks
- SQL schemas
- Function signatures or pseudocode
- Implementation algorithms
- Error codes (beyond conceptual error scenarios)
- Package names or import paths

## Document Structure

Each PRD file follows this structure:

```markdown
# PRD {NN} — {平面/模块名称}

> **文档类型**: Product Requirements Document (PRD)
> **所属**: [AgentOrg V{X} 总览](./00_overview.md) > {Plane Name}
> **版本**: V{X}
> **状态**: 设计中
> **最后更新**: {YYYY-MM-DD}
> **前版**: [V{X-1} {名称}](../v{x-1}/prd/{file})（如有）
> **设计来源**: {FP-xx / Px-xx / V0 / 无}

---

## 1. 概述
{模块的职责、V0→V1 变化矩阵（如有）、架构总览 mermaid 图}

## 2-N. 各子主题
{每个子主题一个一级章节}

## N+1. 与其他平面的交互
{mermaid graph 展示依赖关系}

## N+2. 边界情况与约束（可选）
{本 PRD 定义的 / 不定义的 / 待讨论的}
```

## Data Model Presentation

使用表格描述字段，不使用 TypeScript interface：

```markdown
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 唯一标识符，不可变 |
| `name` | string | ✅ | 显示名称，可修改 |
| `status` | enum | ✅ | 当前状态：`idle` / `busy` / `error` |
```

## Mermaid 使用规范

每个 PRD 文件至少包含以下 mermaid 图中的两种：

| 图类型 | 用途 | 关键场景 |
|--------|------|---------|
| `graph TB/LR` | 架构/组件关系 | 模块概览、平面间交互 |
| `stateDiagram-v2` | 状态机 | 实体生命周期 |
| `sequenceDiagram` | 时序交互 | 跨组件协作流程 |
| `flowchart TD` | 决策流程 | 路由逻辑、条件分支 |

## Version Evolution

当从 V(N-1) 升级到 V(N) 时，每个 PRD 文件的概述部分必须包含变化对比表：

```markdown
| 维度 | V0 | V1 | 变化来源 |
|------|----|----|---------|
| **协作原语** | `send_message` | `ask/delegate/dispatch` | FP-02 v2 |
```

## Terminology Discipline

- 首次使用的专有术语必须在 `00_overview.md` 的术语表中定义
- 术语表按概念域分组，不按字母排序
- 术语定义必须是一句话，不超过两行
- 后续 PRD 文件中使用术语时，首次出现可加粗标注

## Cross-Reference Format

引用同目录其他 PRD：`[02_collaboration.md](./02_collaboration.md)`
引用 SPEC：`见 SPEC 阶段定义` 或 `详见 [SPEC 05](../specs/05_task-execution.md)`
引用 proposal：`（来源：FP-02 v2）`
引用前版：`[V0 对话平面](../v0/prd/02_conversation.md)`

## Quality Criteria

- [ ] 每个设计选择都有 rationale 或 source reference
- [ ] 无 TypeScript 代码或 SQL
- [ ] 每个新专有术语都在术语表中
- [ ] 至少 2 个 mermaid 图
- [ ] 有"与其他平面的交互"章节
- [ ] 有明确的范围边界声明
