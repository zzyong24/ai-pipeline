# PRD：content 路由 SubGraph — 内容分类落库到 vault

> 任务 ID：`04-30-content-routing-subgraph`
> 优先级：P2（依赖 `04-24-langfuse-integration` 完成后实施）
> 目标：Pipeline 产出书稿后，自动判断内容类型、选择落库路径，通过 ThirdSpace MCP 写入 vault。

---

## 一、现状与问题

- `node_notify` 现在只把书稿写到本地文件 `output/book/*.md`，没有写入 vault
- vault 有严格的 frontmatter 规范（7 必填字段）和目录结构，手动写入容易出错
- 未来 Pipeline 增多，每个都自己实现落库逻辑会重复造轮子
- 内容类型（学习文档 vs 知识卡片 vs 工作笔记）需要根据内容动态决策，不是写死的

---

## 二、目标状态

Pipeline 跑完后，书稿自动出现在 vault 对应目录：

```
vault/space/study/reading/
  └── 2026-04-30_AI-Agent发展趋势_学习文档.md   ← 自动落库
      (frontmatter 完整，topic/tags 正确)
```

Langfuse 中可以看到：
```
span: route_content
  ├── match_method: "rule"   ← 规则命中还是 LLM fallback
  └── generation: llm_classify（仅 fallback 时有）
```

---

## 三、架构

### 3.1 整体流程（插入位置）

```
write_book_subgraph → [node_route_content] → [node_save_to_vault] → notify → END
```

`node_route_content` 和 `node_save_to_vault` 都是主 Graph 的胶水节点，不放进 SubGraph 库。
`routing_subgraph` 是可复用组件，只负责「分类决策」，不直接调 ThirdSpace。

### 3.2 routing_subgraph 内部结构

```
RoutingState 输入（title + summary + source_type）
    ↓
[rule_match_node]
    ├── 命中 → 直接输出 RouteDecision，match_method="rule"
    └── 未命中 → [llm_classify_node]
                    ↓ 结构化输出（Pydantic schema）
                    match_method="llm"
    ↓（两路汇合）
[validate_node]
    ├── content_type 合法 → 通过
    └── 非法 → error，fallback 到 "study_doc/reading"
    ↓
RouteDecision 输出
```

---

## 四、State 设计

```python
# subgraphs/routing_subgraph/state.py

class RouteDecision(TypedDict):
    content_type: str    # "study_doc" | "knowledge_card" | "article" | "note"
    topic: str           # "reading" | "ai" | "dev" | ...
    tags: List[str]
    confidence: float    # 规则命中=1.0，LLM 输出原始置信度

class RoutingState(TypedDict, total=False):
    # 输入
    title: str
    summary: str
    source_type: str         # "video" | "podcast" | "article" | "web"
    source_url: str
    raw_content: str         # 可选，LLM 分类时使用

    # 透传（由主 Graph 注入，routing_subgraph 不创建）
    _trace_span: Optional[Any]

    # 中间状态
    match_method: str        # "rule" | "llm"
    matched_rule: Optional[str]

    # 输出
    route_decision: Optional[RouteDecision]
    error: Optional[str]
```

---

## 五、Config 设计

```python
# subgraphs/routing_subgraph/config.py

@dataclass
class RoutingRule:
    # 匹配条件（至少一个有值，按优先级依次匹配）
    source_type: Optional[str] = None       # 精确匹配 state.source_type
    keywords: List[str] = field(default_factory=list)  # title 或 summary 含任一关键词
    domain: Optional[str] = None            # source_url 的域名匹配

    # 路由结果
    content_type: str = "study_doc"
    topic: str = "reading"
    tags: List[str] = field(default_factory=list)

@dataclass
class RoutingConfig:
    rules: List[RoutingRule]              # 由主 Graph 注入，SubGraph 内不硬编码
    llm_fallback: bool = True             # False 时规则未命中直接用默认值
    default_content_type: str = "study_doc"
    default_topic: str = "reading"
    confidence_threshold: float = 0.7    # LLM 置信度低于此值时写 warning 日志
    timeout: int = 30
```

### 01-video-md 注入的默认规则

```python
RoutingConfig(rules=[
    RoutingRule(source_type="video",
                content_type="study_doc", topic="reading"),
    RoutingRule(source_type="podcast",
                content_type="study_doc", topic="reading"),
    RoutingRule(keywords=["论文", "研究", "实验", "数据集"],
                content_type="knowledge_card", topic="ai"),
    RoutingRule(keywords=["教程", "手册", "实战", "指南"],
                content_type="study_doc", topic="reading"),
    RoutingRule(domain="github.com",
                content_type="note", topic="dev"),
])
```

