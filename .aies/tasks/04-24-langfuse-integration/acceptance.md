# 验收与测试：接入 Langfuse 可观测

> 任务 ID：`04-24-langfuse-integration`
> 对应 PRD：prd.md

---

## 一、验收场景（从用户需求出发）

| # | 用户场景 | 输入 | 期望输出 | 优先级 |
|---|---------|------|---------|-------|
| AC-01 | 未配置 Langfuse 环境变量时跑 Pipeline | `LANGFUSE_PUBLIC_KEY` 未设置 | Pipeline 正常完成，无报错，无 trace 上报 | P0 |
| AC-02 | 配置 Langfuse 后跑 Pipeline | `LANGFUSE_PUBLIC_KEY` 已设置 | Langfuse UI 出现对应 trace，含 span 层级 | P0 |
| AC-03 | 查看 trace 详情 | trace 点开 | 可见 research/transcribe×N/write_book 各 span | P0 |
| AC-04 | 查看单次 LLM 调用 | generation 点开 | 可见模型名、prompt 摘要、耗时、tokens | P1 |
| AC-05 | LLM 调用失败时 | API 返回错误 | generation 显示 ERROR 状态，Pipeline 仍有 fallback | P1 |
| AC-06 | research_subgraph 独立测试 | `python -m subgraphs.research_subgraph.test` | 正常完成，`_trace_span=None` 时静默跳过 | P0 |

---

## 二、单元测试矩阵

| 测试用例 | 被测函数/类 | 输入 | 期望输出 | Mock 什么 |
|---------|-----------|------|---------|---------|
| UT-01 | `get_langfuse()` | `LANGFUSE_PUBLIC_KEY` 未设 | 返回 `None` | 无 |
| UT-02 | `get_langfuse()` | 已设 key | 返回 `Langfuse` 实例 | `Langfuse.__init__` |
| UT-03 | `llm_minimax()` | `trace_span=None` | 正常返回，不调 span 方法 | HTTP 请求 |
| UT-04 | `llm_minimax()` | `trace_span=mock_span` | 调用 `span.generation()`，正常返回 | HTTP 请求 |
| UT-05 | `llm_minimax()` | API 抛异常，`trace_span=mock_span` | 调用 `gen.end(level="ERROR")`，重新抛异常 | HTTP 请求 |
| UT-06 | `span()` 上下文管理器 | 正常执行 | `s.end()` 被调用 | 无 |
| UT-07 | `span()` 上下文管理器 | 内部抛异常 | `s.end(level="ERROR")` 被调用，异常继续传播 | 无 |
| UT-08 | `research_node` | `_trace_span=mock_trace` | `llm_minimax` 收到 `trace_span=mock_trace` | llm_minimax |
| UT-09 | `research_node` | `_trace_span=None` | `llm_minimax` 收到 `trace_span=None` | llm_minimax |

**测试文件位置**：`tests/unit/test_observability.py`、`tests/unit/test_llm.py`

---

## 三、端到端测试（E2E）

### Happy Path — Langfuse 未配置

```
场景：最常见的开发场景，本地没起 Langfuse
1. 不设 LANGFUSE_PUBLIC_KEY 环境变量
2. 构建 research_subgraph 并调用
3. 断言：
   - subgraph 正常返回结果
   - 没有任何 Langfuse 相关异常
```

```bash
python -m tests.e2e.test_langfuse_disabled
```

### Happy Path — Langfuse 已配置（集成测试）

```
场景：Langfuse 已部署，验证 trace 上报
1. 设置 LANGFUSE_PUBLIC_KEY / SECRET / HOST
2. 创建 trace，执行 research_subgraph（mock LLM）
3. 断言：
   - trace 创建成功
   - generation 记录被写入（通过 mock Langfuse client 验证调用）
```

```bash
python -m tests.e2e.test_langfuse_enabled
```

### 异常路径

| 场景 | 模拟方法 | 期望行为 |
|------|---------|---------|
| Langfuse 服务不可用 | mock `Langfuse.__init__` 抛异常 | `get_langfuse()` 返回 None，Pipeline 正常运行 |
| LLM 调用失败 | `llm_minimax` 抛 RuntimeError | generation 记录 ERROR，SubGraph 返回 error 字段 |
| `langfuse` 包未安装 | ImportError | `get_langfuse()` 返回 None，不崩溃 |

---

## 四、验收命令

```bash
cd /Users/zyongzhu/workbase/github/moon/ai-pipeline

# 单元测试
pytest tests/unit/test_observability.py tests/unit/test_llm.py -v

# E2E（Langfuse 未配置场景，CI 可跑）
python -m tests.e2e.test_langfuse_disabled

# 手动验收（需要真实 Langfuse 实例）
# 1. docker compose up langfuse
# 2. 设置 .env 中的 LANGFUSE_* 变量
# 3. python -m tests.e2e.test_langfuse_enabled
# 4. 打开 localhost:3000 确认 trace 出现

# 全量单元测试
pytest tests/unit/ -v
```

---

## 五、验收通过标准

- [ ] AC-01：未配置时 Pipeline 正常，无报错 ✅
- [ ] AC-02：配置后 Langfuse UI 出现 trace ✅
- [ ] AC-03：trace 含各 SubGraph span ✅
- [ ] AC-04：generation 有模型名/耗时 ✅
- [ ] AC-05：LLM 失败时 generation 显示 ERROR ✅
- [ ] AC-06：独立 test.py 仍正常运行 ✅
- [ ] 单元测试矩阵 UT-01 ~ UT-09 全部通过
- [ ] E2E `test_langfuse_disabled` 通过
- [ ] 无真实网络请求（全部 mock）
- [ ] 现有三个 SubGraph 的 `test.py` 未被破坏
