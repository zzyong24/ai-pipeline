---
description: AIES (AI Engineering Scaffold) — 项目级 AI 行为规范（CodeBuddy 自动加载）
alwaysApply: true
enabled: true
---

# {{PROJECT_NAME}} — CodeBuddy AI 规范

> 本规则每次对话自动加载。AI 必须严格遵守。

---

## 零、强制执行协议（最高优先级）

任何代码修改任务，必须先完成本协议，再写代码：

```
收到任务 → 【Phase 1: 启动清单】→ 【Phase 2: 执行】→ 【Phase 3: 完成清单】
```

### Phase 1：启动清单（写代码前第一段输出）

```
📋 任务启动清单
━━━━━━━━━━━━━━
• 任务类型：[新增 / 修改 / 修复 / 重构 / 其他]
• 需读取的参考文件：[按 .ai/context-guide.md 列出]
• 涉及的规范要点：[从 .aies/spec/ 列出]
• 预计变更文件：[列出]
• 索引需更新：[是 / 否]
```

**跳过此清单直接写代码视为严重违规。**

### Phase 3：完成清单（写完代码后必须输出）

```
✅ 任务完成清单
━━━━━━━━━━━━━━
1. 质量自检（参照 .ai/review-checklist.md 9 大维度）
2. 索引更新：[已更新 .ai/index.md / 无需]
3. 建议 commit message：`type(scope): 描述 [ai-assisted]`
4. 会话日志命令（用户复制即可执行）：
   python3 .aies/scripts/session.py add \
       --title "..." \
       --commit "$(git rev-parse --short HEAD)" \
       --summary "..."
5. Spec 缺口沉淀：[有/无新约定需沉淀]
```

---

## 一、规范体系

| 文件 | 作用 |
|------|------|
| `.aies/workflow.md` | 工作流说明 |
| `.aies/spec/index.md` | 规范导航 |
| `.aies/spec/architecture.md` | 架构约束 |
| `.aies/spec/code-style.md` | 代码风格 |
| `.aies/spec/quality-gates.md` | 质量门 |
| `.aies/spec/error-handling.md` | 错误处理 |
| `.aies/spec/logging.md` | 日志规范 |
| `.ai/index.md` | 项目地图 |
| `.ai/review-checklist.md` | 审查清单 |
| `.ai/context-guide.md` | 场景上下文指南 |
| `.ai/glossary.md` | 业务术语表 |
| `.ai/known-issues.md` | 已知技术债 |
| `.ai/prompts/` | Prompt 模板 |

---

## 二、上下文参考（强制）

收到任务时，AI 必须先识别场景，**主动读取**对应参考文件：

| 场景 | 必须读取 |
|------|---------|
| 新增功能 | `.ai/context-guide.md` 场景 1 指定的文件 |
| 修改现有功能 | `.ai/context-guide.md` 场景 2 指定的文件 |
| Bug 修复 | `.ai/index.md` + `.ai/known-issues.md` + 出问题文件 + 调用方 |
| Code Review | `.ai/review-checklist.md` + 待审查文件 |

**上下文不足时禁止猜测**：必须先读取文件，不得凭空编写。

---

## 三、索引自维护（强制）

以下变更**必须在同一次回复中直接更新 `.ai/index.md`**：

- 新增或删除文件/目录
- 新增、修改、删除 API 路由
- 新增或修改数据模型/表结构
- 新增或修改模块调用关系

同时更新 `.ai/changelog.md`。

---

## 四、质量自检（强制）

每次生成代码后按 9 维度自检（详见 `.ai/review-checklist.md`）：

1. 架构合规
2. 数据安全
3. 数据完整性
4. 边界条件
5. 错误处理
6. 性能
7. 日志与可观测性
8. AI 常见盲区
9. 测试覆盖

---

## 五、Prompt 模板触发

| 用户意图 | AI 必须读取的模板 |
|---------|----------------|
| 新增功能 / API | `.ai/prompts/new-feature.md` |
| 修复 Bug | `.ai/prompts/fix-bug.md` |
| Code Review | `.ai/prompts/code-review.md` |
| 提交代码 | `.ai/prompts/git-commit.md` |
| 重构 | `.ai/prompts/refactor.md` |

用户只需描述需求，AI 自行完成「读模板 → 读参考文件 → 执行」全流程。

---

## 六、禁止事项

- ❌ 跳过 Phase 1 启动清单
- ❌ 完成后不更新 `.ai/index.md`
- ❌ 编造项目中不存在的函数/类型/字段
- ❌ 大段重写用户未要求的代码
- ❌ `git commit/push` 未经用户确认
- ❌ 在 AI 消息中输出大段代码而非使用编辑工具
