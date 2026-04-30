# ai-pipeline — 项目索引

> ⚠️ **维护规则**：每次新增/修改/删除文件后，必须同步更新本索引。
> 最后更新：2026-04-30

---

## 一、项目定位

**内容创作流水线库**，用 LangGraph 搭建。核心设计：

- **SubGraph 作为可复用组件**（不走 MCP 暴露，避免上下文膨胀）
- **主 Graph 只做编排**（业务逻辑全部下沉到 SubGraph）
- **LangGraph 单栈**（不引入 Temporal，用 Checkpointer 做持久化）

### 技术栈锁定

| 层 | 技术 | 说明 |
|----|------|------|
| 编排 | LangGraph | SubGraph 组合 + Checkpointer 持久化 |
| 可视化/调试 | LangGraph Studio | 开发期必开 |
| LLM 可观测 | Langfuse | trace / 成本 / eval |
| 执行代理 | Claude Code（via Hermes MCP） | Hermes 指挥 Claude Code 写代码 |
| 长流程可靠性 | Checkpointer（SqliteSaver） | 崩了手动重启 |
| ❌ 明确不用 | Temporal、MCP 暴露 SubGraph | 已弃用 |

---

## 二、目录结构总览

```
ai-pipeline/
├── README.md                   # 🆕 项目总览（待创建）
├── requirements.txt            # ✅ 依赖清单
├── .env.example                # ✅ 环境变量模板
├── AGENTS.md / CLAUDE.md       # AI 平台入口
│
├── subgraphs/                  # 🧩 可复用 SubGraph 库（共享给所有 Pipeline）
│   ├── __init__.py
│   ├── shared/                 # 共享工具
│   │   ├── llm.py             # LLM 调用封装（含 Langfuse trace_span 埋点）
│   │   ├── observability.py   # ✅ Langfuse 封装（懒加载，None 安全）
│   │   └── timeout.py         # 超时工具
│   ├── research_subgraph/      # 主题 → 候选视频 URL
│   │   ├── graph.py / nodes.py / state.py / config.py / test.py / README.md
│   ├── transcribe_subgraph/    # 视频 → 摘要（下载→转录→总结 3 步）
│   │   └── （同上结构）
│   ├── write_book_subgraph/    # 摘要 → 书稿（聚合→写 2 步）
│   │   └── （同上结构）
│   └── routing_subgraph/       # ✅ 内容分类路由（规则+LLM fallback）
│       ├── graph.py / nodes.py / state.py / config.py / test.py / README.md
│
├── tests/                      # ✅ 测试目录
│   ├── conftest.py             # 全局 fixtures（mock_llm_* 等）
│   ├── unit/                   # 单元测试（34 项，全部通过）
│   │   ├── test_observability.py
│   │   ├── test_llm.py
│   │   └── test_routing_subgraph.py
│   └── e2e/                    # 端到端测试
│       ├── test_langfuse_disabled.py
│       ├── test_routing_happy_path.py
│       └── test_routing_llm_fallback.py
│
├── 01-video-md/                # 📼 Pipeline 1：视频→书稿（已完成）
│   ├── main_graph.py          # 主 Graph（含 route_content + save_to_vault 节点）
│   ├── run.py                 # CLI 入口（使用 run_pipeline()）
│   ├── readme.md
│   └── tools_src/             # 工具源码（下载/转录/总结）
│
├── 02-podcast-md/              # 🆕 Pipeline 2：播客→书稿（roadmap）
│
├── observability/              # ✅ 可观测
│   └── langfuse_setup.md      # Langfuse Docker Compose 自部署指南
│
└── mcp_server/                 # 🆕 Pipeline MCP Server（roadmap）
```

---

## 三、SubGraph 清单

| SubGraph | 入口函数 | Input State | Output | 职责 |
|---------|---------|------------|--------|------|
| `research_subgraph` | `build_research_subgraph(ResearchConfig)` | `{topic: str}` | `{video_urls: [...], selected_videos: [...]}` | LLM 搜索主题相关视频 |
| `transcribe_subgraph` | `build_transcribe_subgraph(TranscribeConfig)` | `{video_url, task_idx, topic}` | `{success, title, file_path, srt_path, summary, duration}` | 视频下载→转录→摘要 |
| `write_book_subgraph` | `build_write_book_subgraph(WriteBookConfig)` | `{topic, summaries: [...]}` | `{book: str}` | 摘要聚合 → 生成书稿 |
| `routing_subgraph` | `build_routing_subgraph(RoutingConfig)` | `{title, summary, source_type, source_url}` | `{route_decision: RouteDecision, match_method}` | ✅ 内容分类路由（规则+LLM fallback） |
| `shared/` | — | — | — | `llm.py`（含 trace_span）+ `observability.py` + `timeout.py` |

### 独立测试命令

