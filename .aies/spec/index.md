# ai-pipeline 规范索引

> 所有 AI 开发任务**必须**在写代码前先阅读相关 Spec 文件。
> 本文件是规范导航，按任务类型选择性读取，遵循「最小充分上下文」原则。

---

## 项目概览

| 项 | 值 |
|----|-----|
| 技术栈 | Python 3.10+ / LangGraph / LangChain / Langfuse / MCP |
| 架构模式 | SubGraph 组件化 + 主 Graph 编排 |
| 持久化 | SqliteSaver（LangGraph Checkpointer） |
| 可观测 | Langfuse（LLM trace/cost） + LangGraph Studio（调试） |
| 最后更新 | 2026-04-24 |

---

## Spec 清单

| Spec | 适用场景 | 必读时机 |
|------|---------|---------|
| [architecture.md](./architecture.md) | **SubGraph 设计约束 / 主 Graph 编排 / fan-out 规则** | **每次写代码前**（本项目最关键） |
| [code-style.md](./code-style.md) | Python / LangGraph 命名、注释、类型、反模式 | **每次写代码前** |
| [quality-gates.md](./quality-gates.md) | 禁止模式、必须模式、自检清单 | 每次写代码前 |
| [testing.md](./testing.md) | 单元测试、E2E、acceptance.md 规范 | **每次新增任务时、implement 前** |
| [error-handling.md](./error-handling.md) | 错误处理、异常传递 | 涉及错误处理时 |
| [logging.md](./logging.md) | 日志级别、格式、前缀 | 涉及日志时 |
| **外部规范** | `vault/space/crafted/study/langgraph-subgraph/subgraph-design-spec.md` | SubGraph 相关任务必读（待迁入仓库，见 `.ai/known-issues.md` #1） |

---

## Thinking Guides（动手前思维检查）

> 不是规范，是**防踩坑的思维框架**。遇到对应场景花 5 分钟读一遍。

| Guide | 适用场景 |
|-------|---------|
| [guides/code-reuse.md](./guides/code-reuse.md) | 新增 SubGraph / Node / 工具函数前，先搜索是否已有类似实现 |
| [guides/cross-layer.md](./guides/cross-layer.md) | 跨 SubGraph / 主 Graph 调用时，检查依赖方向和 State 边界 |
| [guides/auth-context.md](./guides/auth-context.md) | 涉及 LLM 配置、Langfuse token、API key 透传时 |

---

## 开发前必读清单

```bash
# 每次任务开始前按顺序读取：
cat .aies/spec/index.md              # 本文件
cat .aies/spec/architecture.md       # SubGraph 架构约束（最重要）
cat .aies/spec/code-style.md         # Python / LangGraph 风格
cat .aies/spec/testing.md            # 测试规范（新增任务时必读）

# 按任务类型额外读取（详见 .ai/context-guide.md）：
# 新增 SubGraph  → architecture.md 的 SubGraph 设计约束章节
# 新增 Pipeline  → architecture.md 的主 Graph 编排章节
# Bug 修复      → .ai/known-issues.md
```

---

## 任务启动检查清单

```
📋 任务启动清单
━━━━━━━━━━━━━━
• 任务类型：[新增 SubGraph / 新增 Pipeline / 修改 SubGraph / 修改主 Graph / Bug 修复 / 其他]
• 需读取的规范：[读 context.jsonl 的 phase=implement 条目，或按 .ai/context-guide.md]
• 涉及的 Thinking Guide：[新增组件→code-reuse / 跨层→cross-layer / config透传→auth-context]
• 预计变更文件：[列出]
• 已知技术债关联：[从 .ai/known-issues.md 查询]
```

---

## 任务完成检查清单

```
✅ 任务完成清单
━━━━━━━━━━━━━━
1. 质量自检（10 大维度，见 .ai/review-checklist.md）：
   - [ ] 架构合规（SubGraph 独立、主 Graph 仅编排）
   - [ ] LangGraph 特定（List[Send] 位置、Reducer、NodeInterrupt）
   - [ ] 数据完整性（thread_id、任务隔离、失败 State）
   - [ ] 边界条件（0/1/N 任务、SubGraph 异常）
   - [ ] 错误处理（try/except 包 invoke、日志含上下文）
   - [ ] 性能（SubGraph 单例、并发限制）
   - [ ] 日志（[模块:node] 前缀、无敏感信息）
   - [ ] Python 风格（pathlib、无硬编码路径、docstring）
   - [ ] AI 常见盲区（硬编码路径、遗漏 Reducer）
   - [ ] 文档更新（index.md / changelog.md / README.md）
2. 测试验收（参照 acceptance.md）：
   - [ ] 单元测试全部通过（pytest tests/unit/ -v）
   - [ ] E2E Happy Path 通过
   - [ ] acceptance.md 中所有 P0 验收场景打勾
3. 索引更新：[已更新 .ai/index.md / 无需]
4. 建议 commit message：`type(scope): 描述 [ai-assisted]`
5. ⭐ Spec 回流（强制，不可跳过）：
   Q1: 本次有没有"应该统一规范"的地方？[有/无]
   Q2: 有没有踩坑（LangGraph 陷阱/Python 边界），下次需要提前规避？[有/无]
   Q3: spec/guides/ 是否需要新增场景？[有/无]
   → 有则直接修改对应 spec 文件，在 .ai/changelog.md 追加一行
   → 无则明确写"Spec 回流：无新约定"
```

---

## 规范维护规则

1. **发现新约定 → 24 小时内进入 Spec**
2. **修改 Spec 必须在 `.ai/changelog.md` 记录**
3. **Spec 使用「强制」/「建议」标签清晰区分**
4. **示例代码使用 ✅/❌ 对比呈现**
5. **LangGraph 反模式累积在 `code-style.md` 第十节**（项目血泪史）
