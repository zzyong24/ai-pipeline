# AGENTS.md — 通用 AI Agent 入口

> 适用于任何不在 `platforms/` 中独立适配的 AI 工具。

## 项目规范入口

1. 读取 `.aies/workflow.md` 理解工作流
2. 读取 `.aies/spec/index.md` 加载规范
3. 读取 `.ai/index.md` 理解项目
4. 按 `.aies/workflow.md` 的 Phase 1/2/3 协议执行任务

## 关键能力

```bash
# 会话上下文
python3 .aies/scripts/session.py get-context

# 任务管理
python3 .aies/scripts/task.py list

# 完成后记录
python3 .aies/scripts/session.py add --title "..." --summary "..."
```

## 禁止

- 跳过 Phase 1 清单直接写代码
- 大段重写未要求的代码
- git 相关操作未经用户确认
