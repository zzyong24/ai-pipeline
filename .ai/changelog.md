# ai-pipeline 变更日志

> 每次变更后追加一行。格式：`| 日期 | 变更内容 | 涉及文件 |`

| 日期 | 变更内容 | 涉及文件 |
|------|---------|---------|
| 2026-04-24 | 落地 AIES 脚手架（AI 工程化底座）：新增 `.ai/` + `.aies/` + 平台入口文件（Claude/Cursor/CodeBuddy/Universal）；开发者身份初始化为 zyongzhu | `.ai/*`、`.aies/*`、`CLAUDE.md`、`.cursor/`、`.codebuddy/` |
| 2026-04-24 | 定制化填充 Spec：architecture.md（SubGraph 架构约束）、code-style.md（Python/LangGraph 风格）、glossary.md（业务术语）、known-issues.md（技术债/roadmap）、context-guide.md（场景上下文） | `.aies/spec/*`、`.ai/*` |
| 2026-04-24 | 项目索引 `.ai/index.md` 按 SubGraph/Pipeline 结构填写（3 个 SubGraph + 01-video-md Pipeline） | `.ai/index.md` |
| 2026-04-24 | review-checklist 加入项目特定检查项（LangGraph 反模式、SubGraph 架构合规、fan-out 规则） | `.ai/review-checklist.md` |
| 2026-04-24 | `119efa6` 首次正式提交 AIES 脚手架到 ai-pipeline（merge 模式，未覆盖原有代码，新增 48 个文件） | `.ai/**`、`.aies/**`、`.claude/**`、`.cursor/**`、`.codebuddy/**`、`CLAUDE.md` |
