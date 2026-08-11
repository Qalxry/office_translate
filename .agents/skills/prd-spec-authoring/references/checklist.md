# Pre-Submission Quality Checklist

在提交 PRD/SPEC 文档给用户审阅前，逐项检查。

---

## PRD 检查

### 结构完整性
- [ ] `00_overview.md` 包含：愿景、核心原则、架构图、术语表、文档索引
- [ ] 每个 PRD 文件有 header metadata（文档类型、所属、版本、状态、日期、前版、来源）
- [ ] 每个 PRD 文件有"与其他平面的交互"章节
- [ ] 文档之间的交叉引用链接全部有效

### 内容规范
- [ ] 无 TypeScript interface / SQL / 函数签名（属于 SPEC）
- [ ] 每个新术语在 `00_overview.md` 术语表中有定义
- [ ] 每个设计选择标注了 rationale 或 source（如 FP-02 v2、P1-3）
- [ ] 数据模型使用字段表格，不使用代码

### 可视化
- [ ] 每个 PRD 至少 2 个 mermaid 图
- [ ] 架构总览使用 `graph TB/LR`
- [ ] 状态机使用 `stateDiagram-v2`
- [ ] 交互流程使用 `sequenceDiagram`

### 版本演进（如适用）
- [ ] 概述包含 V(N-1) → V(N) 变化对比表
- [ ] 每个变化标注来源（FP/P0/P1/P2）
- [ ] 明确列出"保持不变的部分"
- [ ] 前版文档已移至 `docs/v{N-1}/`

---

## SPEC 检查

### 结构完整性
- [ ] `01_core-types.md` 包含所有跨 SPEC 共享类型
- [ ] `02_storage.md` 包含完整 SQL DDL
- [ ] 每个 SPEC 文件标注对应 PRD 章节
- [ ] 每个 SPEC 末尾有错误码表

### 类型一致性
- [ ] 所有 SPEC 引用的类型在 core-types 中存在
- [ ] 所有 SPEC 引用的表在 storage 中存在
- [ ] 新增 EventType 在 core-types 的联合类型中声明
- [ ] V1 新增字段用 `// V1:` 注释标注

### SQL Schema
- [ ] 所有 enum 列有 CHECK 约束
- [ ] 所有 boolean 列有 CHECK (col IN (0,1))
- [ ] 主要查询场景有 INDEX
- [ ] append-only 表有防 UPDATE/DELETE trigger

### 处理流程
- [ ] 所有流程使用编号步骤伪代码
- [ ] 无超过 30 行的连续代码块
- [ ] 每个步骤的输入/输出/副作用清晰
- [ ] 错误路径有明确处理

### API
- [ ] 所有端点有 method/path/request/response/errors
- [ ] 列表端点统一支持分页参数
- [ ] 认证要求声明
- [ ] WebSocket 协议有消息类型表

---

## 交叉验证

- [ ] PRD 中每个概念在 SPEC 中有对应实现定义
- [ ] SPEC 中没有引入 PRD 未定义的概念
- [ ] PRD 的 mermaid 状态机与 SPEC 的状态转换表一致
- [ ] PRD 的数据模型字段表与 SPEC 的 TypeScript interface 字段对应
- [ ] API 端点在 PRD 概述中有提及，在 SPEC 中有完整定义

---

## 交付材料

- [ ] 所有文件 `wc -l` 和 `du -sh` 统计
- [ ] 汇总表：文件名、行数、大小、内容摘要
- [ ] 无残留的 `.part*.md` 临时文件
