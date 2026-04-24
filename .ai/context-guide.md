# AI 开发上下文指南（ai-pipeline）

> 不同开发场景需要给 AI 提供不同的上下文文件。
> 遵循「最小充分上下文」原则：给够参考但不过载。

---

## 场景 1：新增 SubGraph

**必读**：
- `.aies/spec/architecture.md` → SubGraph 设计约束（最重要）
- `.aies/spec/code-style.md` → 代码风格
- `.ai/index.md` → 看现有 SubGraph 列表

**参考模板**：
- `subgraphs/research_subgraph/` 全目录（结构最简单）
- 或 `subgraphs/transcribe_subgraph/`（多步流程示例）

**必须产出**：
```
subgraphs/{name}_subgraph/
├── __init__.py       # 导出 build_xxx_subgraph, XxxState
├── graph.py          # build_xxx_subgraph(config)
├── nodes.py          # node 实现
├── state.py          # XxxState TypedDict
├── config.py         # XxxConfig dataclass
├── test.py           # python -m 可跑的独立测试
└── README.md
```

**禁止**：
- ❌ 把文件堆在一个 py 里
- ❌ 在 SubGraph 内读环境变量
- ❌ 依赖任何 Pipeline 特定模块

---

## 场景 2：新增 Pipeline

**必读**：
- `.aies/spec/architecture.md` → 主 Graph 编排约束
- `.ai/index.md` → SubGraph 列表
- `01-video-md/main_graph.py` → 参考模板（最完整的 Pipeline）
- `01-video-md/readme.md` → 流程说明
- `01-video-md/run.py` → CLI 模式

**重点关注**：
- fan-out 规则（`List[Send]` 只能从 conditional edge 返回）
- Reducer（`Annotated[list, lambda a,b: a+b]`）
- 父子 State 映射（胶水 node）
- HITL（如需）：`raise NodeInterrupt(id="...")`

---

## 场景 3：修改现有 SubGraph

**必读**：
- 目标 SubGraph 全部 6 个文件（graph/nodes/state/config/test/README）
- **所有调用该 SubGraph 的主 Graph 文件**（搜 `build_{name}_subgraph`）
  - 需确认 State 改动不破坏父子映射

**禁止**：
- ❌ 改 SubGraph 的 `State` / `Config` schema 但不同步更新调用方

---

## 场景 4：修改 fan-out / dispatcher 逻辑

**必读**：
- `01-video-md/main_graph.py` 中 `node_dispatcher` + `route_dispatcher`
- `.aies/spec/architecture.md` 的「fan-out 规则」章节

**测试要求**：
- 0 个并行任务场景（全部 reject）
- 1 个并行任务场景
- N 个并行任务场景（N≥5）
- 部分失败场景

---

## 场景 5：修改 HITL 审核逻辑

**必读**：
- `01-video-md/main_graph.py` 中 `node_send_review_request` + `node_wait_review` + `_save_review` / `_get_review`
- `review_status.db` 的表结构

**注意**：
- HITL 状态必须和 LangGraph Checkpointer 分离（独立 DB）
- 必须有超时机制（默认 1 小时）

---

## 场景 6：接入 Langfuse（roadmap）

**必读**：
- `.ai/known-issues.md` 事项 #9
- `subgraphs/shared/llm.py`
- `HERMES_TASK.md` 阶段 3

**要改的地方**：
- `subgraphs/shared/llm.py` 注入 Langfuse callback
- 每个 SubGraph 的 `build_xxx_subgraph` 接收 `langfuse_handler` 参数

---

## 场景 7：Bug 修复

**必读**：
- `.ai/index.md` 定位相关模块
- `.ai/known-issues.md` 检查是否已知问题
- 出问题的文件 + 调用方

**五问分析**：
1. 根因是什么？（不是现象）
2. 其他地方有同样模式吗？
3. 是 SubGraph 的 bug 还是主 Graph 的 bug？
4. 是规范缺口还是实现 bug？
5. 应该加什么测试避免回归？

---

## 场景 8：修改 CLI（run.py）

**必读**：
- `01-video-md/run.py`
- `01-video-md/readme.md` 的「触发方式」章节

**验证**：
- `./run.py start`
- `./run.py status --thread-id xxx`
- `./run.py continue --thread-id xxx`
- `./run.py approve/reject/modify`
- `./run.py list`

---

## 场景 9：Pipeline 代码审查（Code Review）

**必读**：
- `.ai/review-checklist.md`
- `.aies/spec/architecture.md` + `code-style.md`
- 待审查文件

**重点检查项**（针对本项目）：
- [ ] 主 Graph 是否写了业务逻辑？
- [ ] SubGraph 是否依赖了 Pipeline 特定模块？
- [ ] State 的并行字段是否加了 reducer？
- [ ] `List[Send]` 是不是只从 conditional edge 返回？
- [ ] SubGraph 是否有 test.py？
- [ ] 日志前缀是否用 `[模块:node]`？

---

## 通用提示

1. **始终加载 Spec**：`.aies/spec/architecture.md` 是本项目最关键的规范
2. **参考现有 SubGraph**：模仿 `research_subgraph/` 的结构，比从零写更一致
3. **不确定时查 index.md**：SubGraph 入口、State schema、Config 字段都在索引里
4. **涉及 Hermes 编排的任务，读 `HERMES_TASK.md`**：这是项目的"任务书"
