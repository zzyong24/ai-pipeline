# AIES 工作流

> 本工程采用 **AI Engineering Scaffold (AIES)** 的统一工作流。所有 AI 助手（Claude Code / Cursor / CodeBuddy / Copilot / Codex）都按本文件执行。

---

## 核心原则

1. **读规范再动手** —— 每次会话开始必须读取 `.aies/spec/index.md`
2. **结构化输出** —— 每个任务必须输出 Phase 1/3 清单（详见下文）
3. **增量推进** —— 单次任务只做一件事
4. **留下痕迹** —— 任务完成后更新 `.ai/index.md` + 追加会话日志

---

## 每次会话的标准流程

### Phase 0：会话初始化（一次性）

```bash
# 1. 初始化开发者身份（首次使用时）
python3 .aies/scripts/init-developer.py your-name

# 2. 获取当前上下文
python3 .aies/scripts/session.py get-context
```

上下文脚本会输出：
- 当前开发者身份
- 活跃任务列表
- 最近 git 状态
- 最近 3 条会话日志

### Phase 1：任务启动清单（每次写代码前）

AI 收到任务后**第一段输出**必须是：

```
📋 任务启动清单
━━━━━━━━━━━━━━
• 任务类型：[新增/修改/修复/重构/其他]
• 绑定任务：[task.json title，或 "即时任务"]
• 需读取的参考文件：[按 .ai/context-guide.md 列出]
• 涉及的规范要点：[从 .aies/spec/ 列出相关强制项]
• 预计变更文件：[将要修改/新增的文件]
• 索引需更新：[是/否]
```

**跳过此清单直接写代码视为严重违规。**

### Phase 2：执行

按 Phase 1 清单逐项执行：
1. 读取参考文件
2. 按 `.aies/spec/` 规范生成代码
3. 生成过程中主动指出潜在风险
4. 关键决策处补充「为什么这样做」的注释

### Phase 3：任务完成清单（每次写完代码后）

代码完成后必须输出：

```
✅ 任务完成清单
━━━━━━━━━━━━━━
1. 质量自检（参照 .ai/review-checklist.md）：
   - [ ] 架构合规
   - [ ] 错误处理
   - [ ] 安全检查
   - [ ] 性能检查
   - [ ] 日志规范
   - [ ] AI 常见盲区
   - [ ] 编译/类型检查通过
2. 索引更新：[已更新 .ai/index.md / 无需更新]
3. 建议 commit message：`type(scope): 描述 [ai-assisted]`
4. 会话日志建议：`python3 .aies/scripts/session.py add --title "..." --summary "..."`
5. Spec 缺口沉淀：[是否发现新约定需要沉淀到 .aies/spec/]
```

### Phase 4：会话结束（手动触发）

```bash
# 完成代码提交后，记录会话日志
python3 .aies/scripts/session.py add \
    --title "本次会话标题" \
    --commit "$(git rev-parse --short HEAD)" \
    --summary "变更摘要：做了什么，改了哪些文件，关键决策"
```

---

## 任务管理

### 创建任务

```bash
python3 .aies/scripts/task.py create "任务标题" --slug task-slug
```

会在 `.aies/tasks/` 下生成：
```
.aies/tasks/{MM-DD-slug}/
└── task.json
```

### 查看任务

```bash
python3 .aies/scripts/task.py list           # 活跃任务
python3 .aies/scripts/task.py list-archive   # 已归档任务
```

### 归档任务

```bash
python3 .aies/scripts/task.py archive task-slug
```

---

## 会话日志

### 结构

```
.aies/workspace/{developer}/
├── index.md          # 个人索引（自动维护）
├── journal-1.md      # 日志文件（单文件 ≤ 2000 行）
├── journal-2.md      # 超过 2000 行自动切换
└── ...
```

### 日志条目格式

每个会话追加一段：

```markdown
## [时间戳] 会话标题

**Commit**: abc1234
**摘要**: ...

### 关键决策
- ...

### 变更文件
- ...
```

---

## 规范沉淀原则

**发现新约定 → 24 小时内进入 Spec**，不能只在对话中说一次。

流程：
1. AI 或人发现「这个模式应该统一」
2. 判断归属：
   - 架构/分层 → `.aies/spec/architecture.md`
   - 代码风格 → `.aies/spec/code-style.md`
   - 错误处理 → `.aies/spec/error-handling.md`
   - 质量门 → `.aies/spec/quality-gates.md`
3. AI 直接修改对应 Spec 文件
4. 在 `.ai/changelog.md` 追加一行

---

## 禁止事项

- ❌ 跳过 Phase 1 清单直接写代码
- ❌ 完成后不更新 `.ai/index.md`
- ❌ 大段重写用户未要求的代码
- ❌ 生成代码时编造项目中不存在的函数/类型（必须先读 `.ai/index.md` 确认）
- ❌ 日志日期混乱、多个 journal 并行追加
- ❌ `git commit`/`git push` 未经用户确认
