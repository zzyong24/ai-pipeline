# /aies:start

初始化 AIES 会话。

## 执行步骤

1. 读取 `.aies/workflow.md` 理解工作流
2. 运行 `python3 .aies/scripts/session.py get-context` 获取当前上下文
3. 读取 `.aies/spec/index.md` 查看规范导航
4. 读取 `.ai/index.md` 查看项目地图
5. 输出初始化报告：

```
🌱 AIES Session 已初始化
━━━━━━━━━━━━━━━━━━━━━━━
• 开发者: {从 .aies/.developer 读取}
• 活跃任务: {列表 或 "无活跃任务"}
• 最近提交: {git_hash} — {commit_msg}
• 已加载规范: spec/index.md + review-checklist.md

等待用户第一条指令。
```

6. 如有活跃任务，询问是否继续
