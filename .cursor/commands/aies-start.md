# aies-start

初始化 AIES 会话：读取上下文 + 规范。

## 执行步骤

1. 运行 `python3 .aies/scripts/session.py get-context` 获取开发者/任务/git 状态
2. 读取 `.aies/workflow.md`、`.aies/spec/index.md`、`.ai/index.md`
3. 输出 session 初始化报告
4. 若有活跃任务，询问是否继续
