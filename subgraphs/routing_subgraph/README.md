# routing_subgraph

内容路由 SubGraph：根据标题、摘要、来源类型决定内容分类。

## 图结构

```
rule_match -> llm_classify -> validate -> END
```

## Input State

| 字段 | 类型 | 说明 |
|------|------|------|
| title | str | 内容标题 |
| summary | str | 内容摘要 |
| source_type | str | "video" / "podcast" / "article" / "web" |
| source_url | str | 来源 URL |
| _trace_span | Optional[Any] | Langfuse trace（预留） |

## Output State

| 字段 | 类型 | 说明 |
|------|------|------|
| route_decision | RouteDecision | content_type + topic + tags + confidence |
| match_method | str | "rule" / "llm" |
| error | Optional[str] | 错误信息 |

## Config

```python
RoutingConfig(
    rules=[RoutingRule(...)],   # 规则列表
    llm_fallback=True,          # 是否启用 LLM fallback
    default_content_type="study_doc",
    default_topic="reading",
    confidence_threshold=0.7,
    timeout=30,
)
```

## 独立测试

```bash
python -m subgraphs.routing_subgraph.test
```
