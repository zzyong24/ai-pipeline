# ai-pipeline — Claude Code 规范入口

> 本项目采用 AIES (AI Engineering Scaffold) 管理 AI 工程化。
> 所有代码生成行为必须先加载本文件指向的规范。

---

## 项目背景（一分钟了解）

`ai-pipeline` 是内容创作流水线库，用 LangGraph 搭建：

- **SubGraph 作为可复用组件**（不走 MCP 暴露）
- **主 Graph 只做编排**（业务逻辑全在 SubGraph）
- **Hermes 通过 Claude Code MCP 调度本项目开发**

当前已完成：3 个 SubGraph（research / transcribe / write_book）+ 1 个 Pipeline（`01-video-md`）。
Roadmap：项目工程化底座、Langfuse 接入、MCP Server、第二个 Pipeline 复用验证。

---

## 必读文件（每次会话开始）

Claude Code 的 SessionStart Hook 会自动注入以下文件。如未启用 Hook，请 AI 在对话开始时主动读取：

1. `.aies/workflow.md` — 工作流（Phase 1/2/3 协议）
2. `.aies/spec/index.md` — 规范导航
3. `.aies/spec/architecture.md` — **本项目最关键**（SubGraph 架构约束）
4. `.aies/spec/code-style.md` — Python / LangGraph 代码风格
5. `.ai/index.md` — 项目地图
6. `.ai/review-checklist.md` — 审查清单
7. `HERMES_TASK.md` — Hermes 的施工说明书（了解 roadmap 背景）

---

## 每次任务的强制协议

### Phase 1：启动清单（写代码前第一段输出）

```
📋 任务启动清单
━━━━━━━━━━━━━━
• 任务类型：[新增 SubGraph / 新增 Pipeline / 修改 SubGraph / 修改主 Graph / 修复 Bug / 其他]
• 需读取的参考文件：[按 .ai/context-guide.md 列出]
• 涉及的规范要点：[从 .aies/spec/architecture.md 列出]
• 预计变更文件：[列出]
• 索引需更新：[是 / 否]
• 已知技术债相关项：[从 .ai/known-issues.md 查询]
```

### Phase 2：执行

按清单读取参考文件 → 生成代码。
**特别注意 LangGraph 反模式**（见 `code-style.md` 第十节）：
- `List[Send]` 只能从 conditional edge 返回
- 并行字段必须有 Reducer
- 每任务独立 `task-{idx}/` 目录
- SubGraph 不读环境变量（走 Config）

### Phase 3：完成清单（写完代码后必须输出）

```
✅ 任务完成清单
━━━━━━━━━━━━━━
1. 质量自检（参照 .ai/review-checklist.md 10 大维度）
2. 索引更新：[已更新 .ai/index.md / 无需]
3. 建议 commit message：`type(scope): 描述 [ai-assisted]`
4. 会话日志：python3 .aies/scripts/session.py add --title "..." --summary "..."
5. Spec 缺口：[有/无新约定需沉淀]
6. 技术债更新：[是否需要更新 .ai/known-issues.md]
```

---

## 任务场景 Quick Reference

| 用户说... | AI 应该读 | 参考模板 |
|----------|---------|---------|
| 新增 SubGraph | `.aies/spec/architecture.md` + `.ai/context-guide.md` 场景 1 | `subgraphs/research_subgraph/` |
| 新增 Pipeline | `.aies/spec/architecture.md` + `.ai/context-guide.md` 场景 2 | `01-video-md/main_graph.py` |
| 修改 fan-out | `code-style.md` 反模式 + `.ai/context-guide.md` 场景 4 | `route_dispatcher` |
| 接入 Langfuse | `.ai/known-issues.md` #9 + `subgraphs/shared/llm.py` | — |
| 接入 MCP Server | `.ai/known-issues.md` #11 + HERMES_TASK.md 阶段 4 | — |
| Bug 修复 | `.ai/known-issues.md` + 出问题文件 + 调用方 | — |

---

## Slash 命令

| 命令 | 作用 |
|------|------|
| `/aies:start` | 初始化会话（读上下文 + 规范） |
| `/aies:finish-work` | 完成清单 |

---

## 辅助脚本

```bash
# 查看当前上下文
python3 .aies/scripts/session.py get-context

# 任务管理
python3 .aies/scripts/task.py list
python3 .aies/scripts/task.py create "任务标题" --slug xxx

# 会话结束后记录日志
python3 .aies/scripts/session.py add \
    --title "..." \
    --commit "$(git rev-parse --short HEAD)" \
    --summary "..."
```

---

## 禁止事项

- ❌ 跳过 Phase 1 直接写代码
- ❌ 违反 `architecture.md` 约束（主 Graph 写业务 / SubGraph 依赖 Pipeline / `List[Send]` 从 node 返回 / 并行字段无 Reducer）
- ❌ `git commit/push/merge` 未经用户确认
- ❌ 编造项目中不存在的 SubGraph / node / State 字段（必须先读 `.ai/index.md` 确认）
- ❌ 大段重写 `main_graph.py` 或 SubGraph（除非用户明确要求重构）
- ❌ 硬编码 `/Users/zyongzhu/...` 路径（已存在的是技术债，新增代码不得出现）
