# ai-pipeline — AIES Agent 操作系统

> **定位**：人描述意图，Agent 驱动执行。`.aies/` + `.ai/` 是 Agent 的上下文体系和跨会话记忆。

---

## 项目背景（一分钟了解）

`ai-pipeline` 是内容创作流水线库，用 LangGraph 搭建：

- **SubGraph 作为可复用组件**（research / transcribe / write_book / routing）
- **主 Graph 只做编排**（HITL + fan-out，业务逻辑全在 SubGraph）
- **Langfuse 全链路可观测**（LLM trace / 成本 / 耗时）

当前：4 个 SubGraph，1 个 Pipeline（01-video-md），34 项测试全通过。

---

## Agent 工作模式

**不要等人告诉你怎么做。根据人说的话，自己判断该做什么。**

```
用户描述新需求/功能    → /aies:task（意图解析 → 填 prd+acceptance → 提议 → 确认 → 实现）
继续/上次/那个任务     → /aies:start → 读 journal 接续
做完了/收尾/提交       → /aies:finish（Phase3 + Spec 回流 + 日志）
初始化/.aies 不存在    → /aies:bootstrap
进度/状态             → task list + journal 摘要
技术问题              → 读 .ai/index.md 后基于项目上下文回答
```

---

## 提议协议

**提议而非询问**：Agent 基于意图生成 prd + acceptance，展示给用户确认。

```
❌ "请问您需要什么功能？"
✅ "我的理解：你要做X。验收标准是[3条]。说'ok'开始，或告诉我哪里要改。"
```

---

## 上下文体系

```
读：
  .aies/spec/index.md         规范总导航（写代码前必读）
  .aies/spec/architecture.md  架构约束（SubGraph/主Graph 分层）
  .aies/spec/guides/          Thinking Guides（动手前按场景选读）
  .ai/index.md                项目地图（禁止编造里面没有的函数/类型）
  .aies/tasks/{slug}/context.jsonl  本任务需要的 spec 清单

写：
  .aies/tasks/{slug}/prd.md          Agent 填，人确认
  .aies/tasks/{slug}/acceptance.md   Agent 填，人确认
  .aies/workspace/zyongzhu/          自动追加会话日志
  .aies/spec/*.md                    Spec 回流时直接修改
  .ai/index.md                       完成任务后更新
  .ai/changelog.md                   Spec 变更记录
```

---

## Thinking Guides（动手前选读）

| 场景 | Guide |
|------|-------|
| 新增 SubGraph / Node / 工具函数前 | `spec/guides/code-reuse.md` |
| 跨 SubGraph / 主 Graph 调用 | `spec/guides/cross-layer.md` |
| 涉及 LLM 调用路径、Langfuse trace | `spec/guides/cross-layer.md` |

---

## 人必须拍板的两个点

1. **prd + acceptance 提议展示后** — 用户说"ok"才开始实现
2. **Spec 回流展示后** — 用户确认才写入 spec 文件

---

## 三条铁律

- ❌ 禁止编造 `.ai/index.md` 中不存在的 SubGraph/函数/类型
- ❌ 禁止 Spec 回流沉默跳过
- ❌ 禁止未经用户说"提交"执行 git commit/push

---

## 快速参考

```bash
# 运行测试（每次 implement 后必须）
pytest tests/ -v

# 查看活跃任务
python3 .aies/scripts/task.py list

# 获取会话上下文
python3 .aies/scripts/session.py get-context
```

详细规范：`.aies/spec/index.md`
项目地图：`.ai/index.md`
