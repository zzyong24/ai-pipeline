# 验收与测试：content 路由 SubGraph

> 任务 ID：`04-30-content-routing-subgraph`
> 对应 PRD：prd.md

---

## 一、验收场景（从用户需求出发）

| # | 用户场景 | 输入 | 期望输出 | 优先级 |
|---|---------|------|---------|-------|
| AC-01 | 视频 Pipeline 产出书稿，自动分类 | `source_type="video"` | `content_type="study_doc"`, `topic="reading"`，规则命中无 LLM 调用 | P0 |
| AC-02 | 含"论文"关键词的内容自动分类 | `title="某某论文解析"` | `content_type="knowledge_card"`, `topic="ai"` | P0 |
| AC-03 | 无规则匹配时 LLM fallback | 无 source_type、无关键词匹配 | LLM 被调用，返回合法 RouteDecision | P0 |
| AC-04 | LLM 也失败时系统不崩溃 | LLM 抛异常 | fallback 到默认值 `study_doc/reading`，`error` 字段有值 | P0 |
| AC-05 | 整条 Pipeline 跑完后路由决策写入 State | 完整 Pipeline 执行 | `state.route_decision` 有值，日志出现 `[main:route_content]` | P1 |
| AC-06 | Langfuse 中可见路由 span | Langfuse 已配置 | `route_content` span 可见，`match_method` 字段可见 | P1 |

---

## 二、单元测试矩阵

### routing_subgraph 节点

| 测试用例 | 被测函数 | 输入 | 期望输出 | Mock 什么 |
|---------|---------|------|---------|---------|
| UT-01 | `rule_match_node` | `source_type="video"` | `match_method="rule"`, `content_type="study_doc"` | 无 |
| UT-02 | `rule_match_node` | `keywords` 含"论文" | `match_method="rule"`, `topic="ai"` | 无 |
| UT-03 | `rule_match_node` | `source_url` 含 `github.com` | `match_method="rule"`, `content_type="note"` | 无 |
| UT-04 | `rule_match_node` | 无任何匹配条件 | `route_decision=None`（交给 llm_classify） | 无 |
| UT-05 | `llm_classify_node` | 正常输入，LLM 返回合法 JSON | `match_method="llm"`, `RouteDecision` 合法 | LLM 调用 |
| UT-06 | `llm_classify_node` | LLM 抛异常 | fallback 到默认值，`error` 有值 | LLM 调用 |
| UT-07 | `validate_node` | `content_type="study_doc"` | 通过，`route_decision` 不变 | 无 |
| UT-08 | `validate_node` | `content_type="invalid_type"` | fallback 到默认值，`error` 有值 | 无 |
| UT-09 | `validate_node` | `route_decision=None`（上游全失败） | fallback 到默认值 | 无 |

### 规则匹配优先级测试

| 测试用例 | 场景 | 期望 |
|---------|------|------|
| UT-10 | `source_type` 和 `keywords` 同时匹配两条不同规则 | 取 rules 列表中靠前的规则 |
| UT-11 | 空 rules 列表 | 直接进 LLM fallback |

**测试文件位置**：`tests/unit/test_routing_subgraph.py`

---

## 三、端到端测试（E2E）

### Happy Path — 规则命中

```
场景：视频 Pipeline 完整运行，route_content 节点规则命中
1. 准备：mock LLM（research + transcribe + write_book）
2. 执行：Pipeline 完整跑，source_type="video"
3. 断言：
   - state["route_decision"]["content_type"] == "study_doc"
   - state["route_decision"]["topic"] == "reading"
   - match_method == "rule"
   - LLM classify 没被调用（规则已命中）
   - 日志含 [main:route_content] → ...
```

```bash
python -m tests.e2e.test_routing_happy_path
```

### Happy Path — LLM Fallback

```
场景：内容无法被规则匹配，走 LLM fallback
1. 准备：空规则列表，mock LLM classify 返回合法 RouteDecision
2. 执行：routing_subgraph.invoke({"title": "随机内容", "summary": "..."})
3. 断言：
   - match_method == "llm"
   - route_decision 合法
   - LLM classify 被调用一次
```

```bash
python -m tests.e2e.test_routing_llm_fallback
```

### 异常路径

| 场景 | 模拟方法 | 期望行为 |
|------|---------|---------|
| LLM classify 完全失败 | mock 抛 RuntimeError | fallback 到 `study_doc/reading`，`error` 字段有值，不崩溃 |
| 规则配置为空列表 | `RoutingConfig(rules=[])` | 直接走 LLM fallback |
| `source_type` 和 `title`/`summary` 均为空 | 空 State | fallback 到默认值 |
| LLM 返回非法 `content_type` | mock 返回 `{"content_type": "xxx"}` | validate_node 改为默认值 |

---

## 四、验收命令

```bash
cd /Users/zyongzhu/workbase/github/moon/ai-pipeline

# 单元测试
pytest tests/unit/test_routing_subgraph.py -v

# E2E
python -m tests.e2e.test_routing_happy_path
python -m tests.e2e.test_routing_llm_fallback

# routing_subgraph 独立真实测试（需 API Key）
python -m subgraphs.routing_subgraph.test

# 全量
pytest tests/unit/ -v
```

---

## 五、验收通过标准

- [ ] AC-01：video 自动路由到 study_doc/reading，无 LLM 调用 ✅
- [ ] AC-02：论文关键词路由到 knowledge_card/ai ✅
- [ ] AC-03：无匹配时 LLM fallback 返回合法结果 ✅
- [ ] AC-04：LLM 完全失败时 fallback 不崩溃 ✅
- [ ] AC-05：Pipeline 日志出现 `[main:route_content]` ✅
- [ ] 单元测试 UT-01 ~ UT-11 全部通过
- [ ] E2E `test_routing_happy_path` 通过
- [ ] E2E `test_routing_llm_fallback` 通过
- [ ] 所有异常路径不崩溃，有明确 fallback
- [ ] 无真实网络请求（全部 mock）
- [ ] `routing_subgraph/test.py` 独立可运行
