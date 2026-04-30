# AIES 工作流

> **定位**：这是一个 Agent 驱动的工作流。人提供意图，Agent 驱动执行，在关键节点暂停等待人拍板。

---

## 核心模式

```
人描述意图
    ↓
Agent 解析（读 .ai/index.md 确认上下文）
    ↓
Agent 驱动任务创建 + 填 prd + 填 acceptance
    ↓
⏸️ 暂停 — 展示提议，等待人确认
    ↓
Agent 实现 + 自检
    ↓
⏸️ 暂停 — Spec 回流展示，等待人拍板
    ↓
Agent 写日志 + 归档任务
```

**人介入的两个点**：
1. 确认 prd + acceptance（定义"做什么"和"做好的标准"）
2. 确认 Spec 回流（决定"这次的经验要不要沉淀"）

其余所有步骤由 Agent 自主执行。

---

## 任务生命周期

### Phase 0：会话初始化

Session Start Hook 自动检测：
- `.aies/` 是否存在 → 不存在则提示 `/aies:bootstrap`
- 开发者身份是否存在 → 不存在则询问并初始化
- 活跃任务列表 → 有则展示，问是否继续

### Phase 1：意图接收与任务创建（由 `/aies:task` 驱动）

Agent 执行：
1. 解析用户意图（不问问题，直接解析）
2. 创建任务目录：`python3 .aies/scripts/task.py create "{title}" --slug {slug}`
3. 填写 `prd.md`（Agent 主动写，不留 TODO）
4. 填写 `acceptance.md`（参考 spec/guides/ 推导边界场景）
5. 生成 `context.jsonl`（按任务类型精准指定需要的 spec）
6. **展示提议，等待人确认** ← 唯一的人介入点

提议格式：
```
📋 我的理解：{一句话}
✅ 验收标准（{N}条）：{列表}
❓ 不确定点（{N}个）：{列表}
说 "ok" 开始，或告诉我哪里要改。
```

### Phase 2：实现（由 `implement` agent 驱动）

Agent 执行：
1. 读 `context.jsonl` → 加载指定 spec（不全量读）
2. 检查 `spec/guides/` 中相关的 Thinking Guide
3. 读 `.ai/index.md` → 确认函数/类型真实存在（禁止编造）
4. 按 spec 约束实现代码
5. 关键决策处写 "为什么" 注释
6. 自检：build / lint / test

### Phase 3：完成收尾（由 `/aies:finish` 驱动）

Agent 自动执行（无需人触发）：
1. 对照 `acceptance.md` P0 场景逐条确认
2. 对照 `review-checklist.md` 9 大维度自检
3. 更新 `.ai/index.md`（如有新增文件/接口）

Spec 回流（**必须展示给人确认**）：
```
Q1: 有没有"应该统一规范"的地方？→ {分析}
Q2: 有没有踩坑要记录？→ {分析}
Q3: guides/ 需要新增场景吗？→ {分析}
```
有则展示 diff → 人确认 → Agent 写入 spec + changelog
无则明确输出"Spec 回流：无新约定"

Agent 自动执行收尾：
- `python3 .aies/scripts/session.py add --title "..." --summary "..."`
- `python3 .aies/scripts/task.py finish {slug}`
- 输出 commit message 建议（等用户说"提交"再执行）

---

## 上下文文件职责

| 文件 | 谁写 | 谁读 | 内容 |
|------|------|------|------|
| `.aies/spec/*.md` | Agent（Spec 回流时）| Agent（每次任务）| 编码约束 |
| `.aies/spec/guides/*.md` | Agent（回流时）| Agent（动手前）| 踩坑防范 |
| `.aies/tasks/{slug}/prd.md` | **Agent 填，人确认** | Agent | 需求背景 |
| `.aies/tasks/{slug}/acceptance.md` | **Agent 填，人确认** | Agent | 验收标准 |
| `.aies/tasks/{slug}/context.jsonl` | Agent 自动生成 | Agent | 精准 spec 注入 |
| `.aies/workspace/{dev}/journal.md` | Agent 自动追加 | Agent（接续会话）| 跨会话记忆 |
| `.ai/index.md` | Agent（完成任务后更新）| Agent（禁止编造）| 项目地图 |
| `.ai/changelog.md` | Agent（Spec 回流时）| Agent | Spec 变更记录 |

---

## Agent 的边界

**Agent 自主执行（不需要问人）**：
- 创建任务目录和文件
- 填写 prd.md / acceptance.md / context.jsonl
- 读取和写入 spec 文件（回流确认后）
- 追加会话日志
- 归档完成的任务
- 更新 .ai/index.md

**必须暂停等待人确认**：
- 展示 prd + acceptance 提议后
- 展示 Spec 回流内容后
- `git commit` / `git push` 前

**禁止**：
- ❌ 编造 .ai/index.md 中不存在的函数/类型
- ❌ Spec 回流沉默跳过
- ❌ acceptance.md 留 TODO（必须基于意图填写真实场景）
- ❌ 未经人确认执行 git 操作

---

## 意图路由速查

| 用户说 | Agent 做 |
|--------|---------|
| "帮我做X" / "实现Y" / "加一个Z" | `/aies:task` |
| "继续" / "上次那个" | 读 journal，恢复上下文，继续实现 |
| "做完了" / "收尾" / "提交" | `/aies:finish` |
| "初始化" / "setup" / 检测到 .aies 不存在 | `/aies:bootstrap` |
| "进度" / "在做什么" | `task.py list` + journal 摘要 |
| 技术问题 / 方案讨论 | 读 .ai/index.md，基于项目上下文回答 |