---

## 六、节点实现要点

### rule_match_node

- 按 rules 顺序遍历，首个命中即返回（优先级由顺序决定）
- 匹配顺序：source_type → domain → keywords（从精确到模糊）
- 命中时 `confidence=1.0`，`match_method="rule"`
- 未命中时不写 route_decision，流向 llm_classify_node

### llm_classify_node

- 只在 rule_match_node 未命中时执行
- 用 `langchain_anthropic.ChatAnthropic` 对接 MiniMax（与 langgraph-fastapi-muilt-agent 一致，已验证可用）
- 结构化输出（`with_structured_output(RouteDecisionSchema)`）
- 把 `_trace_span` 传给 observability 层记录 generation
- 失败时 fallback 到 `(default_content_type, default_topic)`

### validate_node

- 校验 `content_type` 在合法列表内：`["study_doc", "knowledge_card", "article", "note"]`
- topic 不校验（ThirdSpace 会处理不存在的 topic）
- 不合法时写 error，同时 fallback 到默认值（不让 Pipeline 因此中断）

---

## 七、主 Graph 胶水节点

### node_route_content（新增）

```python
def node_route_content(state: PipelineState) -> Dict[str, Any]:
    """调 routing_subgraph，把 RouteDecision 写回主 State。"""
    sub_input: RoutingState = {
        "title": state.get("topic", ""),
        "summary": (state.get("book_draft") or "")[:500],  # 摘要截断
        "source_type": "video",
        "source_url": (state.get("approved_videos") or [""])[0],
        "_trace_span": state.get("_trace_span"),
    }
    sub_result = _get_routing_subgraph().invoke(sub_input)
    decision = sub_result.get("route_decision")
    method = sub_result.get("match_method", "rule")
    print(f"[main:route_content] → {decision} (method={method})")
    return {"route_decision": decision}
```

### node_save_to_vault（新增）

⚠️ **关键决策点**：ThirdSpace 的 `save_study_doc()` / `save_knowledge_card()` 是 MCP 工具，在 Claude Code 运行环境中可直接调用。但 ai-pipeline 是独立 Python 进程，**不在 Claude Code 环境中**。

实施前需确认落库方式（二选一）：
1. **HTTP 方式**：若 ThirdSpace MCP server 有 HTTP 接口，Python 直接调
2. **直接写文件**：按 `vault-writing-spec.md` 规范直接构造 frontmatter + 写文件（绕过 MCP，但需维护规范一致性）

在确认前，`node_save_to_vault` 先实现为「生成规范 frontmatter + 写本地文件」，留 TODO 注释等待 ThirdSpace 接入方式确认后替换。

---

## 八、PipelineState 新增字段

```python
class PipelineState(TypedDict, total=False):
    # ... 原有字段 ...
    route_decision: Optional[Dict[str, Any]]  # routing_subgraph 输出
    vault_saved: bool                          # 是否已落库
```

---

## 九、文件结构

```
subgraphs/routing_subgraph/
├── __init__.py          # export: build_routing_subgraph, RoutingState, RoutingConfig
├── graph.py             # build_routing_subgraph(config: RoutingConfig)
├── nodes.py             # rule_match_node / llm_classify_node / validate_node
├── state.py             # RoutingState, RouteDecision
├── config.py            # RoutingConfig, RoutingRule
├── test.py              # 覆盖三种情况（见验收标准）
└── README.md

01-video-md/main_graph.py    # 新增 node_route_content + node_save_to_vault
                             # 在 write_book_node 和 notify 之间插入
```

---

## 十、验收标准

- [ ] `python -m subgraphs.routing_subgraph.test` 通过三种情况：
  - 规则命中（video → study_doc/reading，无 LLM 调用）
  - LLM fallback（无规则匹配，LLM 返回合法 RouteDecision）
  - 无法分类（LLM 也失败，fallback 到默认值，不崩溃）
- [ ] 跑 `01-video-md/run.py`，日志中出现 `[main:route_content] → ...`
- [ ] Langfuse trace 中 `route_content` span 可见，`match_method` 字段可见
- [ ] LLM fallback 时 Langfuse 中有 `llm_classify` generation 记录
- [ ] 落库方式确认后，书稿出现在 vault 对应目录，frontmatter 完整（7 必填字段）