```bash
cd ai-pipeline/
python -m subgraphs.research_subgraph.test "AI Agent 发展趋势"
python -m subgraphs.transcribe_subgraph.test "https://www.bilibili.com/video/BV.../"
python -m subgraphs.write_book_subgraph.test
```

---

## 四、Pipeline 清单

| Pipeline | 状态 | 入口 | 使用的 SubGraph | 特有逻辑 |
|---------|------|------|----------------|---------|
| `01-video-md` | ✅ 完成 | `./run.py start "..."` | research + transcribe + write_book | HITL 飞书审核、fan-out 分发、飞书通知 |
| `02-podcast-md` | 📋 roadmap | — | transcribe + write_book | 验证 SubGraph 复用 |

---

## 五、01-video-md 主 Graph 流程

```
START → research → send_review_request
                        │
                        ├─ 正常 → wait_review → dispatcher
                        └─ --urls 跳过 → dispatcher
                                            │
                                 ┌──────────┴──────────┐
                                 │ route_dispatcher    │
                                 └──────────┬──────────┘
                                            │
                                 ┌──────────┴──────────┐
                       [Send×N] │                     │ 全部完成
                                ▼                     ▼
                       transcribe_single      write_book_node
                                │                     ▼
                                └──→ dispatcher     notify → END
```

**橙色节点** = 调 SubGraph（`research` / `transcribe_single` / `write_book_node`）
**蓝色节点** = Pipeline 特有（`send_review_request` / `wait_review` / `dispatcher` / `notify`）

### 主 State（`PipelineState`）关键字段

```python
class PipelineState(TypedDict, total=False):
    # 输入
    topic: str
    thread_id: str
    # 流程
    step: Literal["idle", "researching", "awaiting_review", "transcribing",
                  "integrating", "done", "error"]
    review_status: Literal["pending", "approved", "rejected", "timeout", "none"]
    # research 产出
    research_results: Optional[Dict]
    pending_videos: Annotated[List[str], lambda a,b: a+b]   # reducer 合并
    # 审核
    approved_videos / rejected_videos: Annotated[List[str], ...]
    # transcribe 产出（fan-out 合并）
    _dispatched: Annotated[List[str], ...]
    completed_videos / failed_videos / summaries: Annotated[List[...], ...]
    # write_book 产出
    book_draft: Optional[str]
    output_files: Optional[Dict[str, str]]
```

---

## 六、关键文件导航

| 场景 | 文件 |
|------|-----|
| 新增 SubGraph | 参考 `subgraphs/research_subgraph/` 模板（graph/nodes/state/config/test） |
| 新增 Pipeline | 参考 `01-video-md/main_graph.py` 的编排模式 |
| 主 Graph 编排 | `01-video-md/main_graph.py` |
| CLI 入口 | `01-video-md/run.py` |
| 父子 State 映射 | `01-video-md/main_graph.py` 中 `node_transcribe_single` |
| fan-out 分发 | `01-video-md/main_graph.py` 中 `route_dispatcher`（conditional edge） |
| HITL 审核 | `node_send_review_request`（raise `NodeInterrupt`） |
| Checkpointer | `_get_checkpointer()` 单例 + SqliteSaver |
| LLM 调用 | `subgraphs/shared/llm.py` |
| 超时工具 | `subgraphs/shared/timeout.py` |

---

## 七、数据持久化

| 存储 | 位置 | 用途 |
|------|-----|------|
| Checkpoints | `01-video-md/checkpoints.db` | LangGraph SqliteSaver 状态持久化 |
| 审核状态 | `01-video-md/review_status.db` | HITL 审核结果（自定义表） |
| research 产出 | `01-video-md/output/research/{topic}/` | JSON |
| transcribe 产出 | `01-video-md/output/transcribe/task-{idx}/` | 音视频 + 字幕 + 摘要 |
| 书稿输出 | `01-video-md/output/book/{topic}_书稿.md` | 最终产物 |

---

## 八、环境变量

| 变量 | 用途 | 必填 |
|------|-----|------|
| `MINIMAX_CN_API_KEY` | LLM 调用 | ✅ |
| `MINIMAX_API_KEY` | LLM 调用（备用） | — |
| `FEISHU_APP_ID` | 飞书审核通知 | HITL 场景 |
| `FEISHU_APP_SECRET` | 飞书审核通知（或存 macOS keychain `feishu`） | HITL 场景 |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | LLM 可观测 | roadmap |
| `ANTHROPIC_API_KEY` | Claude Code | Hermes 调用 |

---

## 九、迁移历史

| 版本 | 时间 | 变化 |
|------|-----|------|
| v1 | 2026-04 初 | 单文件 `pipeline.py`（758 行），所有 node 在一起 → 已归档为 `pipeline.py.old` |
| v2 | 2026-04-24 | 主 Graph + 3 SubGraph，业务逻辑可复用 |
| v2.1 | 2026-04-24 | 落地 AIES 脚手架（AI 工程化） |

---

## 十、变更日志

> 变更日志独立在 `.ai/changelog.md`（省 token）。
